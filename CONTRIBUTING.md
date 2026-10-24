# Contributing

Use Python 3.11 or newer and a virtual environment:

    python -m pip install -r requirements-dev.txt
    python -m pip install --no-build-isolation -e .
    python -m unittest discover -s tests -v
    python -m ruff check .
    python -m ruff format --check .
    python -m build --no-isolation

Provide a minimal synthetic reproducer, expected result, Python and OS version.
Do not post private inputs or credentials. Add regression tests for behavior
changes. Runtime dependencies currently use the standard library only.
The maintainer reviews patches; no auto-merges or bot commits are configured.
