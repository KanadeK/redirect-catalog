# Design and acceptance

User: maintainer preparing an exact-path migration. Workflow: export inventories,
write CSV, audit locally/in CI, correct the plan, then test the deployed site
using an HTTP tool. This tool performs the offline stage.

Parse and canonicalize all three inputs before graph analysis. Sources with
multiple rules are ambiguous: no first/last-wins assumption. Every legacy path
and rule source is walked with a visited set and fixed edge cap. New live
inventory membership is evaluated only at a terminal; redirect sources also
listed as live produce a separate shadowing error. Output samples never change
full summary counts.

Acceptance includes retained legacy routes, complete direct permanent migration,
unmapped legacy routes, missing destination, self/multi-node cycles, incoming
paths to ambiguous/cyclic nodes, all-source validation, encoded collisions and
deterministic truncation. A seeded graph oracle independently computes terminal
reachability. Physical CSV line numbers account for quoted records.

Production code uses the Python standard library. No third-party code is
vendored. Research references: phauer/bulk-url-checker, public redirect map
validators and vectorize-io/hindsight issue 1926. This model intentionally does
not infer middleware/server semantics or test live HTTP responses.
