# Decoder

A web tool for decoding text. Paste something encoded, and it works out what it
is; or build your own private shorthand and encode with that.

Written in Flask with plain HTML forms — no JavaScript is needed for anything
except the visual theme, so the whole site works with scripting turned off.

---

## What it does

**Auto-detect.** Paste a string and press *Detect*. Every method is tried, and
the results are ranked by how much they look like readable text. Click the one
you want and it becomes a step.

**Chain steps.** Real puzzles are layered — Base64 wrapped around Hex wrapped
around a Caesar shift. Each step runs on the previous step's output, with a
preview under every one, so you can see exactly where a chain goes wrong.

**Save and revisit.** With an account, name a result to keep it, and every run
is recorded in your history automatically.

**Your own symbol library.** Store short triggers that stand for whole phrases
(`;late` → *running late, be there soon*), then add rules on top to scramble the
result. Export the library as a text file and whoever imports it reads exactly
what you wrote.

---

## Encodings

| Method | Example |
|---|---|
| Base64 | `SGVsbG8=` → `Hello` |
| Hex | `48 65 6c 6c 6f` → `Hello` |
| Binary | `01001000 01101001` → `Hi` |
| ASCII decimal | `72 101 121` → `Hey` |
| URL / percent | `a%20b` → `a b` |
| Caesar shift | `Dwwdfn` → `Attack` (shift 3) |

Every decoder is **strict**: it refuses input that isn't in its own alphabet.
That's what makes detection work — a codec that parses cleanly is already
evidence, so detection is mostly "try everything and rank what survives".

### How detection ranks candidates

Each candidate result is scored on three things:

- the share of printable characters (garbage scores badly),
- common English words appearing in it,
- how closely letter frequencies match English (a chi-square fit).

Then each codec adds a bonus reflecting how restrictive its alphabet is — a
clean Morse or Binary parse means more than a clean Caesar one, since Caesar
"decodes" any text at all. Layout matters too: `72 101 108` could be read as
hex, but hex bytes are always two digits, so three-digit groups tip the ranking
towards ASCII decimal.

---

## Symbol libraries and patterns

A **symbol** is a trigger and a phrase. Decoding swaps triggers for phrases;
encoding does the reverse, longest phrase first.

A **pattern** is up to six rules applied after your symbols:

| Rule | Shape | What it does |
|---|---|---|
| Custom alphabet | strict | your own order for a–z |
| Keyword shift | strict | each letter moves by the next letter of a keyword |
| Reverse all | stable | the whole message backwards |
| Reverse each word | stable | words stay put, letters flip |
| Rail fence | stable | write along a zig-zag, read off line by line |

Every rule **keeps the message the same length** — *strict* means each character
stays in place, *stable* means characters move but the count doesn't change.
That guarantee is enforced at runtime and is what makes a pattern reversible:
decoding runs the same list backwards.

A pattern is checked against awkward sample text (empty, punctuation, digits,
non-ASCII) before it can be saved. If it can't be undone, it isn't stored.

---

## Running it

```bash
pip install -r requirements.txt
python wsgi.py
```

Then open <http://localhost:8000>.

In production, any WSGI server works:

```bash
gunicorn wsgi:app
```

### Settings

| Variable | Purpose |
|---|---|
| `DECODE_SECRET` | Signs session cookies. Set this in deployment, or logins reset on every restart. |
| `DECODE_DATA` | Where the SQLite database lives. Defaults to `backend/data/`. |

---

## Tests

```bash
cd backend
pytest
```

136 tests. Alongside the usual cases they check the properties that matter:
every codec round-trips (`decode(encode(x)) == x`), every rule preserves length,
and one account can neither see nor delete another's saved results.

---

## Layout

```
wsgi.py              entry point — puts backend/ on the path, exposes `app`
backend/
  app/
    main.py          routes; reads the form, runs the pipeline, renders
    codecs.py        the six encodings, detection scoring, the step pipeline
    db.py            SQLite storage via pandas
    symbols.py       symbol library add-on (optional)
    rules.py         length-preserving rules for patterns
  templates/         Jinja templates — one per page
  tests/
frontend/            style.css, symbols.css, glitch.js (theme only)
```

`symbols.py` and `rules.py` are an **optional add-on**. `main.py` registers them
inside a `try/except ImportError`, so deleting those files leaves the decoder
working exactly as before — there's a test for it.

---

## A note on what this is

This is obfuscation, not encryption. Anyone holding your symbol library can read
your messages, and the classical ciphers here are breakable with frequency
analysis and an afternoon. It's built to be personal and memorable, not private.
