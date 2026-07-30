"""pytest (run from backend/)"""
import pytest

from app.codecs import CODECS, apply, detect, run, score

ENCODINGS = [k for k, v in CODECS.items() if v[3]]


@pytest.mark.parametrize("method", ENCODINGS)
@pytest.mark.parametrize("text", ["Hello World", "go the green door!", "ESAP 2026", "a b+c"])
def test_round_trip(method, text):
    encoded = apply(method, text, "encode")
    if encoded == text:
        pytest.skip("nothing to decode — this sample has no special characters")
    decoded = apply(method, encoded)
    assert decoded == text


@pytest.mark.parametrize("method,bad", [
    ("base64", "not base64!!"), ("hex", "zzzz"), ("binary", "012"),
    ("decimal", "abc"), ("url", "plain"),
])
def test_bad_input_rejected(method, bad):
    with pytest.raises(ValueError):
        apply(method, bad)


def test_caesar():
    assert apply("caesar", "Attack at dawn!", "encode", "3") == "Dwwdfn dw gdzq!"
    assert apply("caesar", "Dwwdfn dw gdzq!", "decode", "3") == "Attack at dawn!"
    assert apply("caesar", "Hello", "encode", "13") == apply("caesar", "Hello", "decode", "13")
    assert apply("caesar", "abc", "encode") == "def"          # default shift of 3
    assert apply("caesar", "z A 9!", "encode", "1") == "a B 9!"  # wraps, keeps case & symbols
    with pytest.raises(ValueError):
        apply("caesar", "abc", "encode", "banana")


def test_detect_finds_caesar_shift():
    _, candidates = detect("Dwwdfn dw gdzq")
    assert candidates[0]["method"] == "caesar"
    assert candidates[0]["param"] == "3"
    assert candidates[0]["output"] == "Attack at dawn"


def test_pipeline_passes_param():
    out, _ = run("Dwwdfn", [{"method": "caesar", "param": "3"}])
    assert out == "Attack"


@pytest.mark.parametrize("raw,expected", [
    ("72 101 121", "Hey"),               # space separated
    ("72,101,108,108,111", "Hello"),     # commas
    ("72-101-108", "Hel"),               # dashes
    ("72\n101\n108", "Hel"),            # newlines
    ("104101108108111", "hello"),        # run together, 3-digit groups
    ("072101121", "Hey"),                # zero padded
])
def test_decimal_shapes(raw, expected):
    assert apply("decimal", raw) == expected


@pytest.mark.parametrize("bad", ["1234", "99999999999", "abc"])
def test_decimal_rejects_plain_numbers(bad):
    # a bare number that doesn't land on printable characters isn't ASCII
    with pytest.raises(ValueError):
        apply("decimal", bad)


@pytest.mark.parametrize("raw,winner", [
    ("72 101 108 108 111", "decimal"),   # 3-digit groups can't be hex bytes
    ("104101108108111", "decimal"),
    ("48 69", "hex"),                    # 2-digit groups: hex still wins on merit
    ("01001000 01101001", "binary"),     # 8-digit groups are binary
    ("SGVsbG8gV29ybGQ=", "base64"),
])
def test_detect_picks_the_right_numeric_codec(raw, winner):
    _, candidates = detect(raw)
    assert candidates[0]["method"] == winner


def test_unknown_method():
    with pytest.raises(ValueError):
        apply("vigenere", "abc")


def test_score_prefers_plaintext():
    assert score("the quick brown fox") > score("k3j2\x00\xff9d")


def test_detect_ranks_base64_first():
    _, candidates = detect("SGVsbG8gV29ybGQ=")
    assert candidates[0]["method"] == "base64"
    assert candidates[0]["output"] == "Hello World"


def test_pipeline_chains():
    out, results = run("Njc2ZjIwNzQ2ODY1MjA2NzcyNjU2NTZlMjA2NDZmNmY3MjIx",
                       [{"method": "base64"}, {"method": "hex"}])
    assert out == "go the green door!"
    assert not any("error" in r for r in results)


def test_failing_step_passes_input_through():
    out, results = run("Hello", [{"method": "hex"}])
    assert results[0]["error"] and out == "Hello"


def test_auto_step():
    assert run("SGVsbG8=", [{"method": "auto"}])[0] == "Hello"


def test_disabled_step_skipped():
    out, results = run("Hello", [{"method": "base64", "direction": "encode", "enabled": False}])
    assert out == "Hello" and results[0]["skipped"]


