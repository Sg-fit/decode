"""Tests for the symbol library add-on. Delete alongside app/symbols.py."""

import importlib

import pytest

from app.symbols import decode, encode, tidy


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECODE_DATA", str(tmp_path))
    monkeypatch.setenv("DECODE_SECRET", "test-secret")
    from app import db as db_module
    importlib.reload(db_module)
    from app import symbols as sym_module
    importlib.reload(sym_module)
    from app import main as main_module
    importlib.reload(main_module)
    main_module.app.config["TESTING"] = True
    c = main_module.app.test_client()
    c.post("/api/register", json={"username": "loki", "password": "hunter2"})
    return c


SYMBOLS = [
    {"trigger": ";late", "value": "running late, be there soon"},
    {"trigger": ";ty", "value": "thank you"},
    {"trigger": "△", "value": "on my way"},
]


# --------------------------------------------------------------------------- #
# the codec
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    (";ty", "Thank you."),
    ("△", "On my way."),
    (";late ;ty", "Running late, be there soon thank you."),
    ("hey ;ty, see you", "Hey thank you, see you."),      # punctuation stays put
    ("nothing here", "Nothing here."),                    # unknown words untouched
])
def test_decode(raw, expected):
    assert decode(raw, SYMBOLS) == expected


def test_encode_swaps_phrases_back():
    assert encode("thank you", SYMBOLS) == ";ty"
    assert ";late" in encode("Running late, be there soon", SYMBOLS)


def test_encode_prefers_the_longer_phrase():
    syms = [{"trigger": ";a", "value": "see you"}, {"trigger": ";b", "value": "see you tomorrow"}]
    assert encode("see you tomorrow", syms) == ";b"


def test_tidy():
    assert tidy("  hello   world ") == "Hello world."
    assert tidy("already right!") == "Already right!"
    assert tidy("") == ""


# --------------------------------------------------------------------------- #
# rules — every one of them must keep the message the same length
# --------------------------------------------------------------------------- #
from app import rules as R

TEXTS = ["", "a", "Hello, World!", "12345", "café ünïcode",
         "the quick brown fox jumps over the lazy dog", "  spaced  out  "]


@pytest.mark.parametrize("key", list(R.RULES))
@pytest.mark.parametrize("text", TEXTS)
def test_every_rule_round_trips_and_keeps_length(key, text):
    coded = R.apply_rule(key, text, None, "encode")
    assert len(coded) == len(text)
    assert R.apply_rule(key, coded, None, "decode") == text


def test_chain_runs_backwards_to_decode():
    chain = [{"rule": "alphabet", "param": "qwertyuiopasdfghjklzxcvbnm"},
             {"rule": "keyword", "param": "kite"},
             {"rule": "railfence", "param": "3"},
             {"rule": "words"},
             {"rule": "reverse"}]
    for text in TEXTS:
        coded = R.run_chain(text, chain, "encode")
        assert len(coded) == len(text)
        assert R.run_chain(coded, chain, "decode") == text


def test_order_matters():
    a = [{"rule": "reverse"}, {"rule": "keyword", "param": "kite"}]
    b = [{"rule": "keyword", "param": "kite"}, {"rule": "reverse"}]
    assert R.run_chain("hello world", a, "encode") != R.run_chain("hello world", b, "encode")


@pytest.mark.parametrize("key,param", [
    ("alphabet", "abc"),            # not 26 letters
    ("alphabet", "aabcdefghijklmnopqrstuvwxy"),   # a repeat
    ("keyword", "1234"),            # no letters
    ("railfence", "1"),             # too few rails
    ("railfence", "many"),          # not a number
])
def test_bad_parameters_rejected(key, param):
    with pytest.raises(ValueError):
        R.apply_rule(key, "hello", param, "encode")


def test_unknown_rule_rejected():
    with pytest.raises(ValueError):
        R.apply_rule("enigma", "hello", None, "encode")


# --------------------------------------------------------------------------- #
# the page — plain forms
# --------------------------------------------------------------------------- #
def register(client, name="loki"):
    return client.post("/login", data={"username": name, "password": "hunter2",
                                       "action": "register"}, follow_redirects=True)


def html(response):
    return response.get_data(as_text=True)


def test_page_needs_login(client):
    assert "Log in on the" in html(client.get("/symbols"))


