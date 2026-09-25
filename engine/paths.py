"""Where Phosphor reads and writes. Every path is overridable by environment.

    PHOSPHOR_CONFIG   ~/.config/phosphor        tokens.txt, location.txt, units
    PHOSPHOR_CACHE    ~/.cache/phosphor         prices, weather, Pip's mode
    PHOSPHOR_SIDEBAR  ~/.config/cmux/sidebars/phosphor.swift
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.environ.get("PHOSPHOR_CONFIG") or os.path.expanduser("~/.config/phosphor")
CACHE = os.environ.get("PHOSPHOR_CACHE") or os.path.expanduser("~/.cache/phosphor")
SIDEBAR = (os.environ.get("PHOSPHOR_SIDEBAR")
           or os.path.expanduser("~/.config/cmux/sidebars/phosphor.swift"))
TEMPLATE = os.path.join(ROOT, "cmux", "phosphor.tmpl.swift")


def config_file(name):
    """The user's copy if they made one, else the shipped default."""
    mine = os.path.join(CONFIG, name)
    return mine if os.path.exists(mine) else os.path.join(ROOT, "config", name)


def cache(*parts):
    return os.path.join(CACHE, *parts)


def setting(name, default):
    """A one-line setting file in the config dir, e.g. `units` containing `f`."""
    try:
        with open(os.path.join(CONFIG, name), encoding="utf-8") as fh:
            v = fh.read().split("#", 1)[0].strip()
            return v or default
    except OSError:
        return default
