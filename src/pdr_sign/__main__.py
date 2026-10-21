"""Entry point: ``python -m pdr_sign [file.pdf ...]``."""

import sys


def main() -> int:
    from pdr_sign.app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
