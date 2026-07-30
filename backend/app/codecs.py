"""Encodings, plaintext scoring, and the step pipeline.
Basically js construct any function that needed to run the 
page and the algorithm
All necessary nothing decorative
"""

import base64
import re
import urllib.parse

# --------------------------------------------------------------------------- #
# codecs
#
# Error convention: every decode() raises ValueError when the input isn't in its
# alphabet, with a short lowercase reason ("not hex") that is shown to the user
# verbatim. This is load-bearing in two places:
#   - detect() treats a ValueError as "this codec isn't it" and moves on;
#   - run() catches it per step and reports it without killing the chain.
# So a strict decode that fails loudly is a feature, not a bug — never widen a
# check to "accept anything and return garbage".
# --------------------------------------------------------------------------- #


def b64_encode(t):
    #Encodes the string t as UTF-8 bytes, 
    # then Base64-encodes those bytes
    return base64.b64encode(t.encode()).decode() # decode only for python to understand 
#cuz it convert it into a string 


def b64_decode(t):
    s = re.sub(r"\s+", "", t).replace("-", "+").replace("_", "/")
    if not s or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", s):
        raise ValueError("not base64")
    return _text(base64.b64decode(s + "=" * (-len(s) % 4), validate=True))


def hex_encode(t):
    return " ".join(f"{b:02x}" for b in t.encode())


def hex_decode(t):
    s = re.sub(r"[\s,:]|0x", "", t, flags=re.I)
    if not s or len(s) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", s):
        raise ValueError("not hex")
    return _text(bytes.fromhex(s))


def bin_encode(t):
    return " ".join(f"{b:08b}" for b in t.encode())


def bin_decode(t):
    s = re.sub(r"[\s,]", "", t)
    if not s or len(s) % 8 or not re.fullmatch(r"[01]+", s):
        raise ValueError("not 8-bit binary")
    return _text(bytes(int(s[i:i + 8], 2) for i in range(0, len(s), 8)))


def dec_encode(t):
    return " ".join(str(ord(c)) for c in t)


#: separators people actually use between decimal codes
DEC_SEPARATORS = r"[\s,;:|/\-]"


def dec_decode(t):
    """Code points as numbers: '72 101 121', '72,101,121', or run-together '072101121'.s
    """
    s = t.strip()
    if not s:
        raise ValueError("not decimal codes")

    if re.search(DEC_SEPARATORS, s) and re.fullmatch(rf"[\d\s]|[\d{DEC_SEPARATORS[1:-1]}]+", s):
        values = [int(p) for p in re.split(r"[^0-9]+", s) if p]
    elif re.fullmatch(r"\d+", s):
        values = _fixed_width(s)
    else:
        raise ValueError("not decimal codes")

    if not values or any(v > 0x10FFFF for v in values):
        raise ValueError("value out of range")
    return "".join(chr(v) for v in values)


def _fixed_width(digits):
    """Split a bare digit run into equal-width code points, widest first."""
    for width in (3, 2):
        if len(digits) % width:
            continue
        groups = [int(digits[i:i + width]) for i in range(0, len(digits), width)]
        if all(32 <= v < 127 or v in (9, 10, 13) for v in groups):
            return groups
    raise ValueError("not decimal codes")


def url_encode(t):
    return urllib.parse.quote(t, safe="")


def url_decode(t):
    if not re.search(r"%[0-9a-fA-F]{2}|\+", t):
        raise ValueError("no percent escapes")
    return urllib.parse.unquote_plus(t)


ALPHA = "abcdefghijklmnopqrstuvwxyz"


def caesar_encode(t, shift):
    """Shift letters by `shift`; digits, spaces and punctuation are left alone."""
    n = int(shift) % 26
    out = []
    for c in t:
        i = ALPHA.find(c.lower())
        if i < 0:
            out.append(c)
        else:
            rotated = ALPHA[(i + n) % 26]
            out.append(rotated.upper() if c.isupper() else rotated)
    return "".join(out)


def caesar_decode(t, shift):
    return caesar_encode(t, -int(shift))


def _text(data):
    return data.decode("utf-8", errors="replace")


# key: (label, encode, decode, detection bonus, parameter default)
# Detection bonus (higher = more preferred when scores are close). 
# 0 means “never auto-detect this one on its own”
# parameter -> default for codecs that take one (None means it takes none)
CODECS = {
    "base64":  ("Base64",           b64_encode,   b64_decode,   30, None),
    "hex":     ("Hex",              hex_encode,   hex_decode,   34, None),
    "binary":  ("Binary (8-bit)",   bin_encode,   bin_decode,   38, None),
    "decimal": ("ASCII decimal",    dec_encode,   dec_decode,   26, None),
    "url":     ("URL / percent",    url_encode,   url_decode,   24, None),
    "caesar":  ("Caesar shift",     caesar_encode, caesar_decode, 0, "3"),
}


def apply(method, text, direction="decode", param=None):
    if method not in CODECS:
        raise ValueError(f"unknown method '{method}'")
    _, encode, decode, _, default = CODECS[method]
    fn = encode if direction == "encode" else decode
    if default is None:
        return fn(text)                      # codec takes no parameter
    try:
        # an empty box in the UI means "use the default", not "shift by nothing"
        return fn(text, param if param not in (None, "") else default)
    except (TypeError, ValueError):
        # int("banana") and wrong-arity calls both land here; re-raised with the
        # method name so the message is useful once it reaches the step preview
        raise ValueError(f"bad parameter for {method}: {param!r}")


