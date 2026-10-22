"""PyInstaller entry point for the ``pdr-sign`` executable."""

import sys

from pdr_sign.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
