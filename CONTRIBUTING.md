# Contributing

Thanks for your interest in contributing to ytb-downloader!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/lsqkk/ytb-downloader
cd ytb-downloader

# Install in editable mode
pip install -e .

# Install dev dependencies
pip install pytest pytest-cov ruff mypy bandit
```

## Running Tests

```bash
python run_tests.py
# or
python -m pytest tests/ -v
```

## Code Quality

```bash
# Lint
ruff check .

# Type check
mypy ytb_downloader/

# Security scan
bandit -r ytb_downloader/
```

## Pull Request Process

1. Ensure all tests pass
2. Add tests for new functionality
3. Update README if needed
4. Keep PRs focused on a single concern

## Commit Messages

Use conventional commits:
- `feat:` new feature
- `fix:` bug fix
- `refactor:` code restructuring
- `docs:` documentation
- `test:` testing
- `chore:` maintenance