# --------------------------------------------------------------------------- #
# detection
# --------------------------------------------------------------------------- #
COMMON = {
    "the", "and", "that", "have", "for", "not", "with", "you", "this", "but",
    "from", "are", "was", "all", "one", "out", "who", "has", "her", "his",
    "they", "what", "when", "which", "were", "there", "their", "flag", "key",
    "message", "secret",
}

# English letter frequency, percent
FREQ = {
    "e": 12.7, "t": 9.1, "a": 8.2, "o": 7.5, "i": 7.0, "n": 6.7, "s": 6.3,
    "h": 6.1, "r": 6.0, "d": 4.3, "l": 4.0, "c": 2.8, "u": 2.8, "m": 2.4,
    "w": 2.4, "f": 2.2, "g": 2.0, "y": 2.0, "p": 1.9, "b": 1.5, "v": 1.0,
    "k": 0.8, "j": 0.15, "x": 0.15, "q": 0.1, "z": 0.07,
}

# weighs are not fixed, they can be easily changed 
def score(text):
    """How much this looks like readable text. Real plaintext lands around 60-120.
    how english-like the input text is 
    """
    if not text.strip():
        return -1e9
    #count how printable is the text, with a scaling for broken word 
    #and normal word each of 55 and 8
    printable = sum(ord(c) in (9, 10, 13) or 32 <= ord(c) < 127 for c in text)
    broken = sum(ord(c) == 0xFFFD or ord(c) < 9 for c in text)
    total = printable / len(text) * 55 - broken * 8
    #count for common work in teh collection, with a weight of 13
    words = re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
    total += 13 * sum(w in COMMON for w in words)
    # letter-freq chi-squared -> stats here 
    letters = [c.lower() for c in text if c.isascii() and c.isalpha()]
    if len(letters) > 8:
        chi = sum((letters.count(c) - pct * len(letters) / 100) ** 2 / (pct * len(letters) / 100)
                  for c, pct in FREQ.items())
        total += max(-20.0, 22 - chi / len(letters) * 9)
    #letter density
    total += len(letters) / len(text) * 18
    #is letter -space -letter pattern exist in teh text 
    if re.search(r"[a-zA-Z] [a-zA-Z]", text):
        total += 6
    return total


def shape_adjust(key, source):
    """Nudge a codec's confidence by how well the input's *layout* fits it.
    """
    groups = [g for g in re.split(r"[\s,;:|/\-]+", source.strip()) if g]
    if len(groups) < 2 or not all(g.isdigit() for g in groups):
        return 0
    if key == "decimal":
        return 18 if any(len(g) != 2 for g in groups) else 0
    if key == "hex":
        return -25 if any(len(g) != 2 for g in groups) else 0
    if key == "binary":
        return -25 if any(len(g) != 8 for g in groups) else 0
    return 0


def detect(text, limit=6):
    """Try every codec worth guessing; return (score of input as-is, ranked candidates)."""
    source = text.strip()
    found = []
    for key, (label, _, decode, bonus, _default) in CODECS.items():
        if not bonus:
            continue
        try:
            out = decode(source)
        except Exception:
            # Deliberately broad: any failure means "not this codec". Catching
            # only ValueError would let a stray TypeError from a future codec
            # take down the whole detection sweep for one bad guess.
            continue
        if out and out != source:
            found.append({"method": key, "label": label, "output": out,
                          "score": score(out) + bonus + shape_adjust(key, source)})

    # Caesar always "decodes", so only its single best shift competes, and at a
    # penalty — otherwise 25 near-identical guesses would crowd out real hits.
    shifts = [(score(caesar_decode(source, n)) - 12, n) for n in range(1, 26)]
    best, shift = max(shifts)
    if source.strip():
        found.append({"method": "caesar", "label": f"Caesar shift {shift}",
                      "output": caesar_decode(source, shift),
                      "param": str(shift), "score": best})

    found.sort(key=lambda c: c["score"], reverse=True)
    return score(source), found[:limit]


# pipeline
def run(text, steps):
    """Run steps in order, each on the previous output.

    A failing step doesn't abort the chain — it reports the error and passes its
    input through
    """
    current = text
    results = []

    #the steps are the adjuestable small bricks in the middle section 
    #all steps can be customized 
    for step in steps:
        #SKIpping wow wowow
        if not step.get("enabled", True):
            results.append({"output": current, "skipped": True})
            continue
        try:
            #if the user doesn't specify a decoding methos
            if step["method"] == "auto":
                _, candidates = detect(current, limit=1)
                if not candidates:
                    # auto-detect found nothing plausible 
                    raise ValueError("nothing detected")
                #based on best score get the top one output 
                current = candidates[0]["output"]
                results.append({"output": current, "note": candidates[0]["label"]})
            else:
                current = apply(step["method"], current,
                                step.get("direction", "decode"), step.get("param"))
                results.append({"output": current})
        except Exception as exc:
            results.append({"output": current, "error": str(exc)})

    return current, results
