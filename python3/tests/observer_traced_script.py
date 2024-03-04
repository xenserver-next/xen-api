#!/usr/bin/env python3
"""A simple script to be traced by packages/observer.py as part of tests"""

import sys


class instrument_me:
    def __init__(self):
        pass

    def print(self):
        print("Hello, I am a print() in tests/observer_traced_script.py.")
        return 1


def main() -> int:
    """Main of the tested script, to be traced by packages/observer.py."""
    return instrument_me().print()


if __name__ == "__main__":
    sys.exit(main())