# --------------------------------------------------------------------------- #
# the pages — plain forms, so every test posts a form and reads the HTML back
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A fresh app + throwaway database per test."""
    monkeypatch.setenv("DECODE_DATA", str(tmp_path))
    monkeypatch.setenv("DECODE_SECRET", "test-secret")
    import importlib
    from app import db as db_module
    importlib.reload(db_module)
    from app import main as main_module
    importlib.reload(main_module)
    main_module.app.config["TESTING"] = True
    return main_module.app.test_client()


def html(response):
    return response.get_data(as_text=True)


def register(client, name="loki", password="hunter2"):
    return client.post("/login", data={"username": name, "password": password,
                                       "action": "register"}, follow_redirects=True)


def test_decoder_page_loads(client):
    body = html(client.get("/"))
    assert "Decoder" in body and "Pipeline" in body


def test_run_a_step(client):
    body = html(client.post("/", data={
        "text": "SGVsbG8gV29ybGQ=", "method": "base64", "dir": "decode",
        "on": "1", "param": "", "action": "run"}))
    assert "Hello World" in body


def test_step_error_is_shown_not_raised(client):
    body = html(client.post("/", data={
        "text": "Hello", "method": "hex", "dir": "decode",
        "on": "1", "param": "", "action": "run"}))
    assert "not hex" in body


def test_add_and_delete_a_step(client):
    body = html(client.post("/", data={"text": "hi", "action": "add"}))
    assert body.count('name="method"') == 1
    body = html(client.post("/", data={
        "text": "hi", "method": "base64", "dir": "decode", "on": "1",
        "param": "", "action": "del:0"}))
    assert 'name="method"' not in body


def test_toggling_a_step_skips_it(client):
    body = html(client.post("/", data={
        "text": "SGVsbG8=", "method": "base64", "dir": "decode", "on": "1",
        "param": "", "action": "toggle:0"}))
    assert "(skipped)" in body


def test_reordering_steps(client):
    data = {"text": "hi",
            "method": ["base64", "hex"], "dir": ["decode", "decode"],
            "on": ["1", "1"], "param": ["", ""], "action": "up:1"}
    body = html(client.post("/", data=data))
    # hex is now the first select
    assert body.index('value="hex" selected') < body.index('value="base64" selected')


def test_detect_offers_candidates(client):
    body = html(client.post("/", data={"text": "SGVsbG8gV29ybGQ=", "action": "detect"}))
    assert "Candidates" in body and "Base64" in body and "Hello World" in body


def test_using_a_candidate_adds_the_step(client):
    body = html(client.post("/", data={"text": "SGVsbG8=", "action": "use:base64:"}))
    assert "Hello" in body and 'value="base64" selected' in body


def test_caesar_candidate_carries_its_shift(client):
    body = html(client.post("/", data={"text": "Dwwdfn dw gdzq", "action": "use:caesar:3"}))
    assert "Attack at dawn" in body


def test_sample_and_clear(client):
    body = html(client.post("/", data={"action": "sample"}))
    assert "Njc2ZjIw" in body
    body = html(client.post("/", data={"text": "leftovers", "action": "clear"}))
    assert "leftovers" not in body


def test_use_output_as_input(client):
    body = html(client.post("/", data={
        "text": "SGVsbG8=", "method": "base64", "dir": "decode", "on": "1",
        "param": "", "action": "feed"}))
    assert ">Hello</textarea>" in body


def test_download_returns_a_file(client):
    r = client.post("/", data={
        "text": "SGVsbG8=", "method": "base64", "dir": "decode", "on": "1",
        "param": "", "filename": "out.txt", "action": "download"})
    assert r.data == b"Hello" and "out.txt" in r.headers["Content-Disposition"]


def test_upload_a_file(client):
    import io
    r = client.post("/", data={
        "text": "", "method": "base64", "dir": "decode", "on": "1", "param": "",
        "action": "run", "upload": (io.BytesIO(b"SGVsbG8="), "note.txt")},
        content_type="multipart/form-data")
    assert "Hello" in html(r)


def test_register_login_logout(client):
    assert "user: <b>loki</b>" in html(register(client))
    assert "Log out" in html(client.get("/"))

    assert "taken" in html(register(client))                     # same name again
    client.post("/logout", data={"next": "/"}, follow_redirects=True)
    assert "Log out" not in html(client.get("/"))

    bad = client.post("/login", data={"username": "loki", "password": "nope"})
    assert "wrong username or password" in html(bad)
    ok = client.post("/login", data={"username": "loki", "password": "hunter2"},
                     follow_redirects=True)
    assert "user: <b>loki</b>" in html(ok)


def test_weak_credentials_rejected(client):
    assert "3-32" in html(register(client, "a"))
    assert "at least 6" in html(register(client, "loki", "12"))


def test_save_requires_login(client):
    assert "log in to save" in html(client.post("/", data={"text": "hi", "action": "save"}))


def test_save_and_delete(client):
    register(client)
    body = html(client.post("/", data={
        "text": "SGVsbG8=", "method": "base64", "dir": "decode", "on": "1",
        "param": "", "savename": "flag", "action": "save"}))
    assert "Saved." in body and "flag" in body

    from app import db as db_module
    entry = db_module.list_entries(1, "save")[0]
    body = html(client.post(f"/saves/{entry['id']}/delete", follow_redirects=True))
    assert "Nothing saved yet" in body


def test_history_records_and_shows_a_block(client):
    from app import db as db_module
    from app.main import HISTORY_BLOCK
    register(client)
    for i in range(HISTORY_BLOCK + 3):
        client.post("/", data={"text": f"SGVsbG8{i}=", "method": "base64",
                               "dir": "decode", "on": "1", "param": "", "action": "run"})
    assert db_module.count_entries(1, "history") == HISTORY_BLOCK + 3
    assert f"{HISTORY_BLOCK} of {HISTORY_BLOCK + 3}" in html(client.get("/"))

    full = html(client.get("/history"))
    assert full.count("base64") >= HISTORY_BLOCK + 3

    client.post("/history/clear", follow_redirects=True)
    assert "No runs yet" in html(client.get("/history"))


def test_history_skips_a_repeat(client):
    from app import db as db_module
    register(client)
    for _ in range(3):
        client.post("/", data={"text": "SGVsbG8=", "method": "base64",
                               "dir": "decode", "on": "1", "param": "", "action": "run"})
    assert db_module.count_entries(1, "history") == 1


def test_saves_are_private(client):
    register(client, "loki")
    client.post("/", data={"text": "hi", "method": "base64", "dir": "decode",
                           "on": "1", "param": "", "savename": "mine", "action": "save"})
    client.post("/logout", data={"next": "/"})
    register(client, "mallory")
    assert "mine" not in html(client.get("/"))


def test_history_page_needs_login(client):
    assert "Log in on the" in html(client.get("/history"))
