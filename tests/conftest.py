"""Lets the tests import the plain-Python modules in src/ (state, language, spoken_numbers, ...)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
