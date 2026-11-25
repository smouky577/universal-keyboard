"""Quick check of the detector: python test_engine.py"""
import sys

from uk.engine import SENTENCE_END, Context, Engine

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
    ctx = Context()
    out = []
    for w in s.split():
        core = w.rstrip(",.?!")
        r = e.analyze(core, ctx.value)
        if r["lang"] == "bg":
            out.append(r["cyr"] + w[len(core):])
        else:
            out.append(w)
        if r["lang"]:
            ctx.push(r["lang"])
        if w[-1] in SENTENCE_END:
            ctx.clear()
    print(f"{s}\n  -> {' '.join(out)}")


# Mixed Bulgarian / English sentences with the expected result.
MIXED = [
    ("zdravei, iskash li da otidem na meeting utre sutrinta?",
     "здравей, искаш ли да отидем на meeting утре сутринта?"),
    ("towa e mnogo dobro idea, no trqbwa da pitam",
     "това е много добро idea, но трябва да питам"),
    ("kupih si nov laptop, ama battery e slabo",
     "купих си нов laptop, ама battery е слабо"),
    ("hello Ivan, kak si I hope you are doing well",
     "hello Иван, как си I hope you are doing well"),  # a name, on the border: either is fine
    ("6te hodim na more prez iuli", "ще ходим на море през юли"),
    ("rojdeniqt mi den e na 5 yuni", "рожденият ми ден е на 5 юни"),
    ("tova e moqta liubima pesen", "това е моята любима песен"),
    ("kl\\`yt e na masata", "ключът е на масата"),
    ("`ovek, ]e doida utre sled rabota", "човек, ще дойда утре след работа"),
    ("[apkata mi e v kuhnqta", "шапката ми е в кухнята"),
    ("tyrsq ti s\\rpriz za sybota", "търся ти сюрприз за събота"),
    ("~estit rojden den, kyshtata e gotova", "Честит рожден ден, къщата е готова"),
    ("dyjdyt spira li ve4e?", "дъждът спира ли вече?"),
    ("it is just a bug in the menu", "it is just a bug in the menu"),
    ("`ovek, the server is down, ]e go restartiram", "човек, the server is down, ще го рестартирам"),
    ("[efyt kaza, 4e deadline-a e v petyk", "шефът каза, че deadline-a е в петък"),
    ("happy birthday, ~estit rojden den!", "happy birthday, Честит рожден ден!"),
    ("tyrsq ti s\\rpriz za party-to v sybota", "търся ти сюрприз за party-to в събота"),
    ("6te hodim na more prez iuli, can't wait", "ще ходим на море през юли, can't wait"),
    ("thank you, ]astliv sym 4e si tuk", "thank you, щастлив съм че си тук"),
    ("see you later, ]e ti se obadq", "see you later, ще ти се обадя"),
    ("kak si? I hope you are well",
     "как си? I hope you are well"),
    ("6te sum na call v 3 4asa, sled towa sum free",
     "ще съм на call в 3 часа, след това съм free"),
    ("the server is down, 6te go restartiram sled malko",
     "the server is down, ще го рестартирам след малко"),
    ("please send me the file, blagodarq mnogo",
     "please send me the file, благодаря много"),
    ("obicham da gledam movies v petuk wecher",
     "обичам да гледам movies в петък вечер"),
    ("i az idvam s teb",
     "и аз идвам с теб"),
    ("send me the report to friday",
     "send me the report to friday"),
    ("the app crashes kogato natisna butona za login",
     "the app crashes когато натисна бутона за login"),
    ("this is the best pizza ever, mnogo e vkusna",
     "this is the best pizza ever, много е вкусна"),
    ("mojesh li da mi pomognesh s tozi bug v koda?",
     "можеш ли да ми помогнеш с този bug в кода?"),
    ("sega sym zaet, but call me later to talk",
     "сега съм зает, but call me later to talk"),
    ("ne znam, maybe we can go to the sea",
     "не знам, maybe we can go to the sea"),
    ("this is so cool, da go napravim li",
     "this is so cool, да го направим ли"),
    # y = ъ or й; ьо comes from "yo"
    ("moyat shofyor kaza, che kyde e bulyona",
     "моят шофьор каза, че къде е бульона"),
    # "-cki" is Bulgarian, not English "ck"; c written for ч ("pricina")
    ("grycki ezik", "гръцки език"),
    ("no ne go hvana po nyakakva pricina", "но не го хвана по някаква причина"),
    ("cvete i nacin", "цвете и начин"),
]


def convert(sentence: str) -> str:
    ctx = Context()
    out = []
    for w in sentence.split():
        core = w.rstrip(",.?!")
        r = e.analyze(core, ctx.value)
        out.append(r["cyr"] + w[len(core):] if r["lang"] == "bg" else w)
        if r["lang"]:
            ctx.push(r["lang"])
        if w[-1] in SENTENCE_END:
            ctx.clear()
    return " ".join(out)


print("\nСмесени изречения:")
bad = 0
for src, want in MIXED:
    got = convert(src)
    ok = got == want
    bad += not ok
    print(f"{'OK ' if ok else 'ГРЕШКА'} {src}\n       -> {got}" + ("" if ok else f"\n  трябва {want}"))
print(f"\n{len(MIXED) - bad}/{len(MIXED)} верни")
sys.exit(1 if bad else 0)
