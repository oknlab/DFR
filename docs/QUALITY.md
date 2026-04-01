# Quality Gates

This project targets the following baseline checks:

1. `pytest -q`
2. `python -m pip install -e .[test]` on Python 3.11+
3. CI matrix on Python 3.11 and 3.12 (`.github/workflows/ci.yml`)

Future gates:
- mypy/pyright strict typing pass
- ruff linting and formatting checks
- Django integration test matrix
