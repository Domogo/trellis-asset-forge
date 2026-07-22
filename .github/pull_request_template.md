## Summary

Describe the production behavior this changes.

## Verification

- [ ] Tests cover the public interface
- [ ] `uv run pytest --cov=trellis_asset_forge`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy src`
- [ ] No provider credentials or generated private artifacts are included

## Game asset impact

Note any change to manifests, topology gates, LODs, promotion output, or engine import behavior.
