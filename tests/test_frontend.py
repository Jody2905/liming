"""The React front end: served safely, its API types up to date, and (with Playwright) working in a browser."""

import json
import os
import re
import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from liming.api import CSP, WEB, create_app

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine=engine)) as c:
        yield c


def test_the_built_app_is_served_with_a_strict_security_policy(client):
    r = client.get("/")
    assert r.status_code == 200 and '<div id="root">' in r.text
    assert r.headers["content-security-policy"] == CSP and "unsafe-inline" not in CSP
    assets = re.findall(r'(?:src|href)="(/static/[^"]+)"', r.text)
    assert any(a.endswith(".js") for a in assets) and any(a.endswith(".css") for a in assets)
    for asset in assets:
        got = client.get(asset)
        assert got.status_code == 200, asset
    js = client.get(next(a for a in assets if a.endswith(".js")))
    assert "javascript" in js.headers["content-type"]


def test_no_inline_code_that_the_policy_would_block():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    assert "<style" not in html and " style=" not in html


def test_react_code_never_inserts_raw_html():
    """React escapes text by default; this makes sure nobody switched that off."""
    for path in (FRONTEND / "src").rglob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        assert "dangerouslySetInnerHTML" not in text and "innerHTML" not in text, path.name


def test_the_front_ends_api_description_is_current():
    """The TypeScript types are generated from frontend/openapi.json; it must match the real API.
    If this fails: py -m liming openapi > frontend/openapi.json, then npm run api-types."""
    committed = json.loads((FRONTEND / "openapi.json").read_text(encoding="utf-8"))
    assert committed == create_app("sqlite://").openapi()


# ---- In a real browser (skipped unless Playwright and its Chromium are installed) -------------------------

@pytest.fixture
def liming_server(tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    from liming.__main__ import init_demo
    url = f"sqlite:///{tmp_path / 'browser.db'}"
    init_demo(url)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(url), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(5)


@pytest.fixture
def browser_page():
    required = os.environ.get("LIMING_REQUIRE_BROWSER") == "1"      # CI sets this: there it must run
    if required:
        import playwright.sync_api as sync_api
    else:
        sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:                    # pragma: no cover - browser not downloaded
            if required:
                raise
            pytest.skip(f"Chromium isn't available for Playwright: {e}")
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        yield pg
        browser.close()


def test_in_a_browser_answer_the_questions_then_edit_and_book(liming_server, browser_page):
    from playwright.sync_api import expect
    pg = browser_page
    pg.goto(liming_server + "#/register")
    pg.get_by_label("Your name").fill("Kemar")
    pg.get_by_label("Email").fill("kemar2@example.test")
    pg.get_by_label("Password").fill("a-long-passphrase")
    pg.get_by_role("button", name="Create account").click()

    next_ = pg.get_by_role("button", name="Next")
    expect(pg.get_by_role("heading", name="Where are we liming?")).to_be_visible()
    next_.click()
    expect(pg.get_by_role("alert")).to_have_text("Pick a country to start.")
    pg.get_by_text("Barbados", exact=True).click()
    for _ in range(4):
        next_.click()                                    # country chosen; dates, people and budget as they are
    pg.get_by_role("button", name="Food and drink: not picked").click()
    pg.get_by_role("button", name="Food and drink: like it").click()   # a second tap means "love"
    expect(pg.get_by_role("button", name="Food and drink: love it")).to_be_visible()
    for _ in range(5):
        next_.click()
    pg.get_by_label("Trip name").fill("Bajan food week")
    pg.get_by_role("button", name="Build my plan").click()
    expect(pg.get_by_role("heading", name="Bajan food week")).to_be_visible()
    expect(pg.locator(".stop .why").first).not_to_be_empty()

    first = pg.locator(".stop.kind-activity").first
    title = first.locator("h3").inner_text()
    first.get_by_role("button", name=f"Lock {title}").click()
    pg.get_by_role("button", name="Something different").click()
    expect(pg.locator(".toast", has_text="Something different")).to_be_visible()
    expect(pg.locator(".stop.locked h3", has_text=title)).to_be_visible()      # locked things stay put

    pg.get_by_role("button", name="Book the stay").click()
    expect(pg.locator(".stay .tag.booked")).to_contain_text("On hold")
    pg.get_by_role("button", name="Confirm stay").click()
    pg.locator("dialog.ask").get_by_role("button", name="Confirm booking").click()
    expect(pg.locator(".stay .tag.booked")).to_contain_text("Booked LIM-")
    assert pg.errors == []
