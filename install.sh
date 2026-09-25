#!/bin/sh
# Phosphor installer. See install.py for what it touches; --dry-run to preview.
exec python3 "$(cd "$(dirname "$0")" && pwd)/install.py" "$@"
