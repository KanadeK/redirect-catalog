# redirect-catalog

Check that a website migration preserves the paths you intended to preserve.
Reconcile a redirect CSV with an old path catalog and a catalog of pages in the
new build, entirely offline.

A redirect map can have no loops and still point to a missing new page.
An old path can disappear without ever appearing in the map. This tool checks
both, along with duplicate sources, live pages shadowed by rules, long chains
and temporary redirects.

Python 3.11+, standard library only, MIT. Alpha 0.1.0.

## Install and run

    git clone https://github.com/KanadeK/redirect-catalog.git
    cd redirect-catalog
    python -m venv .venv

Activate with "source .venv/bin/activate" on POSIX, or
".venv\Scripts\Activate.ps1" in PowerShell:

    python -m pip install .
    redirect-catalog examples/good.csv --old examples/old.txt --live examples/live.txt --json
    redirect-catalog examples/broken.csv --old examples/old.txt --live examples/live.txt --json
    python examples/demo.py

The good map exits 0. The broken map exits 1: /guide-old points to a missing
page and /news-old is not accounted for. The demo checks both outcomes and exits 0.

For a real migration, create these three files from your build/CMS exports:

    source,target,status
    /guide-old,/guide,301
    /news-old,/news,308

    # old.txt: one previously public path per line
    /
    /guide-old
    /news-old
    /keep

    # live.txt: pages that will exist in the new build
    /
    /guide
    /news
    /keep

Then:

    redirect-catalog redirects.csv --old old.txt --live live.txt --json

Header must be exactly source,target,status. Status accepts 301, 302, 307 or
308; this migration profile flags every 302/307 as temporary. Catalogs use one
path per line, with blank lines and full-line # comments. UTF-8 BOM and CRLF
are supported. Duplicate catalog paths are input errors. Duplicate rule sources
are reported as ambiguous, even when the destinations are identical.

## Results

Exit 0 means all checks pass; 1 means a plan finding; 2 means malformed input,
unsupported syntax, read failure or invalid option. Input errors go to stderr
as JSON; the report goes to stdout. Both text and JSON output escape untrusted
strings. Save reports by redirecting stdout; the shell controls overwriting.

Findings:

| Code | Meaning |
|---|---|
| missing_legacy | An old path is neither live nor redirected |
| missing_target | A rule terminates outside the live catalog |
| duplicate_source | Multiple rules define the same normalized source |
| ambiguous_source | Resolution reaches a duplicate source; no rule is chosen |
| live_shadowed | A redirect replaces a path listed as a new live page |
| cycle | Resolution returns to a previously visited path |
| chain_budget | Redirect count exceeds the chosen limit |
| temporary_redirect | A resolved edge uses 302 or 307 |
| walk_limit | Resolution requires more than 256 redirects |

Every old path and every rule source is checked. Thus an unused rule with an
orphan target also fails. Retained old pages need no redirect. A destination
listed as live still has its redirect applied if one is defined, producing a
shadowing finding. A missing target is only a catalog assertion, not an HTTP 404.

Default maximum is one redirect. Use "--max-hops 2" to accept two permanent
hops, or 0 to forbid redirects. Values through 256 are supported; the fixed
256-edge traversal guard is independent of policy. Beyond it, resolution fails
explicitly instead of being assumed valid.

Summary counts cover all paths. Default output includes the first 100 failed
path samples, sorted by source. "--sample-limit 0" emits counts only; the
maximum is 1,000. Each chain sample has at most 33 paths; truncation is explicit.
Duplicate row samples contain up to 20 physical CSV end-line numbers.
"legacy_reachable" counts old paths that terminate in the live catalog, even
when their route also fails a chain or temporary-redirect policy.

## Exact path model and limits

This is a conservative, single-origin, case-sensitive exact-path model:

- Inputs begin with a single / and contain ASCII URL path characters.
  Encode Unicode as UTF-8 percent escapes.
- Percent hex is uppercased; encoded unreserved characters are decoded.
  Thus /%61 and /a are one path.
- Query strings, fragments, full URLs, regex/wildcards, repeated slashes,
  dot segments, raw spaces and raw Unicode are unsupported.
- Encoded slash, backslash, control bytes and percent signs are rejected.
  No double decoding; no automatic slash, case or Unicode normalization.
- Paths are at most 2,048 characters. Each input is at most 4 MiB, with at
  most 100,000 catalog paths or CSV rules.

These rules are not a simulation of nginx, Apache, a CDN, filesystem routing,
browser canonicalization or application middleware. Inventories must describe
your intended exact matching behavior. The tool cannot infer server precedence,
check live status codes, inspect page contents, prove SEO outcomes or discover
missing paths absent from your old inventory. No XML sitemap/config parser is
included; export the path list explicitly.

[bulk-url-checker](https://github.com/phauer/bulk-url-checker) and crawlers are
better for deployed HTTP checks. Browser redirect-map validators already find
loops/chains; this tool adds old/live catalog reconciliation and a local CI
report. It makes no network requests or changes to inputs or web configuration.
Reports include paths; keep private site structures private. Budgets are not
hard OS CPU/memory isolation.

## Development and removal

See CONTRIBUTING.md. Tests cover complete and broken migrations, percent-path
collisions, ambiguous sources, cycles, bounded walks, a seeded graph oracle and
real installed CLI behavior. CI builds and tests the wheel on Linux, Windows
and macOS, with Python 3.11 and 3.14.

    python -m pip uninstall redirect-catalog

Delete the clone/virtual environment when finished. There is no persistent
state, cache, server or scheduled job.

## 中文说明

将重定向 CSV、旧页面路径清单和新版本实际页面清单一起核对，发现遗漏的旧路径、
不存在的最终目标、循环、重复来源、页面被重定向覆盖、超长链和临时跳转。适合在
网站迁移发布前接入 CI，无需部署或联网。按上方步骤安装并运行演示。
仅支持单站点精确路径，不能模拟真实 Web 服务器或证明线上 HTTP 状态正确。
