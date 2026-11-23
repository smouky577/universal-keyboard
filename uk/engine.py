"""Engine: detects Bulgarian written in Latin letters ("shlyokavitsa" / phonetic
style like "towa", "bylgarski", "6te", "kakvo") and converts it to Cyrillic.

No external dependencies. Everything is offline.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def _load_words(name: str) -> set[str]:
    words: set[str] = set()
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for w in line.split():
                words.add(w.lower())
    return words


# ---------------------------------------------------------------- n-gram model
class CharModel:
    """Interpolated character trigram model."""

    def __init__(self) -> None:
        self.tri = defaultdict(lambda: defaultdict(int))
        self.bi = defaultdict(lambda: defaultdict(int))
        self.uni = defaultdict(int)
        self.total = 0

    def train(self, word: str, weight: int = 1) -> None:
        s = "^^" + word + "$"
        for i in range(2, len(s)):
            a, b, c = s[i - 2], s[i - 1], s[i]
            self.tri[a + b][c] += weight
            self.bi[b][c] += weight
            self.uni[c] += weight
            self.total += weight

    def finish(self) -> None:
        self.tri_tot = {k: sum(v.values()) for k, v in self.tri.items()}
        self.bi_tot = {k: sum(v.values()) for k, v in self.bi.items()}
        self.vocab = len(self.uni) + 1

    def _p(self, a: str, b: str, c: str) -> float:
        p1 = (self.uni.get(c, 0) + 0.5) / (self.total + 0.5 * self.vocab * 4)
        bt = self.bi_tot.get(b, 0)
        p2 = self.bi[b].get(c, 0) / bt if bt else 0.0
        tt = self.tri_tot.get(a + b, 0)
        p3 = self.tri[a + b].get(c, 0) / tt if tt else 0.0
        return 0.55 * p3 + 0.33 * p2 + 0.12 * p1

    def logprob(self, word: str, end: bool = True) -> float:
        s = "^^" + word + ("$" if end else "")
        lp = 0.0
        for i in range(2, len(s)):
            lp += math.log(self._p(s[i - 2], s[i - 1], s[i]))
        return lp


# ------------------------------------------------- Cyrillic -> Latin (training)
_STYLES = [
    # chat style
    dict(а="a", б="b", в="v", г="g", д="d", е="e", ж="zh", з="z", и="i", й="i", к="k", л="l",
         м="m", н="n", о="o", п="p", р="r", с="s", т="t", у="u", ф="f", х="h", ц="c", ч="ch",
         ш="sh", щ="sht", ъ="a", ь="y", ю="yu", я="ya"),
    # phonetic-keyboard style ("towa", "bylgarski", "moq")
    dict(а="a", б="b", в="w", г="g", д="d", е="e", ж="j", з="z", и="i", й="j", к="k", л="l",
         м="m", н="n", о="o", п="p", р="r", с="s", т="t", у="u", ф="f", х="h", ц="c", ч="ch",
         ш="sh", щ="sht", ъ="y", ь="x", ю="iu", я="q"),
    # digits style ("4ovek", "6te", "kude")
    dict(а="a", б="b", в="v", г="g", д="d", е="e", ж="j", з="z", и="i", й="i", к="k", л="l",
         м="m", н="n", о="o", п="p", р="r", с="s", т="t", у="u", ф="f", х="h", ц="c", ч="4",
         ш="6", щ="6t", ъ="u", ь="i", ю="iu", я="ia"),
    # pure phonetic-keyboard keys ("`", "[", "]", "\\")
    dict(а="a", б="b", в="w", г="g", д="d", е="e", ж="v", з="z", и="i", й="j", к="k", л="l",
         м="m", н="n", о="o", п="p", р="r", с="s", т="t", у="u", ф="f", х="h", ц="c", ч="`",
         ш="[", щ="]", ъ="y", ь="x", ю="\\", я="q"),
]

# Shifted symbol keys = capital letters on the phonetic keyboard
_SYM_LOWER = {"~": "`", "{": "[", "}": "]", "|": "\\"}


def _norm(word: str) -> str:
    return "".join(_SYM_LOWER.get(c, c) for c in word).lower()


def _is_upper(c: str) -> bool:
    return c.isupper() or c in _SYM_LOWER


def cyr_to_lat(word: str, style: int) -> str:
    m = _STYLES[style]
    return "".join(m.get(ch, ch) for ch in word)


# ------------------------------------------------- Latin -> Cyrillic options
# (latin chunk) -> [(cyrillic, penalty)]  penalty is a log-weight (0 = default)
_OPTS: dict[str, list[tuple[str, float]]] = {
    "sht": [("щ", 0.0), ("шт", -1.5)],
    "6t": [("щ", 0.0), ("шт", -1.5)],
    "sh": [("ш", 0.0), ("сх", -2.5)],
    "ch": [("ч", 0.0)],
    "zh": [("ж", 0.0), ("зх", -3.0)],
    "kh": [("х", 0.0), ("кх", -2.0)],
    "ts": [("тс", 0.0), ("ц", -0.8)],
    "tz": [("ц", 0.0)],
    "dzh": [("дж", 0.0)],
    "dj": [("дж", 0.0)],
    "ya": [("я", 0.0)],
    "yu": [("ю", 0.0)],
    "yo": [("йо", 0.0), ("ьо", -0.5)],
    "ia": [("ия", 0.0), ("я", -0.6)],
    "iu": [("ю", 0.0), ("ию", -0.8)],
    "ja": [("я", -0.4), ("жа", 0.0)],
    "ju": [("ю", -0.4), ("жу", 0.0)],
    "a": [("а", 0.0), ("ъ", -1.3)],
    "b": [("б", 0.0)],
    "c": [("ц", 0.0)],
    "d": [("д", 0.0)],
    "e": [("е", 0.0)],
    "f": [("ф", 0.0)],
    "g": [("г", 0.0)],
    "h": [("х", 0.0)],
    "i": [("и", 0.0), ("й", -1.0)],
    "j": [("ж", 0.0), ("й", -0.8)],
    "k": [("к", 0.0)],
    "l": [("л", 0.0)],
    "m": [("м", 0.0)],
    "n": [("н", 0.0)],
    "o": [("о", 0.0)],
    "p": [("п", 0.0)],
    "q": [("я", 0.0)],
    "r": [("р", 0.0)],
    "s": [("с", 0.0)],
    "t": [("т", 0.0)],
    "u": [("у", 0.0), ("ъ", -1.4)],
    "v": [("в", 0.0), ("ж", -1.4)],
    "w": [("в", 0.0)],
    "x": [("х", 0.0), ("ь", -1.2), ("кс", -1.5)],
    "y": [("ъ", 0.0), ("й", -0.7), ("ь", -1.5), ("и", -1.8)],
    "z": [("з", 0.0)],
    "4": [("ч", 0.0)],
    "6": [("ш", 0.0)],
    "'": [("ь", 0.0)],
    "`": [("ч", 0.0)],
    "[": [("ш", 0.0)],
    "]": [("щ", 0.0)],
    "\\": [("ю", 0.0)],
}
_MAXKEY = max(len(k) for k in _OPTS)

_BG_SUFFIXES = sorted(
    """ите ата ята ото ето ът ят та то те а я и о е ия ият ията ии ове ища ски ска ско ски
    ах ахме ахте аха ях яхме яха ям яш ем еш ете ат ят им иш ихме ихте иха ше л ла ло ли
    ам аш аме ате ва ваш ваме вате ват вам ен на но ни ия ина ен ост ството ство""".split(),
    key=len, reverse=True)
_EN_SUFFIXES = ["ings", "ing", "ies", "ied", "ers", "est", "ed", "es", "er", "ly", "s", "d"]

_LATIN_WORD = re.compile(r"^[a-z0-9'`\[\]\\]+$")


class Engine:
    def __init__(self, user_file: str | None = None) -> None:
        self.bg = _load_words("bg_words.txt")
        self.en = _load_words("en_words.txt")
        self.user_file = user_file
        self.user_bg: set[str] = set()
        self.user_en: set[str] = set()
        self._load_user()

        self.bg_stems = self._stems(self.bg, _BG_SUFFIXES)

        self.cyr_model = CharModel()
        self.bg_lat = CharModel()
        self.en_lat = CharModel()
        for w in self.bg:
            if "-" in w:
                continue
            self.cyr_model.train(w)
            for st in range(len(_STYLES)):
                self.bg_lat.train(cyr_to_lat(w, st))
        for w in self.en:
            if "'" not in w:
                self.en_lat.train(w, 3)
        self.cyr_model.finish()
        self.bg_lat.finish()
        self.en_lat.finish()

    # ---------------------------------------------------------- user learning
    def _load_user(self) -> None:
        if not self.user_file or not os.path.exists(self.user_file):
            return
        try:
            with open(self.user_file, encoding="utf-8") as f:
                d = json.load(f)
            self.user_bg = set(d.get("bg", []))
            self.user_en = set(d.get("en", []))
        except Exception:
            pass

    def _save_user(self) -> None:
        if not self.user_file:
            return
        os.makedirs(os.path.dirname(self.user_file), exist_ok=True)
        with open(self.user_file, "w", encoding="utf-8") as f:
            json.dump({"bg": sorted(self.user_bg), "en": sorted(self.user_en)}, f,
                      ensure_ascii=False, indent=1)

    def learn(self, word: str, lang: str) -> None:
        w = word.lower()
        if lang == "bg":
            self.user_en.discard(w)
            self.user_bg.add(w)
        else:
            self.user_bg.discard(w)
            self.user_en.add(w)
        self._save_user()

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _stems(words: set[str], suffixes: list[str]) -> set[str]:
        stems = set()
        for w in words:
            stems.add(w)
            for suf in suffixes:
                if w.endswith(suf) and len(w) - len(suf) >= 3:
                    stems.add(w[: -len(suf)])
        return stems

    def _bg_stem_hit(self, cyr: str) -> bool:
        if len(cyr) < 4:
            return False
        for suf in _BG_SUFFIXES:
            if cyr.endswith(suf) and len(cyr) - len(suf) >= 3:
                if cyr[: -len(suf)] in self.bg_stems:
                    return True
        return False

    def _en_known(self, w: str) -> tuple[bool, bool]:
        if w in self.en:
            return True, False
        for suf in _EN_SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                base = w[: -len(suf)]
                if base in self.en or base + "e" in self.en:
                    return False, True
                if len(base) > 3 and base[-1] == base[-2] and base[:-1] in self.en:
                    return False, True
        return False, False

    @staticmethod
    def _restore_case(src: str, out: str) -> str:
        letters = [c for c in src if c.isalpha() or c in "`[]\\" or c in _SYM_LOWER]
        if len(letters) > 1 and all(_is_upper(c) for c in letters):
            return out.upper()
        if src[:1] and _is_upper(src[0]):
            return out[:1].upper() + out[1:]
        return out

    # ------------------------------------------------------- transliteration
    def transliterate(self, word: str) -> tuple[str, bool, bool]:
        """Return (best_cyrillic, exact_dict_hit, stem_hit). Case is preserved."""
        w = _norm(word)
        n = len(w)
        beams: list[dict[str, float]] = [dict() for _ in range(n + 1)]
        beams[0][""] = 0.0
        K = 40
        for pos in range(n):
            if not beams[pos]:
                continue
            items = sorted(beams[pos].items(), key=lambda kv: kv[1], reverse=True)[:K]
            for prefix, score in items:
                matched = False
                for L in range(min(_MAXKEY, n - pos), 0, -1):
                    chunk = w[pos:pos + L]
                    opts = _OPTS.get(chunk)
                    if not opts:
                        continue
                    matched = True
                    for cyr, pen in opts:
                        new = prefix + cyr
                        sc = score + pen
                        old = beams[pos + L].get(new)
                        if old is None or sc > old:
                            beams[pos + L][new] = sc
                if not matched:  # unknown char, keep as is
                    new = prefix + w[pos]
                    beams[pos + 1][new] = max(beams[pos + 1].get(new, -1e9), score)
            # prune the next positions lightly using the model
            for nxt in range(pos + 1, min(pos + _MAXKEY, n) + 1):
                b = beams[nxt]
                if len(b) > K * 3:
                    ranked = sorted(b.items(),
                                    key=lambda kv: kv[1] + self.cyr_model.logprob(kv[0], end=False),
                                    reverse=True)[:K * 2]
                    beams[nxt] = dict(ranked)

        best, best_sc, best_exact, best_stem = w, -1e18, False, False
        for cand, pen in beams[n].items():
            exact = cand in self.bg
            stem = (not exact) and self._bg_stem_hit(cand)
            sc = pen + self.cyr_model.logprob(cand) + (8.0 if exact else 3.0 if stem else 0.0)
            if sc > best_sc:
                best, best_sc, best_exact, best_stem = cand, sc, exact, stem
        return self._restore_case(word, best), best_exact, best_stem

    # -------------------------------------------------------------- features
    _EN_FEATS = [
        (re.compile(r"th"), -2.5), (re.compile(r"wh"), -3.0), (re.compile(r"ph"), -2.0),
        (re.compile(r"qu"), -3.0), (re.compile(r"ck"), -2.5), (re.compile(r"tion"), -3.0),
        (re.compile(r"ing$"), -2.5), (re.compile(r"ough"), -3.0), (re.compile(r"gh"), -2.0),
        (re.compile(r"ee"), -1.2), (re.compile(r"oo"), -1.0), (re.compile(r"ou"), -1.2),
        (re.compile(r"ea"), -0.8), (re.compile(r"ly$"), -1.0), (re.compile(r"ed$"), -0.8),
        (re.compile(r"'"), -3.0), (re.compile(r"[aeiou]y$"), -0.8), (re.compile(r"ss$"), -1.0),
        (re.compile(r"[^aeiou]e$"), -0.3),
    ]
    _BG_FEATS = [
        (re.compile(r"[a-z][46]|[46][a-z]"), 4.0),
        (re.compile(r"[`\[\]\\]"), 5.0),
        (re.compile(r"q(?!u)"), 3.0),
        (re.compile(r"zh|sht|6t|yy|iq|yq"), 2.0),
        (re.compile(r"(ite|ata|iata|qta|ovo|ski|ska|sko|shte|ahme|ahte|ihme|ihte|yat|qt|ish|ash|iq)$"), 1.2),
        (re.compile(r"w[bcdfgklmnprstvz]|[bcdfgklmnprstz]w"), 1.5),
        (re.compile(r"[bcdfgklmnprstvz]y[bcdfgklmnprstvz]"), 0.8),
        (re.compile(r"^(v|s|k|ot|na|za|po|pri|bez|pre|raz|iz|do)[bcdfgklmnprstvz]"), 0.4),
    ]

    def _features(self, w: str) -> float:
        f = 0.0
        for rx, v in self._EN_FEATS:
            if rx.search(w):
                f += v
        for rx, v in self._BG_FEATS:
            if rx.search(w):
                f += v
        return f

    # ---------------------------------------------------------------- decide
    def analyze(self, word: str, context: str | None = None) -> dict:
        """Decide if `word` (typed in Latin) is Bulgarian.

        Returns {"lang": "bg"|"en"|None, "cyr": str, "score": float}.
        lang None means "not a word we should touch" (numbers, urls...).
        """
        w = _norm(word)
        res = {"lang": None, "cyr": word, "score": 0.0}
        if not w or not _LATIN_WORD.match(w) or not re.search(r"[a-z]", w):
            return res
        if re.search(r"[0-35789]", w):
            return res
        if w.strip("'") != w:
            return res
        # A lone capital "I" is almost always English
        if word == "I" and context != "bg":
            res["lang"] = "en"
            return res

        if w in self.user_en:
            res["lang"] = "en"
            return res
        cyr, bg_exact, bg_stem = self.transliterate(word)
        res["cyr"] = cyr
        if w in self.user_bg:
            res["lang"] = "bg"
            res["score"] = 99
            return res

        en_exact, en_stem = self._en_known(w)

        s = 0.0
        diff = self.bg_lat.logprob(w) - self.en_lat.logprob(w)
        s += max(-8.0, min(8.0, diff)) * 0.6
        s += self._features(w)
        if bg_exact:
            s += 6.0
        elif bg_stem:
            s += 2.0
        if en_exact:
            s -= 6.0
        elif en_stem:
            s -= 3.0
        if context == "bg":
            s += 1.6
        elif context == "en":
            s -= 1.6
        else:
            s -= 0.5  # slight preference to leave text untouched
        res["score"] = round(s, 2)
        res["lang"] = "bg" if s > 0 else "en"
        return res


def default_user_file() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "UniversalKeyboard", "user_words.json")
