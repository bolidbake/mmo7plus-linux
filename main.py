#!/usr/bin/env python3
"""
Mad Catz M.M.O. 7+ Linux Configurator
Launch entry point.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mmo7 import main


if __name__ == "__main__":
    main()
