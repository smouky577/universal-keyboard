#!/bin/sh
# Starts Universal Keyboard for Linux (X11) in the background (icon in the panel)
cd "$(dirname "$0")" || exit 1
nohup python3 universal_keyboard_linux.py >/dev/null 2>&1 &
