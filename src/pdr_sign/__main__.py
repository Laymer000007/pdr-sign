"""Entry point: ``python -m pdr_sign [file.pdf ...]``."""

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        from pdr_sign import selftest

        return selftest.main(sys.argv[2:])

    from pdr_sign.services.instance import file_args, send_to_running

    files = file_args(sys.argv)
    if send_to_running(files):
        return 0  # the running window opens them in new tabs; Qt never loads here

    from pdr_sign.app import run

    return run(sys.argv, files)


if __name__ == "__main__":
    sys.exit(main())
