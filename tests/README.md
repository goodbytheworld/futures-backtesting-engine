# Tests

The test suite is split by confidence level and scope.

## Structure

- `unit/` for isolated logic, service, and UI contract tests
- `regression/` for behavioral protections that should not drift silently
- root-level test files for broader integration and invariant coverage

## Running

```bash
pytest tests/
pytest tests/unit/
pytest tests/regression/
pytest tests/unit/test_engine_regressions.py
pytest tests/test_engine_integration.py
```

## Notes

- `pyproject.toml` configures `pythonpath = ["."]` for pytest
- shared fixtures and artifact helpers live in `tests/conftest.py`
- when touching execution semantics, prefer running both focused tests and at least one broader integration/regression slice

## What To Update

Add or update tests when you change:

- order execution semantics
- portfolio accounting
- artifact contracts
- terminal UI response shapes
- strategy registration or loading behavior
