#!/usr/bin/env python3
"""Universal Keyboard за Linux (X11) - пиши на английска подредба, а българските
думи, написани на латиница (towa, kakvo, 6te, bylgarski ...), стават на кирилица
автоматично след интервал или Enter (Tab не преобразува).
След Enter новият ред започва начисто.

Не работи в терминали (qterminal, xterm, konsole, gnome-terminal ...) и не пипа
нищо в поле за парола (когато програмата съобщава, че е поле за парола).
Работи само когато е избрана английската подредба.

Горещи клавиши:
  Ctrl+Space  - обърни последната дума (кирилица <-> латиница) и я запомни
  Ctrl+Alt+K  - пауза / пусни

Стартиране:  ./start.sh                                   (икона в панела)
             python3 universal_keyboard_linux.py --debug  (лог на решенията в конзолата)

Само X11 (не Wayland). Не трябва нищо за инсталиране: ползва libX11, libXtst, libXi
и (за иконата и полетата за парола) python3-gi, които ги има в Ubuntu.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import fcntl
import os
import queue
import re
import select
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uk.engine import SENTENCE_END, Context, Engine, default_user_file  # noqa: E402

DEBUG = "--debug" in sys.argv
# --test: also react to synthetic (XTEST) keys, so test_linux.py can type for real.
TEST = "--test" in sys.argv
APPDIR = os.path.dirname(default_user_file())
os.makedirs(APPDIR, exist_ok=True)
LOGFILE = os.path.join(APPDIR, "log.txt")


def log(*a) -> None:
    msg = " ".join(str(x) for x in a)
    if DEBUG:
        try:
            print(msg, flush=True)
        except Exception:
            pass
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def debug_console(*a) -> None:
    """Only with --debug, only on the screen. Typed words never go to a file."""
    if DEBUG:
        try:
            print(" ".join(str(x) for x in a), flush=True)
        except Exception:
            pass


# ------------------------------------------------------------------ X11 via ctypes
def _lib(name: str):
    path = ctypes.util.find_library(name)
    if not path:
        raise OSError(f"lib{name} не е намерена")
    return ctypes.CDLL(path)


x11 = _lib("X11")
xtst = _lib("Xtst")
xi = _lib("Xi")

c_int, c_uint, c_ulong, c_long = ctypes.c_int, ctypes.c_uint, ctypes.c_ulong, ctypes.c_long
c_void_p, c_char_p, c_ubyte = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ubyte
POINTER, byref = ctypes.POINTER, ctypes.byref


class XKeyEvent(ctypes.Structure):
    _fields_ = [("type", c_int), ("serial", c_ulong), ("send_event", c_int), ("display", c_void_p),
                ("window", c_ulong), ("root", c_ulong), ("subwindow", c_ulong), ("time", c_ulong),
                ("x", c_int), ("y", c_int), ("x_root", c_int), ("y_root", c_int),
                ("state", c_uint), ("keycode", c_uint), ("same_screen", c_int)]


class XGenericEventCookie(ctypes.Structure):
    _fields_ = [("type", c_int), ("serial", c_ulong), ("send_event", c_int), ("display", c_void_p),
                ("extension", c_int), ("evtype", c_int), ("cookie", c_uint), ("data", c_void_p)]


class XEvent(ctypes.Union):
    _fields_ = [("type", c_int), ("xkey", XKeyEvent), ("xcookie", XGenericEventCookie),
                ("pad", c_long * 24)]


class XIValuatorState(ctypes.Structure):
    _fields_ = [("mask_len", c_int), ("mask", POINTER(c_ubyte)), ("values", POINTER(ctypes.c_double))]


class XIRawEvent(ctypes.Structure):
    _fields_ = [("type", c_int), ("serial", c_ulong), ("send_event", c_int), ("display", c_void_p),
                ("extension", c_int), ("evtype", c_int), ("time", c_ulong), ("deviceid", c_int),
                ("sourceid", c_int), ("detail", c_int), ("flags", c_int),
                ("valuators", XIValuatorState), ("raw_values", POINTER(ctypes.c_double))]


class XIEventMask(ctypes.Structure):
    _fields_ = [("deviceid", c_int), ("mask_len", c_int), ("mask", POINTER(c_ubyte))]


class XIDeviceInfo(ctypes.Structure):
    _fields_ = [("deviceid", c_int), ("name", c_char_p), ("use", c_int), ("attachment", c_int),
                ("enabled", c_int), ("num_classes", c_int), ("classes", c_void_p)]


class XClassHint(ctypes.Structure):
    _fields_ = [("res_name", c_void_p), ("res_class", c_void_p)]


class XkbStateRec(ctypes.Structure):
    _fields_ = [("group", c_ubyte), ("locked_group", c_ubyte), ("base_group", ctypes.c_ushort),
                ("latched_group", ctypes.c_ushort), ("mods", c_ubyte), ("base_mods", c_ubyte),
                ("latched_mods", c_ubyte), ("locked_mods", c_ubyte), ("compat_state", c_ubyte),
                ("grab_mods", c_ubyte), ("compat_grab_mods", c_ubyte), ("lookup_mods", c_ubyte),
                ("compat_lookup_mods", c_ubyte), ("ptr_buttons", ctypes.c_ushort)]


class XErrorEvent(ctypes.Structure):
    _fields_ = [("type", c_int), ("display", c_void_p), ("resourceid", c_ulong), ("serial", c_ulong),
                ("error_code", c_ubyte), ("request_code", c_ubyte), ("minor_code", c_ubyte)]


ERROR_HANDLER = ctypes.CFUNCTYPE(c_int, c_void_p, POINTER(XErrorEvent))

x11.XInitThreads.restype = c_int
x11.XOpenDisplay.argtypes = [c_char_p]
x11.XOpenDisplay.restype = c_void_p
x11.XCloseDisplay.argtypes = [c_void_p]
x11.XDefaultRootWindow.argtypes = [c_void_p]
x11.XDefaultRootWindow.restype = c_ulong
x11.XConnectionNumber.argtypes = [c_void_p]
x11.XPending.argtypes = [c_void_p]
x11.XNextEvent.argtypes = [c_void_p, POINTER(XEvent)]
x11.XFlush.argtypes = [c_void_p]
x11.XSync.argtypes = [c_void_p, c_int]
x11.XBell.argtypes = [c_void_p, c_int]
x11.XFree.argtypes = [c_void_p]
x11.XQueryExtension.argtypes = [c_void_p, c_char_p, POINTER(c_int), POINTER(c_int), POINTER(c_int)]
x11.XGetEventData.argtypes = [c_void_p, POINTER(XGenericEventCookie)]
x11.XFreeEventData.argtypes = [c_void_p, POINTER(XGenericEventCookie)]
x11.XGrabKey.argtypes = [c_void_p, c_int, c_uint, c_ulong, c_int, c_int, c_int]
x11.XUngrabKey.argtypes = [c_void_p, c_int, c_uint, c_ulong]
x11.XUngrabKeyboard.argtypes = [c_void_p, c_ulong]
x11.XKeysymToKeycode.argtypes = [c_void_p, c_ulong]
x11.XKeysymToKeycode.restype = c_ubyte
x11.XkbKeycodeToKeysym.argtypes = [c_void_p, c_ubyte, c_int, c_int]
x11.XkbKeycodeToKeysym.restype = c_ulong
x11.XkbGetState.argtypes = [c_void_p, c_uint, POINTER(XkbStateRec)]
x11.XDisplayKeycodes.argtypes = [c_void_p, POINTER(c_int), POINTER(c_int)]
x11.XGetKeyboardMapping.argtypes = [c_void_p, c_ubyte, c_int, POINTER(c_int)]
x11.XGetKeyboardMapping.restype = POINTER(c_ulong)
x11.XChangeKeyboardMapping.argtypes = [c_void_p, c_int, c_int, POINTER(c_ulong), c_int]
x11.XQueryKeymap.argtypes = [c_void_p, ctypes.c_char * 32]
x11.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
x11.XInternAtom.restype = c_ulong
x11.XGetWindowProperty.argtypes = [c_void_p, c_ulong, c_ulong, c_long, c_long, c_int, c_ulong,
                                   POINTER(c_ulong), POINTER(c_int), POINTER(c_ulong),
                                   POINTER(c_ulong), POINTER(c_void_p)]
x11.XGetClassHint.argtypes = [c_void_p, c_ulong, POINTER(XClassHint)]
x11.XQueryTree.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                           POINTER(c_void_p), POINTER(c_uint)]
x11.XRefreshKeyboardMapping.argtypes = [c_void_p]
x11.XSetErrorHandler.argtypes = [ERROR_HANDLER]
x11.XSetErrorHandler.restype = c_void_p
xtst.XTestFakeKeyEvent.argtypes = [c_void_p, c_uint, c_int, c_ulong]
xi.XIQueryVersion.argtypes = [c_void_p, POINTER(c_int), POINTER(c_int)]
xi.XISelectEvents.argtypes = [c_void_p, c_ulong, POINTER(XIEventMask), c_int]
xi.XIQueryDevice.argtypes = [c_void_p, c_int, POINTER(c_int)]
xi.XIQueryDevice.restype = POINTER(XIDeviceInfo)
xi.XIFreeDeviceInfo.argtypes = [POINTER(XIDeviceInfo)]

KeyPress, GenericEvent = 2, 35
XI_RawKeyPress, XI_RawKeyRelease, XI_RawButtonPress = 13, 14, 15
XIAllDevices, XIAllMasterDevices = 0, 1
ShiftMask, LockMask, ControlMask, Mod1Mask, Mod2Mask = 1, 2, 4, 8, 16
LOCK_COMBOS = (0, LockMask, Mod2Mask, LockMask | Mod2Mask)  # Caps Lock / Num Lock on or off
GrabModeAsync = 1
XkbUseCoreKbd = 0x0100

XK = {
    "BackSpace": 0xFF08, "Tab": 0xFF09, "Return": 0xFF0D, "Escape": 0xFF1B, "Delete": 0xFFFF,
    "Home": 0xFF50, "Left": 0xFF51, "Up": 0xFF52, "Right": 0xFF53, "Down": 0xFF54,
    "Prior": 0xFF55, "Next": 0xFF56, "End": 0xFF57, "Insert": 0xFF63, "KP_Enter": 0xFF8D,
    "ISO_Left_Tab": 0xFE20, "space": 0x20, "k": 0x6B, "a": 0x61, "Shift_L": 0xFFE1,
}
MOD_SYMS = {
    0xFFE1: "shift", 0xFFE2: "shift", 0xFFE3: "ctrl", 0xFFE4: "ctrl", 0xFFE9: "alt", 0xFFEA: "alt",
    0xFFE7: "alt", 0xFFE8: "alt", 0xFFEB: "win", 0xFFEC: "win", 0xFE03: "alt", 0xFFE5: "caps",
}
NAV_SYMS = {XK[n] for n in ("Tab", "ISO_Left_Tab", "Escape", "Delete", "Home", "Left", "Up", "Right",
                            "Down", "Prior", "Next", "End", "Insert")}
NAV_SYMS |= {0xFF95, 0xFF96, 0xFF97, 0xFF98, 0xFF99, 0xFF9A, 0xFF9B, 0xFF9C, 0xFF9E, 0xFF9F}  # keypad

# word characters: letters, digits, apostrophe and the phonetic keys ` [ ] \ (+ shifted ~ { } |)
_W = r"A-Za-z0-9'`~\[\]{}\\|"
_WE = r"A-Za-z0-9`~\[\]{}\\|"
CORE_RX = re.compile(rf"^([^{_W}]*)([{_W}](?:[{_W}]*[{_WE}])?)([^{_WE}]*)$")


def split_word(word: str):
    """-> (prefix, core, suffix) or None. "[note]" style brackets are not letters."""
    m = CORE_RX.match(word)
    if not m:
        return None
    pre, core, suf = m.groups()
    if len(core) > 2 and core[0] in "[{" and core[-1] in "]}":
        pre, core, suf = pre + core[0], core[1:-1], core[-1] + suf
    return pre, core, suf


# ------------------------------------------------------------------ where are we typing?
# Terminals -> do nothing there (WM_CLASS of the window, lower case).
TERMINAL_CLASSES = {
    "qterminal", "xterm", "uxterm", "rxvt", "urxvt", "urxvt-unicode", "gnome-terminal",
    "gnome-terminal-server", "konsole", "xfce4-terminal", "lxterminal", "mate-terminal",
    "terminator", "tilix", "alacritty", "kitty", "wezterm", "org.wezfurlong.wezterm", "st",
    "st-256color", "sakura", "terminology", "guake", "tilda", "yakuake", "foot", "footclient",
    "cool-retro-term", "ghostty", "com.mitchellh.ghostty", "kgx", "org.gnome.console", "ptyxis",
    "org.gnome.ptyxis", "deepin-terminal", "io.elementary.terminal", "eterm", "aterm",
    "warp", "dev.warp.warp", "blackbox", "com.raggesilver.blackbox", "x-terminal-emulator",
}


# ------------------------------------------------------------------ password fields (AT-SPI)
class PasswordWatcher:
    """Listens to accessibility focus events (runs in the GLib main loop).

    is_password is True while a password field has the focus. Programs that do not
    report accessibility information are never seen as password fields.
    """

    def __init__(self) -> None:
        self.is_password = False
        self.ok = False
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            Atspi.init()
            self.Atspi = Atspi
            self.listener = Atspi.EventListener.new(self._on_focus)
            self.listener.register("object:state-changed:focused")
            self.ok = True
        except Exception:
            log("AT-SPI not available - password fields are not detected")

    def _on_focus(self, event) -> None:
        try:
            role = event.source.get_role()
            pw = role == self.Atspi.Role.PASSWORD_TEXT
            if event.detail1:
                self.is_password = pw
            elif pw:
                self.is_password = False
            if DEBUG:
                log("focus:", role, "-> password" if self.is_password else "")
        except Exception:
            pass


# ------------------------------------------------------------------ X side
class X:
    """Everything that talks to the X server. Used only from the keyboard thread."""

    def __init__(self) -> None:
        self.dpy = x11.XOpenDisplay(None)
        if not self.dpy:
            raise RuntimeError("Няма X11 дисплей (Wayland ли е?)")
        self.root = x11.XDefaultRootWindow(self.dpy)
        self.errors = 0
        self._err_cb = ERROR_HANDLER(self._on_error)
        x11.XSetErrorHandler(self._err_cb)
        mn, mx = c_int(), c_int()
        x11.XDisplayKeycodes(self.dpy, byref(mn), byref(mx))
        self.min_kc, self.max_kc = mn.value, mx.value
        self.atom_active = x11.XInternAtom(self.dpy, b"_NET_ACTIVE_WINDOW", 0)
        self.kc = {name: x11.XKeysymToKeycode(self.dpy, sym) for name, sym in XK.items()}
        self.xtest_ids: set[int] = set()
        self.spare: list[int] = []        # keycodes without any symbol, used to type Cyrillic
        self.spare_map: dict[str, int] = {}   # char -> spare keycode currently holding it
        self.spare_lru: list[str] = []
        self.injected = 0                 # how many of our own key presses are still on their way
        self.refresh_keymap()
        self._init_xi()

    def _on_error(self, dpy, ev) -> int:
        self.errors += 1
        if DEBUG:
            log("X error", ev.contents.error_code, "request", ev.contents.request_code)
        return 0

    # ------------------------------------------------------------ keymap
    def refresh_keymap(self) -> None:
        self.mod_of: dict[int, str] = {}
        self.nav: set[int] = set()
        self.ascii: dict[str, tuple[int, bool]] = {}
        for kc in range(self.min_kc, self.max_kc + 1):
            s0 = x11.XkbKeycodeToKeysym(self.dpy, kc, 0, 0)
            s1 = x11.XkbKeycodeToKeysym(self.dpy, kc, 0, 1)
            if s0 in MOD_SYMS:
                self.mod_of[kc] = MOD_SYMS[s0]
            if s0 in NAV_SYMS:
                self.nav.add(kc)
            for sym, shift in ((s0, False), (s1, True)):
                if 0x20 <= sym <= 0x7E and chr(sym) not in self.ascii:
                    self.ascii[chr(sym)] = (kc, shift)
        if not self.spare:
            per = c_int()
            n = self.max_kc - self.min_kc + 1
            syms = x11.XGetKeyboardMapping(self.dpy, self.min_kc, n, byref(per))
            for i in range(n):
                if not any(syms[i * per.value + j] for j in range(per.value)):
                    self.spare.append(self.min_kc + i)
            x11.XFree(syms)
            self.spare = self.spare[-24:]  # keep a few free for other programs

    def restore_spare(self) -> None:
        for kc in self.spare_map.values():
            x11.XChangeKeyboardMapping(self.dpy, kc, 2, (c_ulong * 2)(0, 0), 1)
        self.spare_map.clear()
        x11.XSync(self.dpy, 0)

    def _ensure_chars(self, text: str) -> None:
        """Put every non-ASCII char of text on a spare keycode."""
        need = [c for c in dict.fromkeys(text) if c not in self.ascii and c not in self.spare_map]
        if not need:
            for c in text:
                if c in self.spare_map:
                    self.spare_lru.remove(c)
                    self.spare_lru.append(c)
            return
        free = [kc for kc in self.spare if kc not in self.spare_map.values()]
        for c in need:
            if not free:  # reuse the least recently used one that this text does not need
                old = next((o for o in self.spare_lru if o not in text), None)
                if old is None:
                    break
                self.spare_lru.remove(old)
                free.append(self.spare_map.pop(old))
            kc = free.pop(0)
            sym = ord(c) if ord(c) < 0x100 else 0x01000000 | ord(c)
            x11.XChangeKeyboardMapping(self.dpy, kc, 2, (c_ulong * 2)(sym, sym), 1)
            self.spare_map[c] = kc
            self.spare_lru.append(c)
        x11.XSync(self.dpy, 0)
        time.sleep(0.05)  # let the programs read the new keyboard map first

    # ------------------------------------------------------------ input
    def _init_xi(self) -> None:
        op, ev, err = c_int(), c_int(), c_int()
        if not x11.XQueryExtension(self.dpy, b"XInputExtension", byref(op), byref(ev), byref(err)):
            raise RuntimeError("X Input extension липсва")
        self.xi_opcode = op.value
        major, minor = c_int(2), c_int(2)
        xi.XIQueryVersion(self.dpy, byref(major), byref(minor))
        mask = (c_ubyte * 4)()
        for t in (XI_RawKeyPress, XI_RawKeyRelease, XI_RawButtonPress):
            mask[t >> 3] |= 1 << (t & 7)
        em = XIEventMask(XIAllMasterDevices, 4, mask)
        xi.XISelectEvents(self.dpy, self.root, byref(em), 1)
        n = c_int()
        info = xi.XIQueryDevice(self.dpy, XIAllDevices, byref(n))
        for i in range(n.value):
            if info[i].name and b"XTEST" in info[i].name:
                self.xtest_ids.add(info[i].deviceid)
        xi.XIFreeDeviceInfo(info)
        x11.XFlush(self.dpy)

    def grab(self, kc: int, mods: int, on: bool) -> bool:
        before = self.errors
        for lock in LOCK_COMBOS:
            if on:
                x11.XGrabKey(self.dpy, kc, mods | lock, self.root, 1, GrabModeAsync, GrabModeAsync)
            else:
                x11.XUngrabKey(self.dpy, kc, mods | lock, self.root)
        x11.XSync(self.dpy, 0)
        return self.errors == before

    def held_keys(self) -> set[int]:
        buf = (ctypes.c_char * 32)()
        x11.XQueryKeymap(self.dpy, buf)
        raw = bytes(buf)
        return {i for i in range(256) if raw[i >> 3] & (1 << (i & 7))}

    def tap(self, kc: int, shift: bool = False) -> None:
        sh = self.kc["Shift_L"]
        if shift:  # modifier presses are not counted in self.injected
            xtst.XTestFakeKeyEvent(self.dpy, sh, 1, 0)
        xtst.XTestFakeKeyEvent(self.dpy, kc, 1, 0)
        xtst.XTestFakeKeyEvent(self.dpy, kc, 0, 0)
        self.injected += 1
        if shift:
            xtst.XTestFakeKeyEvent(self.dpy, sh, 0, 0)

    def state(self) -> XkbStateRec:
        st = XkbStateRec()
        x11.XkbGetState(self.dpy, XkbUseCoreKbd, byref(st))
        return st

    def latin_layout(self) -> bool:
        """The current layout types "a" on the A key (English, not Bulgarian)."""
        return x11.XkbKeycodeToKeysym(self.dpy, self.kc["a"], self.state().group, 0) == XK["a"]

    def caps_on(self) -> bool:
        return bool(self.state().locked_mods & LockMask)

    def char_of(self, kc: int, shift: bool) -> str:
        st = self.state()
        s0 = x11.XkbKeycodeToKeysym(self.dpy, kc, st.group, 0)
        s1 = x11.XkbKeycodeToKeysym(self.dpy, kc, st.group, 1)
        level = shift
        if st.locked_mods & LockMask and 0x61 <= s0 <= 0x7A:
            level = not level
        sym = (s1 or s0) if level else s0
        return chr(sym) if 0x20 <= sym <= 0x7E else ""

    def send_replace(self, n_back: int, text: str, delim: int | None, release_mods: bool = True) -> None:
        """Backspace n_back times, type text, then tap delim (a keycode) if given."""
        held = self.held_keys()
        if release_mods:  # otherwise Backspace becomes Ctrl+Backspace etc.
            for kc in held:
                if self.mod_of.get(kc) in ("shift", "ctrl", "alt", "win"):
                    xtst.XTestFakeKeyEvent(self.dpy, kc, 0, 0)
        self._ensure_chars(text)
        caps = self.caps_on()
        for _ in range(n_back):
            self.tap(self.kc["BackSpace"])
        for c in text:
            if c in self.spare_map:
                self.tap(self.spare_map[c])
            elif c in self.ascii:
                kc, shift = self.ascii[c]
                if caps and c.isalpha():
                    shift = not shift
                self.tap(kc, shift)
        if delim is not None:
            self.tap(delim)
        x11.XSync(self.dpy, 0)

    # ------------------------------------------------------------ windows
    def active_window(self) -> int:
        typ, fmt, n, after = c_ulong(), c_int(), c_ulong(), c_ulong()
        prop = c_void_p()
        r = x11.XGetWindowProperty(self.dpy, self.root, self.atom_active, 0, 1, 0, 0, byref(typ),
                                   byref(fmt), byref(n), byref(after), byref(prop))
        win = 0
        if r == 0 and prop.value:
            if n.value:
                win = ctypes.cast(prop, POINTER(c_ulong))[0]
            x11.XFree(prop)
        return win

    def window_class(self, win: int) -> str:
        """WM_CLASS (name + class) of the window or of its first child that has one."""
        for w in self._self_and_children(win):
            hint = XClassHint()
            if x11.XGetClassHint(self.dpy, w, byref(hint)):
                parts = []
                for p in (hint.res_name, hint.res_class):
                    if p:
                        parts.append(ctypes.string_at(p).decode("utf-8", "replace"))
                        x11.XFree(p)
                if parts:
                    return " ".join(parts).lower()
        return ""

    def _self_and_children(self, win: int):
        yield win
        root, parent, kids, n = c_ulong(), c_ulong(), c_void_p(), c_uint()
        if x11.XQueryTree(self.dpy, win, byref(root), byref(parent), byref(kids), byref(n)):
            arr = ctypes.cast(kids, POINTER(c_ulong))
            children = [arr[i] for i in range(n.value)]
            if kids.value:
                x11.XFree(kids)
            yield from children


# ------------------------------------------------------------------ app
class App:
    def __init__(self) -> None:
        self.engine = Engine(default_user_file())
        self.enabled = True
        self.chunk: list[str] = []
        self.ctx = Context()
        self.last: dict | None = None
        self.win = None
        self.in_terminal = False
        self.pw: PasswordWatcher | None = None
        self.cmds: queue.Queue = queue.Queue()
        self.on_state = lambda enabled, msg: None  # set by the tray
        self.stopped = threading.Event()
        self.x: X | None = None
        self.mods: set[str] = set()
        self.mod_keys: dict[int, str] = {}

    # ------------------------------------------------------------ helpers
    def reset(self, keep_ctx: bool = True) -> None:
        self.chunk = []
        self.last = None
        if not keep_ctx:
            self.ctx.clear()

    def in_password(self) -> bool:
        return bool(self.pw and self.pw.is_password)

    def check_window(self) -> None:
        x = self.x
        win = x.active_window()
        if win != self.win:
            self.win = win
            self.reset(keep_ctx=False)
            cls = x.window_class(win) if win else ""
            self.in_terminal = any(part in TERMINAL_CLASSES for part in cls.split())
            if DEBUG:
                log("window", hex(win), repr(cls), "-> terminal, off" if self.in_terminal else "")

    def can_convert(self) -> bool:
        return (self.enabled and not self.in_terminal and self.x.latin_layout()
                and not self.in_password())

    # ------------------------------------------------------------ keyboard (seen, not swallowed)
    def on_raw_key(self, kc: int, press: bool, synthetic: bool) -> None:
        x = self.x
        mod = x.mod_of.get(kc)
        if mod:
            if press:
                self.mods.add(mod)
                self.mod_keys[kc] = mod
            else:
                self.mod_keys.pop(kc, None)
                self.mods = set(self.mod_keys.values())
            return
        if not press:
            return
        if synthetic:
            if x.injected > 0:  # one of ours
                x.injected -= 1
                return
            if not TEST:
                return
        if not self.enabled:
            return
        self.check_window()
        if self.in_terminal:  # terminal: don't touch anything
            self.reset()
            return
        ctrl, alt, win = "ctrl" in self.mods, "alt" in self.mods, "win" in self.mods
        shift = "shift" in self.mods
        if kc in (x.kc["Return"], x.kc["KP_Enter"]):
            if not (ctrl or alt or win or shift):
                return  # plain Enter is grabbed: on_grabbed_key() handles it
            self.reset(keep_ctx=False)
            return
        if kc == x.kc["space"] and ctrl and not (alt or win):
            return  # Ctrl+Space is grabbed: on_grabbed_key() handles it, keep self.last
        if ctrl or alt or win:  # shortcuts like Ctrl+C
            self.reset()
            return
        if not x.latin_layout():  # Bulgarian layout -> do nothing
            self.reset()
            return
        if kc == x.kc["BackSpace"]:
            if self.chunk:
                self.chunk.pop()
            self.last = None
            return
        if kc in x.nav:  # Tab never converts
            self.reset()
            return
        if self.in_password():  # password box: never remember or convert anything
            self.reset()
            return
        if kc == x.kc["space"]:
            # the space has already reached the window: delete it too and type it again
            self.convert_last(back_extra=1, delim=x.kc["space"])
            return
        ch = x.char_of(kc, shift)
        if ch and not ch.isspace():
            self.chunk.append(ch)
            if len(self.chunk) > 64:
                self.chunk = self.chunk[-64:]
            self.last = None

    # ------------------------------------------------------------ grabbed keys (swallowed)
    def on_grabbed_key(self, kc: int, state: int) -> None:
        x = self.x
        x11.XUngrabKeyboard(x.dpy, 0)
        x11.XFlush(x.dpy)
        if kc == x.kc["k"] and state & ControlMask and state & Mod1Mask:
            self.set_enabled(not self.enabled)
            return
        self.check_window()
        if kc in (x.kc["Return"], x.kc["KP_Enter"]):
            try:
                if self.can_convert():
                    self.convert_last(back_extra=0, delim=None)
                else:
                    self.reset()
            finally:
                self.ctx.clear()  # a new line starts with a clean context
                self.pass_through(kc, 0)
            return
        if kc == x.kc["space"] and state & ControlMask:  # Ctrl+Space
            if self.can_convert():
                self.flip()
            else:
                self.reset()
                self.pass_through(kc, ControlMask | (state & ShiftMask))

    def pass_through(self, kc: int, mods: int) -> None:
        """Give a grabbed key to the window after all."""
        x = self.x
        x.grab(kc, mods, False)
        x.tap(kc)
        x11.XSync(x.dpy, 0)
        if self.enabled:
            x.grab(kc, mods, True)

    def convert_last(self, back_extra: int, delim: int | None) -> bool:
        word = "".join(self.chunk)
        self.chunk = []
        self.last = None
        if not word:
            return False
        parts = split_word(word)
        if not parts or "@" in word or "/" in word:
            return False
        pre, core, suf = parts
        r = self.engine.analyze(core, self.ctx.value)
        if r["lang"]:
            self.ctx.push(r["lang"])
        if any(c in suf for c in SENTENCE_END):
            self.ctx.clear()
        if DEBUG:
            debug_console(f"{core!r:20} -> {r['lang']} {r['score']:6} {r['cyr']}")
        cyr_full = pre + r["cyr"] + suf
        is_space = delim is not None
        self.last = {"latin": word, "cyr": cyr_full, "core": core, "space": is_space,
                     "converted": False}
        if r["lang"] == "bg" and r["cyr"] != core:
            self.x.send_replace(len(word) + back_extra, cyr_full, delim)
            self.last["converted"] = True
            return True
        return False

    def flip(self) -> None:
        """Ctrl+Space: convert / un-convert the last word and remember it."""
        x = self.x
        if self.chunk:  # in the middle of a word -> force Bulgarian
            word = "".join(self.chunk)
            parts = split_word(word)
            if not parts:
                return
            pre, core, suf = parts
            cyr = self.engine.transliterate(core)[0]
            x.send_replace(len(word), pre + cyr + suf, None)
            self.engine.learn(core, "bg")
            self.ctx.push("bg")
            self.chunk = []
            self.last = None
            return
        last = self.last
        if not last or not last["space"]:
            x11.XBell(x.dpy, 0)
            x11.XFlush(x.dpy)
            return
        if last["converted"]:
            x.send_replace(len(last["cyr"]) + 1, last["latin"] + " ", None)
            self.engine.learn(last["core"], "en")
            self.ctx.set_last("en")
        else:
            x.send_replace(len(last["latin"]) + 1, last["cyr"] + " ", None)
            self.engine.learn(last["core"], "bg")
            self.ctx.set_last("bg")
        last["converted"] = not last["converted"]
        debug_console("learned", last["core"], self.ctx.value)

    # ------------------------------------------------------------ on / off
    def set_grabs(self, on: bool) -> None:
        x = self.x
        ok = True
        for kc in (x.kc["Return"], x.kc["KP_Enter"]):
            if kc:
                ok &= x.grab(kc, 0, on)
        ok &= x.grab(x.kc["space"], ControlMask, on)
        ok &= x.grab(x.kc["space"], ControlMask | ShiftMask, on)
        if on and not ok:
            log("some keys could not be grabbed (another program uses them?)")

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self.reset(keep_ctx=False)
        self.set_grabs(on)
        self.on_state(on, "Включена" if on else "На пауза (Ctrl+Alt+K за пускане)")
        log("enabled" if on else "paused")

    # ------------------------------------------------------------ keyboard thread
    def run_x(self, ready: threading.Event) -> None:
        try:
            self.x = x = X()
        except Exception as e:
            log("X init failed:", e)
            self.error = str(e)
            ready.set()
            return
        self.error = None
        if not x.grab(x.kc["k"], ControlMask | Mod1Mask, True):
            log("Ctrl+Alt+K is used by another program")
        self.set_grabs(True)
        ready.set()
        fd = x11.XConnectionNumber(x.dpy)
        ev = XEvent()
        try:
            while not self.stopped.is_set():
                while x11.XPending(x.dpy):
                    x11.XNextEvent(x.dpy, byref(ev))
                    try:
                        self.handle(ev)
                    except Exception:
                        log(traceback.format_exc())
                while not self.cmds.empty():
                    cmd = self.cmds.get_nowait()
                    try:
                        cmd()
                    except Exception:
                        log(traceback.format_exc())
                if not x11.XPending(x.dpy):
                    select.select([fd], [], [], 0.2)
        finally:
            try:
                x.restore_spare()
                x11.XCloseDisplay(x.dpy)
            except Exception:
                pass

    def handle(self, ev: XEvent) -> None:
        x = self.x
        if ev.type == GenericEvent and ev.xcookie.extension == x.xi_opcode:
            cookie = ev.xcookie
            if x11.XGetEventData(x.dpy, byref(cookie)):
                try:
                    raw = ctypes.cast(cookie.data, POINTER(XIRawEvent)).contents
                    synthetic = raw.sourceid in x.xtest_ids
                    if cookie.evtype in (XI_RawKeyPress, XI_RawKeyRelease):
                        self.on_raw_key(raw.detail, cookie.evtype == XI_RawKeyPress, synthetic)
                    elif cookie.evtype == XI_RawButtonPress and raw.detail in (1, 2, 3):
                        self.chunk = []  # a click moves the cursor
                        self.last = None
                finally:
                    x11.XFreeEventData(x.dpy, byref(cookie))
        elif ev.type == KeyPress:
            self.on_grabbed_key(ev.xkey.keycode, ev.xkey.state)
        elif ev.type == 34:  # MappingNotify: the keyboard map changed
            x11.XRefreshKeyboardMapping(byref(ev))
            x.refresh_keymap()


# ------------------------------------------------------------------ tray (GTK) + main
def notify(text: str) -> None:
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                      "org.freedesktop.Notifications", "Notify",
                      GLib.Variant("(susssasa{sv}i)", ("Universal Keyboard", 0, "input-keyboard",
                                                       "Universal Keyboard", text, [], {}, 3000)),
                      None, Gio.DBusCallFlags.NONE, 1000, None)
    except Exception:
        pass


def single_instance():
    f = open(os.path.join(APPDIR, "linux.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return f


def main() -> None:
    x11.XInitThreads()
    lock = single_instance()
    if lock is None:
        print("Universal Keyboard вече работи (виж иконата в панела).")
        notify("Вече работи (виж иконата в панела).")
        return
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    app = App()
    app.pw = PasswordWatcher()
    ready = threading.Event()
    t = threading.Thread(target=app.run_x, args=(ready,), daemon=True)
    t.start()
    ready.wait()
    if app.error:
        print("Грешка:", app.error)
        notify("Не може да стартира: " + app.error)
        return

    icon = Gtk.StatusIcon()

    def show(enabled: bool, msg: str | None = None) -> None:
        icon.set_from_icon_name("input-keyboard" if enabled else "media-playback-pause")
        icon.set_tooltip_text("Universal Keyboard - " + ("включена" if enabled else "на пауза"))
        if msg:
            notify(msg)

    app.on_state = lambda on, msg: GLib.idle_add(show, on, msg)
    show(True)

    def toggle(*_a) -> None:
        app.cmds.put(lambda: app.set_enabled(not app.enabled))

    def learned(*_a) -> None:
        f = default_user_file()
        if not os.path.exists(f):
            app.engine._save_user()
        subprocess.Popen(["xdg-open", f])

    def quit_(*_a) -> None:
        app.stopped.set()
        t.join(2)
        Gtk.main_quit()

    def menu(_icon, button, time_) -> None:
        m = Gtk.Menu()
        for label, cb in (("Пауза  (Ctrl+Alt+K)" if app.enabled else "Пусни  (Ctrl+Alt+K)", toggle),
                          ("Научени думи...", learned), (None, None), ("Изход", quit_)):
            item = Gtk.SeparatorMenuItem() if label is None else Gtk.MenuItem(label=label)
            if cb:
                item.connect("activate", cb)
            m.append(item)
        m.show_all()
        m.popup(None, None, None, None, button, time_)
        icon._menu = m  # keep it alive

    icon.connect("popup-menu", menu)
    icon.connect("activate", toggle)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 2, quit_)   # Ctrl+C
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, quit_)  # kill
    log("started (Linux); Ctrl+Space = обърни дума, Ctrl+Alt+K = пауза")
    notify("Работи. Пиши на латиница - българските думи стават на кирилица.")
    try:
        Gtk.main()
    except Exception:
        log(traceback.format_exc())
    finally:
        app.stopped.set()
        t.join(2)


if __name__ == "__main__":
    main()
