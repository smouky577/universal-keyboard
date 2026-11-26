#!/usr/bin/env python3
"""Test of universal_keyboard_linux.py on the real X11 desktop.

Starts the program with --test, opens its own window (text box + password box)
and types into it with fake key presses, then checks what came out.
Also types an "echo" command in qterminal and checks it was NOT converted.

Do not touch the keyboard or mouse while it runs (about 30 seconds).
The English layout must be selected.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import universal_keyboard_linux as ukl  # noqa: E402

x11, xtst = ukl.x11, ukl.xtst
x11.XInitThreads()

import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

dpy = x11.XOpenDisplay(None)
KC = {}
for kc in range(8, 256):
    for level, shift in ((0, False), (1, True)):
        s = x11.XkbKeycodeToKeysym(dpy, kc, 0, level)
        if 0x20 <= s <= 0x7E and chr(s) not in KC:
            KC[chr(s)] = (kc, shift)
SHIFT = x11.XKeysymToKeycode(dpy, 0xFFE1)
CTRL = x11.XKeysymToKeycode(dpy, 0xFFE3)
RET = x11.XKeysymToKeycode(dpy, 0xFF0D)
TAB = x11.XKeysymToKeycode(dpy, 0xFF09)


def press(kc, mods=()):
    for m in mods:
        xtst.XTestFakeKeyEvent(dpy, m, 1, 0)
    xtst.XTestFakeKeyEvent(dpy, kc, 1, 0)
    xtst.XTestFakeKeyEvent(dpy, kc, 0, 0)
    for m in reversed(mods):
        xtst.XTestFakeKeyEvent(dpy, m, 0, 0)
    x11.XFlush(dpy)


def type_text(text: str):
    for ch in text:
        if ch == "\n":
            press(RET)
            time.sleep(0.35)
            continue
        kc, shift = KC[ch]
        press(kc, (SHIFT,) if shift else ())
        time.sleep(0.25 if ch == " " else 0.06)
    time.sleep(0.2)


def call(fn):
    """Run fn in the GTK thread and return its result."""
    box = {}
    ev = threading.Event()

    def run():
        box["r"] = fn()
        ev.set()
        return False
    GLib.idle_add(run)
    ev.wait(5)
    return box.get("r")


win = Gtk.Window(title="Universal Keyboard test")
win.set_default_size(600, 300)
vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
tv = Gtk.TextView()
pw = Gtk.Entry()
pw.set_visibility(False)
vb.pack_start(tv, True, True, 0)
vb.pack_start(pw, False, False, 0)
win.add(vb)

results: list[tuple[str, str, str]] = []


def text_of_tv():
    b = tv.get_buffer()
    return b.get_text(b.get_start_iter(), b.get_end_iter(), True)


def clear_tv():
    tv.get_buffer().set_text("")


def check(name, got, want):
    results.append((name, got, want))
    print(("OK  " if got == want else "BAD ") + name, repr(got), "" if got == want else f"(want {want!r})",
          flush=True)


def focus(widget):
    def f():
        win.present_with_time(x11.CurrentTime if hasattr(x11, "CurrentTime") else 0)
        widget.grab_focus()
    call(f)
    time.sleep(0.5)


def driver():
    time.sleep(1.5)
    focus(tv)
    cases = [
        ("bg words", "kakvo pravish ", "какво правиш "),
        ("en words", "hello my friend ", "hello my friend "),
        ("c = ch, enter", "grycki ezik\n", "гръцки език\n"),
        ("mixed", "this is so cool, da go napravim li ", "this is so cool, да го направим ли "),
        ("phonetic keys", "[kola i ]e ", "школа и ще "),
        ("capital", "Kakvo stava ", "Какво става "),
    ]
    for name, typed, want in cases:
        call(clear_tv)
        time.sleep(0.2)
        type_text(typed)
        check(name, call(text_of_tv), want)

    # Ctrl+Space flips the last word back
    call(clear_tv)
    time.sleep(0.2)
    type_text("towa ")
    press(KC[" "][0], (CTRL,))
    time.sleep(0.4)
    check("ctrl+space", call(text_of_tv), "towa ")
    press(KC[" "][0], (CTRL,))
    time.sleep(0.4)
    check("ctrl+space again", call(text_of_tv), "това ")

    # Tab does not convert
    call(clear_tv)
    time.sleep(0.2)
    type_text("ivan")
    press(TAB)
    time.sleep(0.3)
    check("tab", call(text_of_tv).rstrip("\t"), "ivan")

    # password box
    focus(pw)
    type_text("kakvo stava ")
    check("password box", call(pw.get_text), "kakvo stava ")

    # terminal
    out = os.path.join(tempfile.mkdtemp(), "out.txt")
    term = subprocess.Popen(["qterminal"])
    time.sleep(3)
    type_text(f"echo kakvo pravish > {out}\n")
    time.sleep(1)
    got = open(out, encoding="utf-8").read() if os.path.exists(out) else "(no file)"
    check("terminal", got, "kakvo pravish\n")
    type_text("exit\n")
    time.sleep(0.5)
    term.terminate()
    GLib.idle_add(Gtk.main_quit)


x11.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
st = ukl.XkbStateRec()
x11.XkbGetState(dpy, ukl.XkbUseCoreKbd, ctypes.byref(st))
old_group = st.locked_group
x11.XkbLockGroup(dpy, ukl.XkbUseCoreKbd, 0)  # English layout for the test
x11.XSync(dpy, 0)

win.show_all()
data = tempfile.mkdtemp()
env = dict(os.environ, XDG_CONFIG_HOME=data)  # fresh learned words, real ones untouched
prog = subprocess.Popen([sys.executable, os.path.join(HERE, "universal_keyboard_linux.py"), "--test",
                         "--debug"], env=env)
threading.Thread(target=driver, daemon=True).start()
try:
    Gtk.main()
finally:
    prog.terminate()
    prog.wait(3)
    x11.XkbLockGroup(dpy, ukl.XkbUseCoreKbd, old_group)  # back to the layout from before
    x11.XSync(dpy, 0)
bad = [r for r in results if r[1] != r[2]]
print(f"\n{len(results) - len(bad)}/{len(results)} OK")
sys.exit(1 if bad else 0)
