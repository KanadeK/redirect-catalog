from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from redirect_catalog.core import (
    InputError,
    audit,
    canonical_path,
    parse_catalog,
    parse_plan,
    read_text,
)

HEADER = "source,target,status\n"


class CatalogTests(unittest.TestCase):
    def codes(self, report):
        return set(report["summary"]["findings_by_code"])

    def test_complete_migration(self):
        report = audit(HEADER + "/old,/new,301", "/\n/old\n/keep", "/\n/new\n/keep")
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["legacy_reachable"], 3)

    def test_retained_page(self):
        self.assertTrue(audit(HEADER, "/keep", "/keep")["passed"])

    def test_missing_legacy(self):
        self.assertIn("missing_legacy", self.codes(audit(HEADER, "/lost", "/")))

    def test_orphan_target_even_unused_rule(self):
        self.assertIn("missing_target", self.codes(audit(HEADER + "/a,/gone,301", "/", "/")))

    def test_chain_budget(self):
        plan = HEADER + "/a,/b,301\n/b,/c,308"
        self.assertIn("chain_budget", self.codes(audit(plan, "/a", "/c")))
        self.assertTrue(audit(plan, "/a", "/c", max_hops=2)["passed"])

    def test_temporary_any_hop(self):
        plan = HEADER + "/a,/b,301\n/b,/c,307"
        self.assertIn("temporary_redirect", self.codes(audit(plan, "/a", "/c", max_hops=2)))

    def test_self_cycle(self):
        self.assertIn("cycle", self.codes(audit(HEADER + "/a,/a,301", "/a", "/")))

    def test_cycle_and_inbound(self):
        report = audit(HEADER + "/a,/b,301\n/b,/a,308\n/x,/a,301", "/x", "/")
        self.assertEqual(report["summary"]["findings_by_code"]["cycle"], 3)
        self.assertEqual(report["summary"]["legacy_reachable"], 0)

    def test_duplicates_never_choose_first(self):
        report = audit(HEADER + "/a,/b,301\n/a,/c,301\n/x,/a,301", "/x", "/b\n/c")
        self.assertEqual(report["summary"]["findings_by_code"]["ambiguous_source"], 2)
        self.assertIn("duplicate_source", self.codes(report))
        self.assertEqual(report["findings"][0]["duplicate_rows"], [2, 3])

    def test_identical_duplicate_still_fails(self):
        self.assertFalse(audit(HEADER + "/a,/b,301\n/a,/b,301", "/a", "/b")["passed"])

    def test_live_page_shadowed(self):
        self.assertIn("live_shadowed", self.codes(audit(HEADER + "/a,/b,301", "/a", "/a\n/b")))

    def test_percent_unreserved_and_case(self):
        self.assertEqual(canonical_path("/%61/%7e/%c3%a9"), "/a/~/%C3%A9")
        self.assertTrue(audit(HEADER + "/%61,/%62,301", "/a", "/b")["passed"])

    def test_case_sensitive_paths(self):
        self.assertIn("missing_legacy", self.codes(audit(HEADER + "/a,/b,301", "/A", "/b")))

    def test_encoded_duplicate(self):
        self.assertIn(
            "duplicate_source", self.codes(audit(HEADER + "/a,/b,301\n/%61,/b,301", "/a", "/b"))
        )

    def test_reject_ambiguous_and_unsupported_paths(self):
        for path in (
            "https://example.org/a",
            "//a",
            "/a//b",
            "/a?b",
            "/a#b",
            "/a\\b",
            "/a/../b",
            "/%2e/b",
            "/%2F",
            "/%5c",
            "/%00",
            "/%7f",
            "/%25",
            "/%ff",
            "/%",
            "/%xz",
            "/a b",
            "/a*",
            "/a[0]",
            "/é",
            "/a\nb",
            " /a",
            "/a ",
        ):
            with self.subTest(path=path), self.assertRaises(InputError):
                canonical_path(path)

    def test_csv_quotes(self):
        report = audit(HEADER + '"/a,b","/c,d",301\r\n', "/a,b", "/c,d")
        self.assertTrue(report["passed"])

    def test_csv_invalid(self):
        for text in (
            "",
            "from,to,status\n",
            HEADER + "/a,/b,200",
            HEADER + "/a,/b,0301",
            HEADER + "/a,/b",
            HEADER + "/a,/b,301,extra",
            HEADER + '"/a,/b,301',
        ):
            with self.subTest(text=text), self.assertRaises(InputError):
                parse_plan(text)

    def test_catalog_strict_duplicates(self):
        for text in ("/a\n/a", "/a\n/%61"):
            with self.assertRaises(InputError):
                parse_catalog(text)

    def test_empty_catalogs(self):
        self.assertTrue(audit(HEADER, "", "")["passed"])

    def test_comments_and_blank_rows(self):
        self.assertTrue(audit(HEADER + "\n/a,/b,301\n", "# catalog\n/a\n\n", "# new\n/b")["passed"])

    def test_sample_truncation_keeps_counts(self):
        report = audit(HEADER, "/a\n/b\n/c", "/", sample_limit=1)
        self.assertEqual(report["summary"]["failed_paths"], 3)
        self.assertEqual(len(report["findings"]), 1)
        self.assertTrue(report["truncated"])
        zero = audit(HEADER, "/a", "/", sample_limit=0)
        self.assertFalse(zero["passed"])
        self.assertEqual(zero["findings"], [])

    def test_walk_limit(self):
        plan = HEADER + "\n".join(f"/p{i},/p{i + 1},301" for i in range(258))
        report = audit(plan, "/p0", "/p258", max_hops=256, sample_limit=1)
        self.assertIn("walk_limit", self.codes(report))
        self.assertTrue(report["findings"][0]["chain_truncated"])

    def test_options_strict(self):
        for options in (
            {"max_hops": -1},
            {"max_hops": 257},
            {"max_hops": True},
            {"sample_limit": -1},
            {"sample_limit": 1001},
        ):
            with self.assertRaises(InputError):
                audit(HEADER, "", "", **options)

    def test_long_input_rejected(self):
        with self.assertRaises(InputError):
            parse_catalog("#" * (4 * 1024 * 1024 + 1))
        with self.assertRaises(InputError):
            canonical_path("/" + "a" * 2048)

    def test_random_graph_oracle(self):
        rng = random.Random(721)
        for _ in range(100):
            targets = {f"/p{i}": f"/p{rng.randrange(12)}" for i in range(8)}
            plan = HEADER + "\n".join(
                f"{source},{target},301" for source, target in targets.items()
            )
            expected = 0
            for source in targets:
                visited = set()
                current = source
                while current in targets and current not in visited:
                    visited.add(current)
                    current = targets[current]
                if current not in {"/p8", "/p9", "/p10", "/p11"}:
                    expected += 1
            report = audit(plan, "", "/p8\n/p9\n/p10\n/p11", max_hops=256)
            self.assertEqual(report["summary"]["failed_paths"], expected)

    def test_cli_real_process_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, old, live = (root / name for name in ("plan.csv", "old.txt", "live.txt"))
            plan.write_text(HEADER + "/a,/b,301", encoding="utf-8")
            old.write_bytes(b"\xef\xbb\xbf/a\r\n")
            live.write_text("/b", encoding="utf-8")
            self.assertEqual(read_text(old), "/a\r\n")
            inputs = {p: p.read_bytes() for p in (plan, old, live)}
            command = [
                sys.executable,
                "-m",
                "redirect_catalog",
                str(plan),
                "--old",
                str(old),
                "--live",
                str(live),
                "--json",
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["passed"])
            self.assertEqual({p: p.read_bytes() for p in inputs}, inputs)
            live.write_text("/", encoding="utf-8")
            self.assertEqual(
                subprocess.run(command, capture_output=True, check=False).returncode, 1
            )
            plan.write_text(HEADER + "/a,/b,200", encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
