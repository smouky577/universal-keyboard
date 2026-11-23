"""Universal Keyboard - пиши на английска подредба, а българските думи,
написани на латиница (towa, kakvo, 6te, bylgarski ...), стават на кирилица
автоматично след интервал / Enter.

Горещи клавиши:
  Ctrl+Space  - обърни последната дума (кирилица <-> латиница) и я запомни
  Ctrl+Alt+K        - пауза / пусни

Стартиране:  pythonw universal_keyboard.pyw      (без прозорец, икона в трея)
             python  universal_keyboard.pyw --debug  (с конзола и лог на решенията)
"""
from __future__ import annotations

import ctypes
import os
import re
import sys
import traceback
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uk.engine import Engine, default_user_file  # noqa: E402

DEBUG = "--debug" in sys.argv
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


# ------------------------------------------------------------------ Win32 API
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.ToUnicodeEx.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_ubyte),
                               wintypes.LPWSTR, ctypes.c_int, wintypes.UINT, ctypes.c_void_p]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetKeyState.restype = ctypes.c_short
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ULONG_PTR, wintypes.LPCWSTR]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.GetDC.restype = wintypes.HDC
user32.CreateIconIndirect.restype = wintypes.HICON
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                             ctypes.POINTER(wintypes.RECT), wintypes.UINT]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
gdi32.CreateBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.CreateFontW.restype = wintypes.HFONT
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.restype = wintypes.HANDLE

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_KEYDOWN, WM_SYSKEYDOWN = 0x100, 0x104
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN = 0x201, 0x204, 0x207
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x2, 0x4
VK_BACK, VK_TAB, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU = 0x08, 0x09, 0x0D, 0x10, 0x11, 0x12
VK_CAPITAL, VK_ESCAPE, VK_SPACE, VK_LWIN, VK_RWIN = 0x14, 0x1B, 0x20, 0x5B, 0x5C
NAV_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, VK_ESCAPE}
DELIMS = {VK_SPACE: " ", VK_RETURN: "\n", VK_TAB: "\t"}
MAGIC = 0x55B6_0001  # marks our own injected keystrokes
WM_TRAY = 0x8000 + 1
WM_COMMAND = 0x111
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 0x10

# word characters: letters, digits, apostrophe and the phonetic keys ` [ ] \ (+ shifted ~ { } |)
_W = r"A-Za-z0-9'`~\[\]{}\\|"
_WE = r"A-Za-z0-9`~\[\]{}\\|"
CORE_RX = re.compile(rf"^([^{_W}]*)([{_W}](?:[{_W}]*[{_WE}])?)([^{_WE}]*)$")
VK_OEM_3 = 0xC0  # ` ~  (dead key on US-International)


def split_word(word: str):
    """-> (prefix, core, suffix) or None. "[note]" style brackets are not letters."""
    m = CORE_RX.match(word)
    if not m:
        return None
    pre, core, suf = m.groups()
    if len(core) > 2 and core[0] in "[{" and core[-1] in "]}":
        pre, core, suf = pre + core[0], core[1:-1], core[-1] + suf
    return pre, core, suf


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


# ------------------------------------------------------------------ sending
def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, scan, flags, 0, MAGIC)
    return inp


