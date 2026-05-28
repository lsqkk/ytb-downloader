#!/usr/bin/env python3
"""Run all tests with coverage report."""

import subprocess
import sys


def main():
    """Run pytest with options."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-v",
        "--tb=short",
    ]

    # Add coverage if pytest-cov is installed
    try:
        import pytest_cov  # noqa: F401

        cmd.extend(["--cov=ytb_downloader", "--cov-report=term-missing"])
    except ImportError:
        pass

    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
