# Contributing

Contributions are welcome through focused pull requests.

## Development setup

The project uses Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy src
```

Keep provider credentials out of fixtures and tests. Tests must exercise public module interfaces and use deterministic local adapters instead of contacting fal.

## Commit style

Prefer one behavioral change per commit. Use concise imperative subjects, for example:

```text
feat: catalog asset manifests
feat: submit privacy-aware fal jobs
docs: explain game topology profiles
```

