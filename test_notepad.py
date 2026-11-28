"""Live test on Windows: python test_notepad.py

Opens Notepad and types about 100 words in Latin, letter by letter like a person, while
Universal Keyboard is running. Then reads Notepad's text and compares it line by line.
Don't touch the keyboard or the mouse while it types (about a minute). If Notepad loses
the focus, the test stops at once, so it never types into another window.
Notepad stays open at the end: close it without saving.
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8")
user32 = ctypes.WinDLL("user32", use_last_error=True)

BACK = "\b"
# (what is typed, what must be in Notepad). Each line ends with Enter.
LINES = [
    ("zdravei, kak si dnes?", "здравей, как си днес?"),
    ("6te dojda utre sled rabota, ako ne vali.", "ще дойда утре след работа, ако не вали."),
    ("towa e mnogo hubawo mqsto za pochivka.", "това е много хубаво място за почивка."),
    ("kolata e v garaja, a boylera ne raboti.", "колата е в гаража, а бойлера не работи."),
    ("moqta priqtelka obicha da gotvi wecher.", "моята приятелка обича да готви вечер."),
    ("the meeting is at 10, ne zakysnqvai.", "the meeting is at 10, не закъснявай."),
    ("kupih si nov laptop, ama battery e slabo.", "купих си нов laptop, ама battery е слабо."),
    ("4ovek, kyde si be, ot chas te chakam!", "човек, къде си бе, от час те чакам!"),
    ("please send me the report, blagodarq mnogo.", "please send me the report, благодаря много."),
    ("dyjdyt spira li ve4e?", "дъждът спира ли вече?"),
    ("imam nujda ot pomosht s tozi bug v koda.", "имам нужда от помощ с този bug в кода."),
    ("obicham da gledam movies v petyk wecher.", "обичам да гледам movies в петък вечер."),
    ("mojesh li da mi kajesh kyde e garata?", "можеш ли да ми кажеш къде е гарата?"),
    ("I think this is a great idea, da go napravim.", "I think this is a great idea, да го направим."),
    # a wrong letter fixed with Backspace: бъдеше -> бъдеще
    ("byde[e " + BACK * 3 + "]e e nashe.", "бъдеще е наше."),
    # a typo fixed with Backspace: kaot -> като
    ("kaot " + BACK * 3 + "to vidish, kaji mi.", "като видиш, кажи ми."),
]

KEYEVENTF_KEYUP = 0x2
VK_SHIFT, VK_BACK, VK_RETURN, VK_MENU = 0x10, 0x08, 0x0D, 0x12
WM_GETTEXT, WM_GETTEXTLENGTH, WM_INPUTLANGCHANGEREQUEST = 0x0D, 0x0E, 0x50


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.GetForegroundWindow.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, ctypes.c_void_p]
user32.VkKeyScanExW.restype = ctypes.c_short


class FocusLost(Exception):
    pass


def key(vk: int, up: bool = False) -> None:
    inp = INPUT(type=1)
    inp.u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def english_layout():
    n = user32.GetKeyboardLayoutList(0, None)
    arr = (ctypes.c_void_p * n)()
    user32.GetKeyboardLayoutList(n, arr)
    for hkl in arr:
        if hkl and (hkl & 0x3FF) == 0x09:
            return hkl
    return None


def find_notepad(pid: int):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if p.value == pid and buf.value == "Notepad" and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def type_text(hwnd, hkl, text: str) -> None:
    for ch in text:
        if user32.GetForegroundWindow() != hwnd:
            raise FocusLost
        if ch == BACK:
            vk, shift = VK_BACK, False
        elif ch == "\n":
            vk, shift = VK_RETURN, False
        else:
            r = user32.VkKeyScanExW(ch, hkl)
            vk, shift = r & 0xFF, bool(r & 0x100)
        if shift:
            key(VK_SHIFT)
        key(vk)
        key(vk, up=True)
        if shift:
            key(VK_SHIFT, up=True)
        # the program converts on space and Enter: give it a moment, like a person would
        time.sleep(0.15 if ch in " \n" else 0.03)


def notepad_text(hwnd) -> str:
    edit = user32.FindWindowExW(hwnd, None, "Edit", None)
    n = user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(edit, WM_GETTEXT, n + 1, ctypes.cast(buf, ctypes.c_void_p).value)
    return buf.value


def main() -> int:
    hkl = english_layout()
    if not hkl:
        print("Няма английска подредба на клавиатурата: добави я в Windows и пусни теста пак.")
        return 2
    proc = subprocess.Popen(["notepad.exe"])
    hwnd = None
    for _ in range(50):
        time.sleep(0.1)
        hwnd = find_notepad(proc.pid)
        if hwnd:
            break
    if not hwnd:
        print("Notepad не се отвори.")
        return 2
    if user32.GetForegroundWindow() != hwnd:
        key(VK_MENU)  # Windows lets a window come forward after a key press
        key(VK_MENU, up=True)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl)  # English layout in Notepad
    time.sleep(0.5)
    if user32.GetForegroundWindow() != hwnd:
        print("Notepad не излезе отпред, нищо не е писано.")
        return 2

    words = sum(len(src.replace(BACK, "").split()) for src, _ in LINES)
    print(f"Пиша {words} думи в Notepad, не пипай клавиатурата и мишката...")
    try:
        for src, _ in LINES:
            type_text(hwnd, hkl, src + "\n")
    except FocusLost:
        print("Notepad вече не е отпред: спрях да пиша.")
        return 2
    time.sleep(0.5)

    got = notepad_text(hwnd).replace("\r\n", "\n").split("\n")
    bad = 0
    for i, (src, want) in enumerate(LINES):
        line = got[i] if i < len(got) else ""
        ok = line == want
        bad += not ok
        print(f"{'OK ' if ok else 'ГРЕШКА'} {line}" + ("" if ok else f"\n       трябва: {want}"))
    print(f"\n{len(LINES) - bad}/{len(LINES)} реда верни")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
