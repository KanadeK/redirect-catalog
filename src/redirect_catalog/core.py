"""Offline, exact-path reconciliation of a website migration plan."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes

MAX_BYTES = 4 * 1024 * 1024
MAX_ITEMS = 100_000
WALK_LIMIT = 256
SAFE = re.compile(r"/[A-Za-z0-9._~!$&'()+,;=:@%/-]*\Z")
UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class InputError(ValueError):
    """Unsupported syntax or a documented resource limit."""


def read_text(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise InputError("input exceeds 4 MiB")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("input must be UTF-8") from exc


def _size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise InputError("input exceeds 4 MiB")


def canonical_path(value: str) -> str:
    if not 1 <= len(value) <= 2048 or not SAFE.fullmatch(value) or "//" in value:
        raise InputError("expected a single-origin exact ASCII path, at most 2048 characters")
    output = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "%":
            output.append(char)
            index += 1
            continue
        code = value[index + 1 : index + 3]
        if len(code) != 2 or not re.fullmatch(r"[0-9a-fA-F]{2}", code):
            raise InputError("invalid percent escape")
        byte = int(code, 16)
        if byte < 32 or byte == 127 or byte in (ord("/"), ord("\\"), ord("%")):
            raise InputError("encoded controls, separators and percent signs are unsupported")
        output.append(chr(byte) if chr(byte) in UNRESERVED else "%" + code.upper())
        index += 3
    normalized = "".join(output)
    if any(part in {".", ".."} for part in normalized.split("/")):
        raise InputError("dot segments are unsupported")
    try:
        unquote_to_bytes(normalized).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("percent-encoded path bytes must be UTF-8") from exc
    return normalized


def parse_catalog(text: str) -> set[str]:
    _size(text)
    result: set[str] = set()
    entries = 0
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.startswith("#"):
            continue
        entries += 1
        if entries > MAX_ITEMS:
            raise InputError("catalog exceeds 100000 paths")
        try:
            path = canonical_path(raw)
        except InputError as exc:
            raise InputError(f"catalog line {number}: {exc}") from exc
        if path in result:
            raise InputError(f"duplicate catalog path at line {number}")
        result.add(path)
    return result


@dataclass(frozen=True)
class Rule:
    source: str
    target: str
    status: int
    row: int


def parse_plan(text: str) -> list[Rule]:
    _size(text)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    result = []
    try:
        if next(reader, None) != ["source", "target", "status"]:
            raise InputError("CSV header must be exactly source,target,status")
        for row in reader:
            if not row:
                continue
            if len(result) >= MAX_ITEMS:
                raise InputError("plan exceeds 100000 rules")
            if len(row) != 3 or row[2] not in {"301", "302", "307", "308"}:
                raise InputError(f"invalid column count or status at CSV line {reader.line_num}")
            try:
                source, target = canonical_path(row[0]), canonical_path(row[1])
            except InputError as exc:
                raise InputError(f"CSV line {reader.line_num}: {exc}") from exc
            result.append(Rule(source, target, int(row[2]), reader.line_num))
    except csv.Error as exc:
        raise InputError(f"malformed CSV near line {reader.line_num}") from exc
    return result


def _resolve(source: str, rules: dict[str, Rule], conflicts: set[str]) -> dict[str, Any]:
    path = source
    seen: set[str] = set()
    chain = []
    hops = 0
    temporary = False
    while True:
        if len(chain) < 33:
            chain.append(path)
        if path in conflicts:
            outcome = "ambiguous_source"
            break
        if path in seen:
            outcome = "cycle"
            break
        if path not in rules:
            outcome = "terminal"
            break
        if hops == WALK_LIMIT:
            outcome = "walk_limit"
            break
        seen.add(path)
        rule = rules[path]
        temporary |= rule.status in (302, 307)
        path = rule.target
        hops += 1
    return {
        "outcome": outcome,
        "terminal": path,
        "hops": hops,
        "temporary": temporary,
        "chain": chain,
        "chain_truncated": hops + 1 > len(chain),
    }


def audit(
    plan_text: str,
    old_text: str,
    live_text: str,
    *,
    max_hops: int = 1,
    sample_limit: int = 100,
) -> dict[str, Any]:
    if type(max_hops) is not int or not 0 <= max_hops <= WALK_LIMIT:
        raise InputError("max_hops must be in 0..256")
    if type(sample_limit) is not int or not 0 <= sample_limit <= 1000:
        raise InputError("sample_limit must be in 0..1000")
    rows = parse_plan(plan_text)
    old, live = parse_catalog(old_text), parse_catalog(live_text)
    grouped: dict[str, list[Rule]] = {}
    for rule in rows:
        grouped.setdefault(rule.source, []).append(rule)
    conflicts = {path for path, group in grouped.items() if len(group) > 1}
    rules = {path: group[0] for path, group in grouped.items() if path not in conflicts}
    counts: Counter[str] = Counter()
    findings = []
    failed = 0
    legacy_reachable = 0
    checked = old | set(grouped)
    for source in sorted(checked):
        result = _resolve(source, rules, conflicts)
        codes = []
        if source in conflicts:
            codes.append("duplicate_source")
        if source in live and source in grouped:
            codes.append("live_shadowed")
        if result["outcome"] != "terminal":
            codes.append(result["outcome"])
        elif result["terminal"] not in live:
            codes.append("missing_legacy" if result["hops"] == 0 else "missing_target")
        elif source in old:
            legacy_reachable += 1
        if result["hops"] > max_hops:
            codes.append("chain_budget")
        if result["temporary"]:
            codes.append("temporary_redirect")
        if codes:
            failed += 1
            counts.update(codes)
            if len(findings) < sample_limit:
                finding = {"source": source, "codes": codes, **result}
                if source in conflicts:
                    finding["duplicate_rows"] = [rule.row for rule in grouped[source][:20]]
                    finding["duplicate_count"] = len(grouped[source])
                findings.append(finding)
    return {
        "version": 1,
        "passed": failed == 0,
        "summary": {
            "rules": len(rows),
            "old_paths": len(old),
            "live_paths": len(live),
            "checked_paths": len(checked),
            "legacy_reachable": legacy_reachable,
            "failed_paths": failed,
            "findings_by_code": dict(sorted(counts.items())),
        },
        "policy": {"max_hops": max_hops, "walk_limit": WALK_LIMIT, "sample_limit": sample_limit},
        "findings": findings,
        "truncated": failed > len(findings),
    }
