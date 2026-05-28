"""pytest configuration: ensure tests run from the project root."""

import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
