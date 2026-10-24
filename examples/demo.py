"""Exercise both expected outcomes through the installed command."""

import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
for plan, expected in (("good.csv", 0), ("broken.csv", 1)):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "redirect_catalog",
            str(root / plan),
            "--old",
            str(root / "old.txt"),
            "--live",
            str(root / "live.txt"),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stderr + result.stdout
    assert json.loads(result.stdout)["passed"] == (expected == 0)
print("Verified a complete migration and detected missing legacy and target paths.")
