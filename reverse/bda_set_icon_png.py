"""Compatibility entry point for the standalone packer's VX icon module."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bda_packer.vx_icon import *  # noqa: F401,F403
from bda_packer.vx_icon import main


if __name__ == "__main__":
    main()
