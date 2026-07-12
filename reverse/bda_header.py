"""Compatibility imports for reverse-engineering scripts."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bda_packer.header import *  # noqa: F401,F403
