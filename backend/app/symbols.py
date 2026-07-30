# """Symbol library — an optional add-on.

# A logged-in user stores their own symbols: a short trigger (";late" or a glyph)
# standing for a phrase. Decoding replaces triggers with phrases; encoding does
# the reverse. Libraries can be exported and shared, so two people who hold the
# same library read the same message.

# Everything for this feature lives in this file, templates/symbols.html and
# frontend/symbols.css. Delete them and the decoder still runs — main.py only
# registers this blueprint if the import succeeds.

# Like the rest of the site it is plain forms: post, act, render.
# """

# import json
# import re
# import time

# from flask import (Blueprint, Response, redirect, render_template, request,
#                    session)

# from . import rules
# from ... import db

# bp = Blueprint("symbols", __name__)

# MAX_SYMBOLS = 200          # a library nobody can learn is a library nobody uses
# MAX_TRIGGER = 24
# MAX_VALUE = 200

# MAX_RULES = 6              # a pattern nobody can hold in their head is no use

# SCHEMA = """
# CREATE TABLE IF NOT EXISTS user_rules (
#     user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
#     chain      TEXT NOT NULL,          -- JSON list of {rule, param}
#     updated_at REAL NOT NULL
# );

# CREATE TABLE IF NOT EXISTS symbols (
#     id         INTEGER PRIMARY KEY AUTOINCREMENT,
#     user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#     trigger    TEXT NOT NULL,
#     value      TEXT NOT NULL,
#     note       TEXT,
#     created_at REAL NOT NULL,
#     UNIQUE (user_id, trigger)
# );
# """


# def connect():
#     """Same database as the rest of the app, plus this feature's own table."""
#     con = db.connect()
#     con.executescript(SCHEMA)
#     return con


# # --------------------------------------------------------------------------- #
# # who is asking
# # --------------------------------------------------------------------------- #
# def user_id():
#     """The logged-in user's id, or None. Symbols are private to one account."""
#     return session.get("uid")


# def need_login():
#     """The logged-in user's id, or None. Pages render a "log in first" panel
#     rather than redirecting, so nobody loses the URL they typed."""
#     return user_id()


# # --------------------------------------------------------------------------- #
# # storage
# # --------------------------------------------------------------------------- #
# def list_symbols(uid):
#     with connect() as con:
#         rows = con.execute(
#             "SELECT id, trigger, value, note FROM symbols WHERE user_id = ? ORDER BY trigger",
#             (uid,),
#         ).fetchall()
#     return [dict(r) for r in rows]


# def save_symbol(uid, trigger, value, note=""):
#     """Add a symbol, or update the value if that trigger already exists."""
#     with connect() as con:
#         con.execute(
#             "INSERT INTO symbols (user_id, trigger, value, note, created_at)"
#             " VALUES (?, ?, ?, ?, ?)"
#             " ON CONFLICT (user_id, trigger) DO UPDATE SET value = ?, note = ?",
#             (uid, trigger, value, note, time.time(), value, note),
#         )
#         row = con.execute(
#             "SELECT id, trigger, value, note FROM symbols WHERE user_id = ? AND trigger = ?",
#             (uid, trigger),
#         ).fetchone()
#     return dict(row)


# def delete_symbol(uid, symbol_id):
#     with connect() as con:
#         cur = con.execute(
#             "DELETE FROM symbols WHERE id = ? AND user_id = ?", (symbol_id, uid)
#         )
#         return cur.rowcount > 0


# def count_symbols(uid):
#     with connect() as con:
#         return con.execute(
#             "SELECT COUNT(*) FROM symbols WHERE user_id = ?", (uid,)
#         ).fetchone()[0]


# def get_chain(uid):
#     """The user's own rule chain — their pattern. Empty list if they have none."""
#     with connect() as con:
#         row = con.execute("SELECT chain FROM user_rules WHERE user_id = ?", (uid,)).fetchone()
#     if not row:
#         return []
#     try:
#         return json.loads(row["chain"])
#     except ValueError:
#         return []          # a corrupt row means "no pattern", not a broken page


