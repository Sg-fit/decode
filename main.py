"""Flask app: the decoder, served as plain HTML forms.

    python main.py              (from the project root, serves on :8000)
"""

import time
from pathlib import Path

from flask import Flask, Response, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

# main.py sits at the project root; the modules live in backend/app, so put
# backend/ on the import path and import them as the "app" package.
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app import codecs, db      # noqa: E402  (must follow the path setup)

FRONTEND = ROOT / "frontend"
TEMPLATES = ROOT / "backend" / "templates"

MAX_INPUT = 200_000
MAX_STEPS = 25
HISTORY_BLOCK = 5          # rows shown on the decoder page; the rest are on /history
MIN_PASSWORD = 6

SAMPLE = "Njc2ZjIwNzQ2ODY1MjA2NzcyNjU2NTZlMjA2NDZmNmY3MjIx"

app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="",
            template_folder=str(TEMPLATES))
# Signs the session cookie. Persisted by db.secret_key() so a server restart
# doesn't log everyone out; set $DECODE_SECRET in deployment.
app.secret_key = db.secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


# Accounts
def current_user():
    """The logged-in user row, or None."""
    uid = session.get("uid")
    return db.user_by_id(uid) if uid else None


def safe_next(default="/"):
    """Where to go after a redirect. Only our own paths — an open redirect
    would let someone bounce a visitor off this site to anywhere."""
    target = request.form.get("next", "") or default
    return target if target.startswith("/") and not target.startswith("//") else default


@app.post("/login")
def login():
    """Log in, or sign up — decided by which button was pressed."""
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    making = request.form.get("action") == "register"
    back = safe_next()

    if not username or not password:
        return decoder_page(message="username and password required", bad=True)

    if making:
        # Format rules apply to new accounts only. Enforcing them at login
        # would reject an older password and hint at what it looks like.
        if not (3 <= len(username) <= 32) or not username.replace("_", "").isalnum():
            return decoder_page(message="username must be 3-32 letters, digits or underscores", bad=True)
        if len(password) < MIN_PASSWORD:
            return decoder_page(message=f"password must be at least {MIN_PASSWORD} characters", bad=True)
        uid = db.create_user(username, generate_password_hash(password))
        if uid is None:
            return decoder_page(message="that username is taken", bad=True)
        session["uid"] = uid
        return redirect(back)

    user = db.find_user(username)
    # One message for both "no such user" and "wrong password" 
    if user is None or not check_password_hash(user["password_hash"], password):
        return decoder_page(message="wrong username or password", bad=True)
    session["uid"] = user["id"]
    return redirect(back)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(safe_next())


# Reading the form
def read_steps():
    methods = request.form.getlist("method")
    dirs = request.form.getlist("dir")
    ons = request.form.getlist("on")
    params = request.form.getlist("param")

    steps = []
    for i, method in enumerate(methods[:MAX_STEPS]):
        if method != "auto" and method not in codecs.CODECS:
            continue                        # a made-up method is simply dropped
        steps.append({
            "method": method,
            "dir": dirs[i] if i < len(dirs) else "decode",
            "on": (ons[i] if i < len(ons) else "1") == "1",
            "param": params[i] if i < len(params) else "",
        })
    return steps


def read_text():
    """The input box — or an uploaded file"""
    upload = request.files.get("upload")
    if upload and upload.filename:
        return upload.read(MAX_INPUT + 1).decode("utf-8", errors="replace")[:MAX_INPUT]
    return request.form.get("text", "")[:MAX_INPUT]


def run_pipeline(text, steps):
    """codecs.run: {method, direction, param}; the form: {method, dir}."""
    return codecs.run(text, [
        {"method": s["method"], "direction": s["dir"],
         "param": s["param"], "enabled": s["on"]}
        for s in steps
    ])


# The decoder page
@app.get("/")
def index():
    return decoder_page()

