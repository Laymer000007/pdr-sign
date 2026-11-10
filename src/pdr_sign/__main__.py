"""Entry point: ``python -m pdr_sign [file.pdf ...]``."""

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        from pdr_sign import selftest

        return selftest.main(sys.argv[2:])

    from pdr_sign.services.instance import file_args, send_to_running, wants_new_window

    files = file_args(sys.argv)
    new_window = wants_new_window(sys.argv)
    if send_to_running(files, new_window=new_window):
        return 0  # the running instance opens them (or a window); Qt never loads here

    from pdr_sign.app import run

    return run(sys.argv, files)


if __name__ == "__main__":
    sys.exit(main())