# def save_chain(uid, chain):
#     with connect() as con:
#         con.execute(
#             "INSERT INTO user_rules (user_id, chain, updated_at) VALUES (?, ?, ?)"
#             " ON CONFLICT (user_id) DO UPDATE SET chain = ?, updated_at = ?",
#             (uid, json.dumps(chain), time.time(), json.dumps(chain), time.time()),
#         )
#     return chain


# def clean_chain(raw):
#     """Keep only steps that name a real rule, and cap the length."""
#     chain = []
#     for step in (raw or [])[:MAX_RULES]:
#         if isinstance(step, dict) and step.get("rule") in rules.RULES:
#             chain.append({"rule": step["rule"], "param": str(step.get("param", ""))})
#     return chain


# # --------------------------------------------------------------------------- #
# # the codec
# #
# # Decoding must be exact: two people holding the same library have to read the
# # same message. So this is plain lookup — no guessing, no cleverness.
# # --------------------------------------------------------------------------- #
# def decode(text, symbols):
#     """Replace every trigger with its phrase. Unknown words are left alone."""
#     table = {s["trigger"]: s["value"] for s in symbols}
#     out = []
#     for word in text.split():
#         # keep punctuation stuck to the end of a symbol: ";late," still matches
#         core = word.rstrip(".,!?;:")
#         tail = word[len(core):]
#         out.append(table[core] + tail if core in table else word)
#     return tidy(" ".join(out))


# def encode(text, symbols):
#     """Replace phrases with their triggers. Longest phrases go first, so a
#     longer symbol always wins over a shorter one inside it."""
#     result = text
#     for s in sorted(symbols, key=lambda s: len(s["value"]), reverse=True):
#         if s["value"]:
#             result = re.sub(re.escape(s["value"]), s["trigger"], result, flags=re.I)
#     return result


# def tidy(text):
#     """Capitalise the start and make sure the line ends with punctuation."""
#     text = re.sub(r"\s+", " ", text).strip()
#     if not text:
#         return text
#     text = text[0].upper() + text[1:]
#     if text[-1] not in ".!?":
#         text += "."
#     return text


# def preview(text, symbols):
#     """Which triggers were found — lets the page show what it recognised."""
#     table = {s["trigger"] for s in symbols}
#     return [w.rstrip(".,!?;:") for w in text.split() if w.rstrip(".,!?;:") in table]


# # --------------------------------------------------------------------------- #
# # the shareable file
# #
# # One symbol per line: trigger, a tab, then the phrase. Plain text on purpose —
# # anyone can read it, edit it in any text editor, or paste it into a message.
# # --------------------------------------------------------------------------- #
# def to_text(symbols):
#     lines = ["# symbol library", "# trigger<TAB>phrase"]
#     for s in symbols:
#         lines.append(f"{s['trigger']}\t{s['value']}")
#     return "\n".join(lines) + "\n"


# def from_text(raw):
#     """Read a library file. Blank lines and # comments are ignored, and a line
#     that isn't trigger-tab-phrase is skipped rather than failing the import."""
#     found = []
#     for line in raw.splitlines():
#         line = line.strip()
#         if not line or line.startswith("#"):
#             continue
#         # a tab, or two spaces used as a column — a single space is just prose,
#         # so "bad line with no tab" is skipped instead of half-imported
#         parts = re.split(r"\t| {2,}", line, maxsplit=1)
#         if len(parts) != 2:
#             continue
#         trigger, value = parts[0].strip(), parts[1].strip()
#         if trigger and " " not in trigger and value:
#             found.append((trigger[:MAX_TRIGGER], value[:MAX_VALUE]))
#     return found