def test_add_edit_delete(client):
    register(client)
    client.post("/symbols/save", data={"trigger": ";late", "value": "late"},
                follow_redirects=True)
    body = html(client.get("/symbols"))
    assert ";late" in body and "late" in body

    # same trigger again overwrites instead of duplicating
    client.post("/symbols/save", data={"trigger": ";late", "value": "very late"},
                follow_redirects=True)
    from app.symbols import list_symbols
    rows = list_symbols(1)
    assert len(rows) == 1 and rows[0]["value"] == "very late"

    client.post(f"/symbols/{rows[0]['id']}/delete", follow_redirects=True)
    assert "No symbols yet" in html(client.get("/symbols"))


@pytest.mark.parametrize("form,expected", [
    ({"trigger": "two words", "value": "x"}, "one word"),
    ({"trigger": ";x", "value": ""}, "phrase must be"),
])
def test_bad_symbols_rejected(client, form, expected):
    register(client)
    assert expected in html(client.post("/symbols/save", data=form))


def test_seed_fills_the_library(client):
    register(client)
    client.post("/symbols/seed", follow_redirects=True)
    from app.symbols import STARTER, list_symbols
    assert len(list_symbols(1)) == len(STARTER)


def test_try_it_both_directions(client):
    register(client)
    client.post("/symbols/save", data={"trigger": ";ty", "value": "thank you"})
    body = html(client.post("/symbols/run", data={"text": ";ty", "direction": "decode"}))
    assert "Thank you." in body and "Recognised: ;ty" in body
    body = html(client.post("/symbols/run", data={"text": "thank you", "direction": "encode"}))
    assert ">;ty</textarea>" in body


def test_export_is_plain_text(client):
    register(client)
    client.post("/symbols/save", data={"trigger": ";ty", "value": "thank you"})
    r = client.get("/symbols/export")
    assert r.mimetype == "text/plain"
    assert ";ty\tthank you" in r.get_data(as_text=True)


def test_import_reads_the_text_file(client):
    import io
    register(client)
    pack = b"# a library\n;ty\tthank you\n;bye\ttalk soon\n\nbad line with no phrase\n"
    body = html(client.post("/symbols/import",
                            data={"pack": (io.BytesIO(pack), "lib.txt")},
                            content_type="multipart/form-data"))
    assert "Imported 2 symbols" in body


def test_import_rejects_a_file_with_nothing_in_it(client):
    import io
    register(client)
    body = html(client.post("/symbols/import",
                            data={"pack": (io.BytesIO(b"# just a comment\n"), "x.txt")},
                            content_type="multipart/form-data"))
    assert "no symbols in it" in body


def test_symbols_are_private(client):
    register(client, "loki")
    client.post("/symbols/save", data={"trigger": ";ty", "value": "thank you"})
    client.post("/logout", data={"next": "/symbols"})
    register(client, "mallory")
    assert "No symbols yet" in html(client.get("/symbols"))


def test_pattern_saves_and_reloads(client):
    register(client)
    body = html(client.post("/symbols/pattern", data={
        "rule": ["keyword", "reverse"], "param": ["kite", ""], "action": "save"}))
    assert "Pattern saved" in body
    from app.symbols import get_chain
    assert [s["rule"] for s in get_chain(1)] == ["keyword", "reverse"]


def test_broken_pattern_is_refused(client):
    register(client)
    body = html(client.post("/symbols/pattern", data={
        "rule": ["alphabet"], "param": ["not-an-alphabet"], "action": "save"}))
    assert "each of the 26 letters" in body
    from app.symbols import get_chain
    assert get_chain(1) == []


def test_pattern_rows_can_be_added_and_removed(client):
    register(client)
    body = html(client.post("/symbols/pattern", data={"action": "add"}))
    assert body.count('name="rule"') == 1
    body = html(client.post("/symbols/pattern", data={
        "rule": ["reverse"], "param": [""], "action": "del:0"}))
    assert 'name="rule"' not in body


def test_symbols_and_pattern_together(client):
    """Encode is symbols then rules; decode is exactly the reverse."""
    register(client)
    client.post("/symbols/save", data={"trigger": ";ty", "value": "thank you"})
    client.post("/symbols/pattern", data={
        "rule": ["keyword", "railfence"], "param": ["kite", "3"], "action": "save"})

    from app.symbols import list_symbols, get_chain, encode, decode
    from app import rules as R
    coded = R.run_chain(encode("thank you", list_symbols(1)), get_chain(1), "encode")
    assert coded != ";ty"
    plain = decode(R.run_chain(coded, get_chain(1), "decode"), list_symbols(1))
    assert plain == "Thank you."


def test_decoder_still_works(client):
    body = html(client.post("/", data={"text": "SGVsbG8=", "method": "base64",
                                       "dir": "decode", "on": "1", "param": "",
                                       "action": "run"}))
    assert "Hello" in body
