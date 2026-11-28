"""Windows key handling without a real keyboard: python test_windows.py

Feeds keystrokes to App.on_key() and keeps a fake text field: keys the program lets
through are typed, swallowed ones are not, and send_replace() edits the field the way
SendInput would. Checks what ends up on the screen.
"""
import importlib.machinery
import importlib.util
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
_loader = importlib.machinery.SourceFileLoader("uk_win", os.path.join(HERE, "universal_keyboard.pyw"))
_spec = importlib.util.spec_from_loader("uk_win", _loader)
ukw = importlib.util.module_from_spec(_spec)
_loader.exec_module(ukw)

screen: list[str] = []


def fake_send_replace(n_back, text, delim_vk, release_mods=True):
    for _ in range(n_back):
        if screen:
            screen.pop()
    screen.extend(text)
    if delim_vk is not None:
        screen.append(ukw.DELIMS[delim_vk])


ukw.send_replace = fake_send_replace
ukw.is_terminal = lambda hwnd: False
ukw.key_down = lambda vk: False
ukw.App.fg_layout = staticmethod(lambda: (1, 0x0409))
ukw.App.in_password = lambda self: False
ukw.App.vk_to_char = staticmethod(lambda vk, scan, hkl: KEYS[vk][1])


class FakeKb:
    def __init__(self, vk):
        self.vkCode, self.scanCode = vk, 0


# vk -> char typed on an English layout
KEYS = {ord(c.upper()): c for c in "abcdefghijklmnopqrstuvwxyz"}
KEYS.update({0xDB: "[", 0xDD: "]", 0xDC: "\\", 0xBC: ","})
KEYS = {vk: (vk, ch) for vk, ch in KEYS.items()}
BY_CHAR = {ch: vk for vk, (_, ch) in KEYS.items()}
BACK = "\b"


def type_keys(app, text):
    for ch in text:
        if ch == " ":
            vk = ukw.VK_SPACE
        elif ch == "\n":
            vk = ukw.VK_RETURN
        elif ch == BACK:
            vk = ukw.VK_BACK
        else:
            vk = BY_CHAR[ch]
        if app.on_key(FakeKb(vk)):
            continue  # swallowed
        if vk == ukw.VK_BACK:
            if screen:
                screen.pop()
        else:
            screen.append(ch)


CASES = [
    # (what is typed, what must be on the screen)
    ("byde[e ", "бъдеше "),
    # a mistake: бъдеше, wanted бъдеще. Backspace x3 (space, е, ш), then ]e and a space
    ("byde[e " + BACK * 3 + "]e ", "бъдеще "),
    # a typo in a word that stayed Latin, fixed with Backspace
    ("kaot " + BACK * 3 + "to ", "като "),
    # a comma after the word survives the edit
    ("byde[e, " + BACK * 4 + "]e, ", "бъдеще, "),
    # Backspace only removes the space, the word is joined with what follows: nothing breaks
    ("dobro " + BACK + " ", "добро "),
    # English word, Backspace, more letters: still English
    ("the " + BACK + "m ", "them "),
    # after Enter the word is not followed again: only the new letters are a word
    # (in a chat Enter sends the message, and Backspace is then somewhere else)
    ("kaot\n" + BACK * 3 + "to ", "каto "),
]

bad = 0
for typed, want in CASES:
    screen.clear()
    app = ukw.App()
    type_keys(app, typed)
    got = "".join(screen)
    ok = got == want
    bad += not ok
    shown = typed.replace(BACK, "⌫")
    print(f"{'OK ' if ok else 'ГРЕШКА'} {shown!r:32} -> {got!r}" + ("" if ok else f"   трябва {want!r}"))
print(f"\n{len(CASES) - bad}/{len(CASES)} верни")
sys.exit(1 if bad else 0)