#because we saved work in html form set up, the action vareiable here is a pain
#but it still saves a lot of work 
@app.post("/")
def index_post():
    action = request.form.get("action", "run")
    text = read_text()
    steps = read_steps()
    message = None
    #for each selected action, set up the algotirthm accordingly and apply method neccessary
    if action == "clear":
        text, steps = "", []
    elif action == "sample":
        text, steps = SAMPLE, []
    elif action == "add":
        if len(steps) < MAX_STEPS:
            steps.append({"method": "base64", "dir": "decode", "on": True, "param": ""})
    elif action == "feed":
        text, _ = run_pipeline(text, steps)
        steps = []
    elif action.startswith(("del:", "up:", "down:", "toggle:")):
        what, _, index = action.partition(":")
        i = int(index) if index.isdigit() else -1
        if 0 <= i < len(steps):
            if what == "del":
                steps.pop(i)
            elif what == "toggle":
                steps[i]["on"] = not steps[i]["on"]
            elif what == "up" and i > 0:
                steps[i - 1], steps[i] = steps[i], steps[i - 1]
            elif what == "down" and i < len(steps) - 1:
                steps[i + 1], steps[i] = steps[i], steps[i + 1]
    elif action.startswith("use:"):
        # the button's value is use:<method>:<param>; param is only ever a shift
        parts = action.split(":", 2)
        method = parts[1] if len(parts) > 1 else ""
        param = parts[2] if len(parts) > 2 else ""
        if method in codecs.CODECS and len(steps) < MAX_STEPS:
            steps.append({"method": method, "dir": "decode", "on": True, "param": param})
    elif action == "download":
        output, _ = run_pipeline(text, steps)
        name = "".join(c for c in request.form.get("filename", "") if c.isalnum() or c in "._- ")
        return Response(
            output, mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name or "decoded.txt"}"'})
    elif action == "save":
        user = current_user()
        output, _ = run_pipeline(text, steps)
        if user is None:
            message = "log in to save results"
        elif not text.strip():
            message = "nothing to save"
        else:
            db.add_entry(user["id"], "save", text, steps, output,
                         (request.form.get("savename") or "untitled")[:80])
            message = "Saved."
    
    #after finish all set-up and respond, return the plain page with neccesary updates
    return decoder_page(text=text, steps=steps, detect=(action == "detect"),
                        message=message, bad=bool(message) and message != "Saved.")


def decoder_page(text="", steps=None, detect=False, message=None, bad=False):
    """Run whatever the form describes, then render the page around the result."""
    steps = steps or []
    output, results = run_pipeline(text, steps)
    user = current_user()

    # Record the run for a logged-in user, skipping a repeat of the last one.
    if user and steps and text.strip():
        last = db.last_entry(user["id"], "history")
        if not (last and last["input"] == text and last["output"] == output):
            db.add_entry(user["id"], "history", text, steps, output)

    #running the auto detection 
    candidates, base_score = [], 0
    if detect:
        source = output if steps else text
        base_score, candidates = codecs.detect(source.strip())
        best = max([c["score"] for c in candidates], default=1)
        for c in candidates:
            c["width"] = max(4, round(c["score"] / best * 100))

       # diplaying the save and hisoty section
    saves, history, history_count = [], [], ""
    if user:
        saves = [decorate(e) for e in db.list_entries(user["id"], "save", 10)]
        rows = db.list_entries(user["id"], "history", HISTORY_BLOCK)
        total = db.count_entries(user["id"], "history")
        history = [decorate(e) for e in rows]
        history_count = f"{len(rows)} of {total}" if total > len(rows) else ""

        #After finish all of the commands, return the plain tempelated withup-date 
    return render_template(
        "index.html",
        text=text, steps=steps, results=results, output=output,
        methods=[{"key": k, "name": v[0]} for k, v in codecs.CODECS.items()],
        param_methods=[k for k, v in codecs.CODECS.items() if v[4] is not None],
        candidates=candidates, base_score=base_score,
        enabled_count=sum(1 for s in steps if s["on"]),
        user=user["username"] if user else None,
        saves=saves, history=history, history_count=history_count,
        history_block=HISTORY_BLOCK,
        message=message, message_bad=bad, here="/",
        symbols_enabled=app.config.get("SYMBOLS_ENABLED", False),
    )

# Integrate ai beautified templates 
def decorate(entry):
    """Add what the templates show: a readable chain and a local timestamp."""
    entry["chain"] = " → ".join(
        s.get("method", "?") + ("↑" if s.get("direction") == "encode" else "")
        for s in entry.get("steps", [])) or "—"
    entry["when"] = time.strftime("%d %b %H:%M", time.localtime(entry["created_at"]))
    return entry


# Saved results and history
@app.post("/saves/<int:entry_id>/delete")
def delete_save(entry_id):
    user = current_user()
    if user:
        # the user_id in the query is the authorisation check, not a filter
        db.delete_entry(user["id"], entry_id)
    return redirect("/")


@app.get("/history")
def history():
    return history_page()


@app.post("/history/clear")
def clear_history():
    user = current_user()
    if user:
        db.clear_history(user["id"])
    return redirect("/history")


def history_page(message=None, bad=False):
    user = current_user()
    items, total = [], 0
    if user:
        items = [decorate(e) for e in db.list_entries(user["id"], "history", db.HISTORY_LIMIT)]
        total = db.count_entries(user["id"], "history")
    return render_template("history.html", items=items, total=total,
                           user=user["username"] if user else None,
                           message=message, message_bad=bad, here="/history",
                           symbols_enabled=app.config.get("SYMBOLS_ENABLED", False))



if __name__ == "__main__":
    app.run(port=8000, debug=True)
