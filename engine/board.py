#!/usr/bin/env python3
"""The market board, for a cmux Dock panel.

Redraws in place off the cached file — it never touches the network itself,
so it costs nothing and cannot hang on a slow API.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402

REFRESH = 5


def main():
    sys.stdout.write("\033[?25l")            # hide the cursor; nothing types here
    try:
        while True:
            rows = render.board(render.load())
            sys.stdout.write("\033[H\033[J")  # home, then clear
            sys.stdout.write("\n".join(rows) + "\n")
            sys.stdout.flush()
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