# #: a dozen symbols to start from, so the page is never empty
# STARTER = [
#     (";late", "running late, be there soon"),
#     (";eta", "what time are you thinking?"),
#     (";move", "can we move this to another day?"),
#     (";yes", "I'll be there"),
#     (";got", "got it"),
#     (";onit", "on it, I'll come back to you"),
#     (";done", "that is done"),
#     (";busy", "can't right now"),
#     (";later", "I'll come back to this later"),
#     (";seen", "I read this, I'm thinking about it, reply coming later"),
#     (";ty", "thank you, really"),
#     (";bye", "talk soon"),
# ]


# # --------------------------------------------------------------------------- #
# # pages
# # --------------------------------------------------------------------------- #
# @bp.get("/symbols")
# def page(message=None, bad=False, try_in="", try_out="", try_note="", chain=None):
#     """The whole library page. Every other route does its work then calls this
#     or redirects back to it."""
#     uid = need_login()
#     edit = {}
#     symbols = []
#     if uid:
#         symbols = list_symbols(uid)
#         chain = chain if chain is not None else get_chain(uid)
#         wanted = request.args.get("edit", type=int)
#         edit = next((s for s in symbols if s["id"] == wanted), {}) if wanted else {}

#     info = {r["key"]: r for r in rules.describe()}
#     return render_template(
#         "symbols.html",
#         user=db.user_by_id(uid)["username"] if uid else None,
#         symbols=symbols, edit=edit, max_symbols=MAX_SYMBOLS,
#         rules=rules.describe(), rule_info=info, chain=chain or [], max_rules=MAX_RULES,
#         try_in=try_in, try_out=try_out, try_note=try_note,
#         message=message, message_bad=bad, here="/symbols", symbols_enabled=True,
#     )


# @bp.post("/symbols/save")
# def add():
#     uid = need_login()
#     if not uid:
#         return redirect("/symbols")
#     trigger = request.form.get("trigger", "").strip()
#     value = request.form.get("value", "").strip()
#     note = request.form.get("note", "").strip()[:120]

#     if not trigger or " " in trigger or len(trigger) > MAX_TRIGGER:
#         return page(message=f"trigger must be one word, up to {MAX_TRIGGER} characters", bad=True)
#     if not value or len(value) > MAX_VALUE:
#         return page(message=f"phrase must be 1-{MAX_VALUE} characters", bad=True)
#     # the cap only blocks new triggers — editing an existing one is always fine
#     existing = {s["trigger"] for s in list_symbols(uid)}
#     if trigger not in existing and len(existing) >= MAX_SYMBOLS:
#         return page(message=f"library is full ({MAX_SYMBOLS} symbols)", bad=True)

#     save_symbol(uid, trigger, value, note)
#     return redirect("/symbols")


# @bp.post("/symbols/<int:symbol_id>/delete")
# def remove(symbol_id):
#     uid = need_login()
#     if uid:
#         delete_symbol(uid, symbol_id)      # the user_id in the query is the check
#     return redirect("/symbols")


# @bp.post("/symbols/seed")
# def seed():
#     uid = need_login()
#     if uid:
#         for trigger, value in STARTER:
#             if count_symbols(uid) < MAX_SYMBOLS:
#                 save_symbol(uid, trigger, value, "")
#     return redirect("/symbols")


# @bp.get("/symbols/export")
# def export():
#     uid = need_login()
#     if not uid:
#         return redirect("/symbols")
#     return Response(
#         to_text(list_symbols(uid)), mimetype="text/plain; charset=utf-8",
#         headers={"Content-Disposition": 'attachment; filename="my-symbols.txt"'})


# @bp.post("/symbols/import")
# def load():
#     """Copy someone else's library into yours, so their later edits never
#     change what your messages mean."""
#     uid = need_login()
#     if not uid:
#         return redirect("/symbols")
#     upload = request.files.get("pack")
#     if not upload or not upload.filename:
#         return page(message="choose a library file first", bad=True)