def send_replace(n_back: int, text: str, delim_vk: int | None, release_mods: bool = True) -> None:
    seq: list[INPUT] = []
    # release held modifiers first, otherwise Backspace becomes Ctrl+Backspace etc.
    for mod in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):  # L/R Shift, Ctrl, Alt
        if release_mods and key_down(mod):
            seq.append(_key(mod, flags=KEYEVENTF_KEYUP))
    for _ in range(n_back):
        seq += [_key(VK_BACK), _key(VK_BACK, flags=KEYEVENTF_KEYUP)]
    for ch in text:
        code = ord(ch)
        seq += [_key(0, code, KEYEVENTF_UNICODE), _key(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    if delim_vk is not None:
        seq += [_key(delim_vk), _key(delim_vk, flags=KEYEVENTF_KEYUP)]
    arr = (INPUT * len(seq))(*seq)
    user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


# ------------------------------------------------------------------ app
class App:
    def __init__(self) -> None:
        self.engine = Engine(default_user_file())
        self.enabled = True
        self.chunk: list[str] = []
        self.ctx: str | None = None
        self.last: dict | None = None
        self.hwnd_fg = None
        self.tray_hwnd = None
        self._icons = {}

    # ------------------------------------------------------------ helpers
    def reset(self, keep_ctx: bool = True) -> None:
        self.chunk = []
        self.last = None
        if not keep_ctx:
            self.ctx = None

    @staticmethod
    def fg_layout():
        hwnd = user32.GetForegroundWindow()
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        return hwnd, user32.GetKeyboardLayout(tid) or 0

    @staticmethod
    def vk_to_char(vk: int, scan: int, hkl) -> str:
        state = (ctypes.c_ubyte * 256)()
        if key_down(VK_SHIFT):
            state[VK_SHIFT] = 0x80
        if user32.GetKeyState(VK_CAPITAL) & 1:
            state[VK_CAPITAL] = 0x01
        buf = ctypes.create_unicode_buffer(8)
        n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 0x4, hkl)  # 0x4: don't touch kbd state
        return buf.value[:n] if n > 0 else ""

    # ------------------------------------------------------------ keyboard
    def on_key(self, kb: KBDLLHOOKSTRUCT) -> bool:
        """Return True to swallow the key."""
        vk = kb.vkCode
        ctrl, alt, shift = key_down(VK_CONTROL), key_down(VK_MENU), key_down(VK_SHIFT)
        win = key_down(VK_LWIN) or key_down(VK_RWIN)

        if ctrl and not alt and not win and vk == VK_SPACE:  # Ctrl+Space (or Ctrl+Shift+Space)
            self.flip()
            return True
        if ctrl and alt and vk == ord("K"):
            self.set_enabled(not self.enabled)
            return True
        if not self.enabled:
            return False
        if vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_CAPITAL, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
            return False

        hwnd, hkl = self.fg_layout()
        if hwnd != self.hwnd_fg:
            self.hwnd_fg = hwnd
            self.reset(keep_ctx=False)
        if ctrl or alt or win:
            self.reset()
            return False
        if (hkl & 0x3FF) != 0x09:  # current layout is not English -> do nothing
            self.reset()
            return False

        if vk == VK_BACK:
            if self.chunk:
                self.chunk.pop()
            self.last = None
            return False
        if vk in NAV_KEYS:
            self.reset()
            return False
        if vk in DELIMS:
            return self.on_delim(vk)

        if vk == VK_OEM_3:
            # ` is a dead key on US-International (à, è ...). Type it literally so it can be "ч".
            ch = "~" if shift else "`"
            self.chunk.append(ch)
            self.last = None
            send_replace(0, ch, None, release_mods=False)
            return True

        ch = self.vk_to_char(vk, kb.scanCode, hkl)
        if ch and ch.isprintable() and not ch.isspace():
            self.chunk.append(ch)
            if len(self.chunk) > 64:
                self.chunk = self.chunk[-64:]
            self.last = None
        return False

    def on_delim(self, vk: int) -> bool:
        word = "".join(self.chunk)
        self.chunk = []
        self.last = None
        if not word:
            return False
        parts = split_word(word)
        if not parts or "@" in word or "/" in word:
            return False
        pre, core, suf = parts
        r = self.engine.analyze(core, self.ctx)
        if r["lang"]:
            self.ctx = r["lang"]
        if DEBUG:
            log(f"{core!r:20} -> {r['lang']} {r['score']:6} {r['cyr']}")
        cyr_full = pre + r["cyr"] + suf
        self.last = {"latin": word, "cyr": cyr_full, "core": core, "delim": vk,
                     "converted": False}
        if r["lang"] == "bg" and r["cyr"] != core:
            send_replace(len(word), cyr_full, vk)
            self.last["converted"] = True
            return True
        return False

    def flip(self) -> None:
        """Ctrl+Space: convert / un-convert the last word and remember it."""
        if self.chunk:  # in the middle of a word -> force Bulgarian
            word = "".join(self.chunk)
            parts = split_word(word)
            if not parts:
                return
            pre, core, suf = parts
            cyr = self.engine.transliterate(core)[0]
            send_replace(len(word), pre + cyr + suf, None)
            self.engine.learn(core, "bg")
            self.ctx = "bg"
            self.chunk = []
            self.last = None
            return
        last = self.last
        if not last or last["delim"] != VK_SPACE:
            user32.MessageBeep(0xFFFFFFFF)
            return
        if last["converted"]:
            send_replace(len(last["cyr"]) + 1, last["latin"] + " ", None)
            self.engine.learn(last["core"], "en")
            self.ctx = "en"
        else:
            send_replace(len(last["latin"]) + 1, last["cyr"] + " ", None)
            self.engine.learn(last["core"], "bg")
            self.ctx = "bg"
        last["converted"] = not last["converted"]
        log("learned", last["core"], self.ctx)

    # ------------------------------------------------------------ tray
    def make_icon(self, on: bool):
        if on in self._icons:
            return self._icons[on]
        size = 32
        sdc = user32.GetDC(None)
        dc = gdi32.CreateCompatibleDC(sdc)
        color = gdi32.CreateCompatibleBitmap(sdc, size, size)
        mask = gdi32.CreateBitmap(size, size, 1, 1, ctypes.create_string_buffer(size * size // 8))
        old = gdi32.SelectObject(dc, color)
        rect = wintypes.RECT(0, 0, size, size)
        brush = gdi32.CreateSolidBrush(0x00A05A1E if on else 0x00808080)  # BGR
        user32.FillRect(dc, ctypes.byref(rect), brush)
        gdi32.SetBkMode(dc, 1)
        gdi32.SetTextColor(dc, 0x00FFFFFF)
        font = gdi32.CreateFontW(-19, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 5, 0, "Segoe UI")
        oldf = gdi32.SelectObject(dc, font)
        user32.DrawTextW(dc, "aБ" if on else "||", -1, ctypes.byref(rect), 0x1 | 0x4 | 0x20)
        gdi32.SelectObject(dc, oldf)
        gdi32.SelectObject(dc, old)
        info = ICONINFO(True, 0, 0, mask, color)
        hicon = user32.CreateIconIndirect(ctypes.byref(info))
        for o in (font, brush, color, mask):
            gdi32.DeleteObject(o)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, sdc)
        self._icons[on] = hicon
        return hicon

    def _nid(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.tray_hwnd
        nid.uID = 1
        return nid

    def update_tray(self, balloon: str | None = None) -> None:
        if not self.tray_hwnd:
            return
        nid = self._nid()
        nid.uFlags = NIF_ICON | NIF_TIP | NIF_MESSAGE
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.make_icon(self.enabled)
        nid.szTip = "Universal Keyboard - " + ("включена" if self.enabled else "на пауза")
        if balloon:
            nid.uFlags |= NIF_INFO
            nid.szInfo = balloon
            nid.szInfoTitle = "Universal Keyboard"
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self.reset(keep_ctx=False)
        self.update_tray("Включена" if on else "На пауза (Ctrl+Alt+K за пускане)")
        log("enabled" if on else "paused")

    def wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                if lparam == 0x203:  # double click
                    self.set_enabled(not self.enabled)
                elif lparam == 0x205:  # right button up
                    self.show_menu(hwnd)
                return 0
            if msg == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            log(traceback.format_exc())
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def show_menu(self, hwnd) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0, 1, "Пауза  (Ctrl+Alt+K)" if self.enabled else "Пусни  (Ctrl+Alt+K)")
        user32.AppendMenuW(menu, 0, 2, "Научени думи...")
        user32.AppendMenuW(menu, 0x800, 0, None)  # separator
        user32.AppendMenuW(menu, 0, 3, "Изход")
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0080 | 0x0002, pt.x, pt.y, 0, hwnd, None)
        user32.DestroyMenu(menu)
        if cmd == 1:
            self.set_enabled(not self.enabled)
        elif cmd == 2:
            f = default_user_file()
            if not os.path.exists(f):
                self.engine._save_user()
            os.startfile(f)
        elif cmd == 3:
            user32.DestroyWindow(hwnd)

    def create_tray(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self.wndproc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "UniversalKeyboardTray"
        user32.RegisterClassW(ctypes.byref(wc))
        self.tray_hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "Universal Keyboard", 0,
                                                0, 0, 0, 0, None, None, hinst, None)
        nid = self._nid()
        nid.uFlags = NIF_ICON | NIF_TIP | NIF_MESSAGE
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.make_icon(True)
        nid.szTip = "Universal Keyboard - включена"
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    # ------------------------------------------------------------ run
    def run(self) -> None:
        def kb_proc(n_code, w_param, l_param):
            try:
                if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if kb.dwExtraInfo != MAGIC and self.on_key(kb):
                        return 1
            except Exception:
                log(traceback.format_exc())
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        def mouse_proc(n_code, w_param, l_param):
            if n_code == 0 and w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                self.chunk = []
                self.last = None
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._kb_proc = HOOKPROC(kb_proc)
        self._mouse_proc = HOOKPROC(mouse_proc)
        hinst = kernel32.GetModuleHandleW(None)
        kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, hinst, 0)
        ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, hinst, 0)
        if not kb_hook:
            log("SetWindowsHookEx failed", ctypes.get_last_error())
            return
        self.create_tray()
        self.update_tray("Работи. Пиши на латиница - българските думи стават на кирилица.")
        log("started; Ctrl+Space = обърни дума, Ctrl+Alt+K = пауза")

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWindowsHookEx(kb_hook)
            if ms_hook:
                user32.UnhookWindowsHookEx(ms_hook)
            if self.tray_hwnd:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))


def main() -> None:
    kernel32.CreateMutexW(None, False, "Global\\UniversalKeyboard_single_instance")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        user32.MessageBoxW(None, "Universal Keyboard вече работи (виж иконата в трея).",
                           "Universal Keyboard", 0x40)
        return
    try:
        App().run()
    except Exception:
        log(traceback.format_exc())


if __name__ == "__main__":
    main()
