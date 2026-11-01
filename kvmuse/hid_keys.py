"""USB HID keyboard usages and US-layout text mapping."""
KEYS = {chr(97+i): 4+i for i in range(26)}
KEYS.update({c: 30+i for i, c in enumerate("1234567890")})
KEYS.update(dict(enter=40, escape=41, backspace=42, tab=43, space=44,
                 right=79, left=80, down=81, up=82, delete=76, home=74, end=77))
KEYS.update({f"f{i}": 57+i for i in range(1, 13)})
MODIFIERS = dict(ctrl=1, shift=2, alt=4, gui=8, cmd=8, win=8)
TEXT = {c: (code, 0) for c, code in KEYS.items() if len(c) == 1}
TEXT.update({c.upper(): (KEYS[c], 2) for c in "abcdefghijklmnopqrstuvwxyz"})
for plain, shifted, code in zip("-=[]\\;'\x60,./", '_+{}|:"~<>?', [45, 46, 47, 48, 49, 51, 52, 53, 54, 55, 56]):
    TEXT[plain] = (code, 0)
    TEXT[shifted] = (code, 2)
TEXT.update({c: (30+i, 2) for i, c in enumerate("!@#$%^&*()")})
TEXT.update({" ": (44, 0), "\n": (40, 0), "\r": (40, 0), "\t": (43, 0)})

def text_keys(text):
    """Validate all text before sending any keys."""
    try:
        return [TEXT[c] for c in text]
    except KeyError as exc:
        raise ValueError(f"Unsupported US-layout character: {exc.args[0]!r}") from None