#     raw = upload.read(500_000).decode("utf-8", errors="replace")
#     added = 0
#     for trigger, value in from_text(raw):
#         if count_symbols(uid) >= MAX_SYMBOLS:
#             break
#         save_symbol(uid, trigger, value, "")
#         added += 1
#     if not added:
#         return page(message="that file has no symbols in it", bad=True)
#     return page(message=f"Imported {added} symbols.")


# # --------------------------------------------------------------------------- #
# # the pattern
# # --------------------------------------------------------------------------- #
# def read_chain():
#     """Rules come back as parallel lists, one entry per row on the page."""
#     names = request.form.getlist("rule")
#     params = request.form.getlist("param")
#     chain = []
#     for i, name in enumerate(names[:MAX_RULES]):
#         if name in rules.RULES:
#             chain.append({"rule": name, "param": params[i] if i < len(params) else ""})
#     return chain


# @bp.post("/symbols/pattern")
# def pattern():
#     uid = need_login()
#     if not uid:
#         return redirect("/symbols")

#     chain = read_chain()
#     action = request.form.get("action", "save")

#     if action == "add":
#         if len(chain) < MAX_RULES:
#             first = next(iter(rules.RULES))
#             chain.append({"rule": first, "param": rules.RULES[first][5] or ""})
#         return page(chain=chain)
#     if action.startswith(("del:", "up:", "down:")):
#         what, _, index = action.partition(":")
#         i = int(index) if index.isdigit() else -1
#         if 0 <= i < len(chain):
#             if what == "del":
#                 chain.pop(i)
#             elif what == "up" and i > 0:
#                 chain[i - 1], chain[i] = chain[i], chain[i - 1]
#             elif what == "down" and i < len(chain) - 1:
#                 chain[i + 1], chain[i] = chain[i], chain[i + 1]
#         return page(chain=chain)

#     # A pattern that cannot be undone is worse than no pattern, so it is
#     # checked against awkward sample text before it reaches the database.
#     problem = check_round_trip(chain)
#     if problem:
#         return page(chain=chain, message=problem, bad=True)
#     save_chain(uid, chain)
#     return page(chain=chain, message="Pattern saved — checked and reversible.")


# #: text a pattern must survive before it can be saved
# SAMPLES = ["", "Hello, World!", "12345", "café ünïcode",
#            "the quick brown fox jumps over the lazy dog"]


# def check_round_trip(chain):
#     """Return a reason the chain is unusable, or None if it is fine."""
#     for sample in SAMPLES:
#         try:
#             coded = rules.run_chain(sample, chain, "encode")
#             back = rules.run_chain(coded, chain, "decode")
#         except ValueError as exc:
#             return str(exc)
#         if back != sample:
#             return "this pattern cannot be undone — check its settings"
#         if len(coded) != len(sample):
#             return "a rule changed the message length"
#     return None


# @bp.post("/symbols/run")
# def try_it():
#     """Encoding goes phrases -> triggers -> rules.
#     Decoding goes rules -> triggers -> phrases, i.e. exactly backwards."""
#     uid = need_login()
#     if not uid:
#         return redirect("/symbols")

#     text = request.form.get("text", "")[:20000]
#     direction = request.form.get("direction", "decode")
#     chain = get_chain(uid)
#     symbols = list_symbols(uid)

#     try:
#         if direction == "encode":
#             out = rules.run_chain(encode(text, symbols), chain, "encode")
#             note = "Phrases swapped for triggers, then your pattern applied."
#         else:
#             plain = rules.run_chain(text, chain, "decode")
#             out = decode(plain, symbols)
#             found = preview(plain, symbols)
#             note = ("Recognised: " + " ".join(found)) if found else "No symbols recognised."
#     except ValueError as exc:
#         return page(try_in=text, message=str(exc), bad=True)

#     return page(try_in=text, try_out=out, try_note=note)
