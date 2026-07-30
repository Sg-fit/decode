"""Rules — the transforms a user can build their own pattern from.

Part of the symbol-library add-on. Delete this file plus symbols.* and the
decoder runs unchanged.

One hard constraint: **every rule keeps the message the same length.**
Length is counted in code points, so "café" is 4 either way.

That rule buys three things:

  * inverses stay simple — nothing has to be parsed back out;
  * chaining is safe — ten rules can't inflate a message;
  * validation is nearly free — len(out) == len(in) catches most mistakes
    before round-tripping does.

Each rule declares a shape:

  strict — character i out came from character i in (alphabet, keyword)
  stable — same length, characters moved (reverse, rail fence)

Anything that would change the length (chunking, base64, padding) is not a
rule and cannot be added to a pattern.
"""

import re

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _same_case(source, letter):
    """Give `letter` the capitalisation of `source`."""
    return letter.upper() if source.isupper() else letter


# --------------------------------------------------------------------------- #
# strict rules — position for position
# --------------------------------------------------------------------------- #
def alphabet_encode(text, key):
    """The user's own alphabet: a becomes key[0], b becomes key[1], and so on.
    Anything that isn't a letter is left exactly where it is."""
    table = check_alphabet(key)
    return "".join(_same_case(c, table[c.lower()]) if c.lower() in table else c
                   for c in text)


def alphabet_decode(text, key):
    table = check_alphabet(key)
    back = {v: k for k, v in table.items()}
    return "".join(_same_case(c, back[c.lower()]) if c.lower() in back else c
                   for c in text)


def check_alphabet(key):
    """A custom alphabet has to be a permutation of a-z, or it can't be undone."""
    cleaned = str(key or "").lower()
    if len(cleaned) != 26 or set(cleaned) != set(LETTERS):
        raise ValueError("alphabet must use each of the 26 letters exactly once")
    return dict(zip(LETTERS, cleaned))


def keyword_shift(text, key, direction):
    """Shift each letter by the next letter of the keyword (a Vigenere).

    The keyword only advances on letters, so spacing and punctuation don't
    knock the key out of step.
    """
    word = re.sub(r"[^a-z]", "", str(key or "").lower())
    if not word:
        raise ValueError("keyword must contain letters")

    out = []
    i = 0
    for c in text:
        if c.lower() in LETTERS:
            step = LETTERS.index(word[i % len(word)]) * direction
            moved = LETTERS[(LETTERS.index(c.lower()) + step) % 26]
            out.append(_same_case(c, moved))
            i += 1
        else:
            out.append(c)
    return "".join(out)


def keyword_encode(text, key):
    return keyword_shift(text, key, 1)


def keyword_decode(text, key):
    return keyword_shift(text, key, -1)


# --------------------------------------------------------------------------- #
# stable rules — same characters, new places
# --------------------------------------------------------------------------- #
def reverse(text, _param=None):
    """Whole message backwards. Its own inverse."""
    return text[::-1]


def reverse_words(text, _param=None):
    """Each word backwards, words stay put. Also its own inverse."""
    parts = re.split(r"(\s+)", text)
    return "".join(p if p.isspace() else p[::-1] for p in parts)


def rail_pattern(length, rails):
    """Which rail each character sits on, zig-zagging down and back up."""
    n = check_rails(rails)
    rows = []
    row, step = 0, 1
    for _ in range(length):
        rows.append(row)
        if n > 1:
            if row == 0:
                step = 1
            elif row == n - 1:
                step = -1
            row += step
    return rows


def check_rails(rails):
    try:
        n = int(rails)
    except (TypeError, ValueError):
        raise ValueError("rails must be a number")
    if n < 2 or n > 20:
        raise ValueError("rails must be between 2 and 20")
    return n


def railfence_encode(text, rails):
    """Write the message along a zig-zag, then read it off row by row.

    No padding — a ragged last row is fine, and skipping padding is what keeps
    the length identical.
    """
    pattern = rail_pattern(len(text), rails)
    buckets = {}
    for row, char in zip(pattern, text):
        buckets.setdefault(row, []).append(char)
    return "".join("".join(buckets[row]) for row in sorted(buckets))


def railfence_decode(text, rails):
    """Rebuild the zig-zag: work out how many characters each row held, cut the
    message up that way, then read back along the pattern."""
    pattern = rail_pattern(len(text), rails)
    counts = {}
    for row in pattern:
        counts[row] = counts.get(row, 0) + 1

    rows, at = {}, 0
    for row in sorted(counts):
        rows[row] = list(text[at:at + counts[row]])
        at += counts[row]
    return "".join(rows[row].pop(0) for row in pattern)


# --------------------------------------------------------------------------- #
# registry
#
# key: (label, encode, decode, shape, parameter label, default, help)
# --------------------------------------------------------------------------- #
RULES = {
    "alphabet": ("Custom alphabet", alphabet_encode, alphabet_decode, "strict",
                 "letters", "qwertyuiopasdfghjklzxcvbnm",
                 "Your own order for a-z. Each letter exactly once."),
    "keyword":  ("Keyword shift", keyword_encode, keyword_decode, "strict",
                 "keyword", "kite",
                 "Each letter moves by the next letter of your keyword."),
    "reverse":  ("Reverse all", reverse, reverse, "stable",
                 None, None, "The whole message backwards."),
    "words":    ("Reverse each word", reverse_words, reverse_words, "stable",
                 None, None, "Every word backwards, word order kept."),
    "railfence": ("Rail fence", railfence_encode, railfence_decode, "stable",
                  "rails", "3",
                  "Write along a zig-zag of N lines, read off line by line."),
}


def describe():
    """What the page needs to draw the rule menu."""
    return [{"key": k, "name": v[0], "shape": v[3],
             "param": v[4], "default": v[5], "help": v[6]}
            for k, v in RULES.items()]


def apply_rule(key, text, param=None, direction="encode"):
    """Run one rule and make sure it kept its promise about length."""
    if key not in RULES:
        raise ValueError(f"unknown rule '{key}'")
    _, encode, decode, _, param_label, default, _ = RULES[key]
    fn = encode if direction == "encode" else decode

    if param_label is None:
        out = fn(text, None)
    else:
        out = fn(text, param if param not in (None, "") else default)

    # The guarantee, checked at runtime: a rule that changes the length would
    # break every pattern it appears in, so refuse the result outright.
    if len(out) != len(text):
        raise ValueError(f"rule '{key}' changed the length — refusing it")
    return out


def run_chain(text, chain, direction="encode"):
    """Apply a list of {rule, param} in order.

    Decoding walks the same list backwards with each rule's inverse, so a user
    only ever builds their pattern one way round.
    """
    steps = list(chain or [])
    if direction == "decode":
        steps = list(reversed(steps))
    for step in steps:
        text = apply_rule(step.get("rule", ""), text, step.get("param"), direction)
    return text
