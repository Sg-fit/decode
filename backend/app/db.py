"""SQLite storage: accounts, saved results, run history — written in pandas.
"""

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
import pandas as pd

DATA_DIR = Path(os.environ.get("DECODE_DATA", Path(__file__).resolve().parents[1] / "data"))
DB_PATH = DATA_DIR / "decode.db"

HISTORY_LIMIT = 50      # oldest history rows are dropped past this

# column name -> SQL type, so pandas creates the tables with sensible types
USERS = {"id": "INTEGER", "username": "TEXT", "password_hash": "TEXT",
         "created_at": "REAL"}
ENTRIES = {"id": "INTEGER", "user_id": "INTEGER", "kind": "TEXT", "name": "TEXT",
           "input": "TEXT", "steps": "TEXT", "output": "TEXT", "created_at": "REAL"}


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row      # so symbols.py can read rows as row["name"]
    return con


# Constructing basic methods 
def load(table):
    """The whole table as a DataFrame."""
    con = connect()
    frame = pd.read_sql_query(f"SELECT * FROM {table}", con)
    con.close()
    return frame


def append(table, row, columns):
    """Add one row."""
    con = connect()
    pd.DataFrame([row]).to_sql(table, con, if_exists="append", index=False, dtype=columns)
    con.close()


def replace(table, frame, columns):
    """Write the table back, dropping whatever was there."""
    con = connect()
    frame.to_sql(table, con, if_exists="replace", index=False, dtype=columns)
    con.close()


# create both tables on import
DATA_DIR.mkdir(parents=True, exist_ok=True)
for table_name, table_columns in (("users", USERS), ("entries", ENTRIES)):
    con = connect()
    pd.DataFrame(columns=list(table_columns)).to_sql(
        table_name, con, if_exists="append", index=False, dtype=table_columns)
    con.close()


def to_dicts(frame):
    """DataFrame -> list of plain dicts.
    """
    rows = frame.to_dict("records")
    for row in rows:
        for key, value in row.items():
            if value is None or pd.isna(value):
                row[key] = None
            elif hasattr(value, "item"):
                row[key] = value.item()
    return rows


def next_id(frame):
    """pandas writes plain columns, so ids are counted"""
    return 1 if frame.empty else int(frame["id"].max()) + 1



def create_user(username, password_hash):
    """Add a user and return their id, or None if the name is taken."""
    users = load("users")
    if not users.empty and (users["username"].str.lower() == username.lower()).any():
        return None

    new_id = next_id(users)
    append("users", {"id": new_id, "username": username,
                     "password_hash": password_hash, "created_at": time.time()}, USERS)
    return new_id


def find_user(username):
    """Names are matched without case"""
    users = load("users")
    if users.empty:
        return None
    found = users[users["username"].str.lower() == username.lower()]
    return to_dicts(found)[0] if not found.empty else None

#find the username and data using user id 
def user_by_id(user_id):
    users = load("users")
    found = users[users["id"] == user_id] if not users.empty else users
    return to_dicts(found)[0] if not found.empty else None


# saved results and history

def add_entry(user_id, kind, text, steps, output, name=None):
    """Save a result or record a run, and return the new row."""
    entries = load("entries")
    new_id = next_id(entries)
    append("entries", {"id": new_id, "user_id": user_id, "kind": kind, "name": name,
                       "input": text, "steps": json.dumps(steps), "output": output,
                       "created_at": time.time()}, ENTRIES)
#all of the parameters are recorded
    if kind == "history":
        trim_history(user_id)

    entries = load("entries")
    return read_entries(entries[entries["id"] == new_id])[0]

#for the sake of storage, trim the history down 
def trim_history(user_id):
    """Keep only this user's newest history rows."""
    entries = load("entries")
    mine = entries[(entries["user_id"] == user_id) & (entries["kind"] == "history")]
    if len(mine) <= HISTORY_LIMIT:
        return
    # newest first, then everything past the limit is the part to drop
    extra = mine.sort_values("id", ascending=False)["id"].iloc[HISTORY_LIMIT:]
    replace("entries", entries[~entries["id"].isin(extra)], ENTRIES)

#loading all of the history out 
def list_entries(user_id, kind, limit=50):
    """Newest first."""
    entries = load("entries")
    if entries.empty:
        return []
    mine = entries[(entries["user_id"] == user_id) & (entries["kind"] == kind)]
    return read_entries(mine.sort_values("id", ascending=False).head(limit))

#for convenience, using json here 
def read_entries(frame):
    """Rows as dicts, with the stored JSON turned back into a list of steps."""
    rows = to_dicts(frame)
    for row in rows:
        row["steps"] = json.loads(row["steps"])
    return rows


def last_entry(user_id, kind):
    rows = list_entries(user_id, kind, 1)
    return rows[0] if rows else None


def count_entries(user_id, kind):
    entries = load("entries")
    if entries.empty:
        return 0
    return int(((entries["user_id"] == user_id) & (entries["kind"] == kind)).sum())


def delete_entry(user_id, entry_id):
    """True if a row was removed. """
    entries = load("entries")
    if entries.empty:
        return False
    doomed = (entries["id"] == entry_id) & (entries["user_id"] == user_id)
    if not doomed.any():
        return False
    replace("entries", entries[~doomed], ENTRIES)
    return True


def clear_history(user_id):
    entries = load("entries")
    if entries.empty:
        return
    doomed = (entries["user_id"] == user_id) & (entries["kind"] == "history")
    replace("entries", entries[~doomed], ENTRIES)


#using cookies js to keep the users logged in and the data recorded 
def secret_key():
    """Flask signs session cookies with this."""
    if os.environ.get("DECODE_SECRET"):
        return os.environ["DECODE_SECRET"]

    path = DATA_DIR / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text()
