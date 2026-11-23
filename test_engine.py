"""Quick check of the detector: python test_engine.py"""
import sys

from uk.engine import Engine

sys.stdout.reconfigure(encoding="utf-8")

SENTENCES = [
    "zdravei kak si kakvo pravish",
    "towa e mnogo hubawo",
    "az sym bylgarin i govorq bylgarski",
    "6te dojda utre sled rabota",
    "kude si be 4ovek",
    "Mnogo mi haresva tozi film",
    "obicham te mnogo",
    "ne znam kakvo da kaja",
    "shte se vidim dovechera",
    "hello how are you doing today",
    "I think this is a great idea",
    "please send me the report by friday",
    "the weather is nice in Sofia",
    "Can you check the server logs",
    "what time is the meeting tomorrow",
    "moq priqtelka e ot Plovdiv",
    "imam nujda ot pomosht",
    "kakwo stawa s teb",
    "dai mi telefona si",
    "otivam na more prez liatoto",
]

e = Engine()
for s in SENTENCES:
    ctx = None
    out = []
    for w in s.split():
        r = e.analyze(w, ctx)
        if r["lang"] == "bg":
            out.append(r["cyr"])
        else:
            out.append(w)
        if r["lang"]:
            ctx = r["lang"]
    print(f"{s}\n  -> {' '.join(out)}")
