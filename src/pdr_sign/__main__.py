"""Entry point: ``python -m pdr_sign [file.pdf ...]``."""

import sys


def main() -> int:
    from pdr_sign.services.instance import file_args, send_to_running

    files = file_args(sys.argv)
    if send_to_running(files):
        return 0  # the running window opens them in new tabs; Qt never loads here

    from pdr_sign.app import run

    return run(sys.argv, files)


if __name__ == "__main__":
    sys.exit(main())
