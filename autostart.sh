#!/bin/sh
# Добавя (или маха с --remove) Universal Keyboard в автоматичното стартиране на Linux.
#   sh autostart.sh
#   sh autostart.sh --remove
dir="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
file="$dir/universal-keyboard.desktop"
if [ "$1" = "--remove" ]; then
    rm -f "$file"
    echo "Махнато от автоматичното стартиране."
    exit 0
fi
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$dir"
cat > "$file" <<EOF
[Desktop Entry]
Type=Application
Name=Universal Keyboard
Comment=Латиница -> кирилица за българските думи
Exec=python3 "$here/universal_keyboard_linux.py"
Icon=input-keyboard
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
echo "Добавено: $file"
