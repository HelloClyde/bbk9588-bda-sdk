"""Compatibility entry point; use `python -m bda_packer`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bda_packer.build import *  # noqa: F401,F403
from bda_packer.build import main


if __name__ == "__main__":
    main()
