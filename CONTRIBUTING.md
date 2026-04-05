# Contributing to EyeOnWater Integration

Thanks for your interest in contributing! Here's how to get started.

## Reporting Issues

- Search [existing issues](https://github.com/kdeyev/eyeonwater/issues) before creating a new one.
- Include your HA version, integration version, and relevant logs.
- Use the provided issue templates when possible.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/kdeyev/eyeonwater.git
   cd eyeonwater
   ```

2. Install dependencies with [Poetry](https://python-poetry.org/):
   ```bash
   poetry install
   ```

3. Run tests:
   ```bash
   poetry run pytest
   ```

4. Run linting:
   ```bash
   poetry run ruff check .
   poetry run mypy custom_components/eyeonwater
   ```

## Pull Requests

1. Fork the repo and create a branch from `master`.
2. Make your changes and add tests if applicable.
3. Ensure all tests pass and linting is clean.
4. Open a pull request with a clear description of the change.

## Code Style

- This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.
- Type hints are checked with [mypy](https://mypy-lang.org/).
- Pre-commit hooks are configured — run `pre-commit install` to enable them.
