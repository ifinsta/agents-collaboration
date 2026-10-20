"""Optional real-browser acceptance check. Requires Playwright and an installed Edge.

Run from the repository root: python scripts/validate_canvas.py --output DIR
Uses disposable Git boards and a temporary dashboard home; starts no agent CLI.
Playwright is a validation dependency only, not an installed skill dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def source_hashes():
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "skills/agents-collaboration/swarm_web.py",
            "skills/agents-collaboration/swarm_sessions.py",
            "skills/agents-collaboration/swarm_core.py",
            "tests/test_web_dashboard.py",
            "tests/test_swarm.py",
            "tests/test_hardening.py",
            "scripts/validate_canvas.py",
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--channel", default="msedge", help="Installed Chromium browser channel")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    from test_web_dashboard import Shared, fixtures, swarm_web

    args.output.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    case = Shared("test_every_registered_board_is_listed_and_selected_with_b")
    case.setUp()
    checks = []
    try:
        case.join("cy")
        case.join("drew")
        with case.board() as sw:
            swarm_web.register(sw, "python swarm.py", str(fixtures.SWARM))
        case.to_ready("bob", "T1", "src/proof.txt")
        case.sw("--as", "cy", "claim", "T2")
        case.sw("--as", "cy", "send", "bob", "Please review this boundary", "--kind", "review_request")
        with case.board() as sw, sw.tx():
            sw.db.execute("INSERT INTO incidents(task,subject,opened_by,signal,state,revision,created_at) VALUES('T1','bob','ann','a signal','open',1,'2026-01-01T00:00:00+00:00')")
            sw.db.execute("UPDATE agents SET reviewing=1 WHERE name='drew'")
        other = case.other_board()
        mine = case.api("/api/team")["active"]["id"]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=args.channel, headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(f"http://127.0.0.1:{case.port}/?t={case.server.token}#/team", wait_until="networkidle")
            expect(page.locator(".node")).to_have_count(7)
            board = page.get_by_role("region", name="Team canvas", exact=True)
            zoom = page.get_by_label("Canvas zoom", exact=True)
            page.evaluate("""() => {
                window.mounted = Object.fromEntries(['#app', 'header.top', 'main', '.board', '.canvas-stage', '.canvas-plane', '.canvas-controls', '.canvas-find input', 'aside'].map(s => [s, document.querySelector(s)]));
                window.originalCards = new Map([...document.querySelectorAll('[data-node]')].map(el => [el.dataset.node, el]));
                window.originalEdges = new Map([...document.querySelectorAll('.canvas-edges > path')].map(el => [el.getAttribute('data-edge'), el]));
            }""")
            page.locator('[data-node="bob"]').click()
            expect(page.get_by_role("complementary", name="Selected participant")).to_contain_text("Bob")
            assert page.evaluate("Object.entries(window.mounted).every(([s, el]) => document.querySelector(s) === el)")
            paths = page.locator(".canvas-edges > path")
            assert paths.count() == len(case.api("/api/team")["edges"])
            assert all(" C " in d or " Q " in d for d in paths.evaluate_all("els => els.map(el => el.getAttribute('d'))"))
            assert page.evaluate("""() => [...document.querySelectorAll('.canvas-edges > path')].every(path => {
                const [kind, from, to] = JSON.parse(path.getAttribute('data-edge'));
                const bounds = id => {
                    const el = [...document.querySelectorAll('[data-node]')].find(el => el.dataset.node === id);
                    return ['left','top','width','height'].map(key => parseFloat(el.style[key]));
                };
                const touches = (p, b) => {
                    const [x,y,w,h] = b;
                    return p.x >= x-3 && p.x <= x+w+3 && p.y >= y-3 && p.y <= y+h+3 && Math.min(Math.abs(p.x-x),Math.abs(p.x-x-w),Math.abs(p.y-y),Math.abs(p.y-y-h)) <= 3;
                };
                const a = path.getPointAtLength(0), b = path.getPointAtLength(path.getTotalLength());
                return kind === 'collab' ? (touches(a,bounds(from)) || touches(a,bounds(to))) && (touches(b,bounds(from)) || touches(b,bounds(to))) : touches(a,bounds(from)) && touches(b,bounds(to)) && !!path.getAttribute('marker-end');
            })""")
            assert page.locator(".canvas-plane polyline").count() == 0
            page.screenshot(path=str(args.output / "canvas-1440.png"), full_page=True)
            initial = int(zoom.inner_text().rstrip("%"))
            page.get_by_role("button", name="Zoom in", exact=True).click()
            assert int(zoom.inner_text().rstrip("%")) > initial
            page.get_by_role("button", name="Reset zoom to 100% (0)", exact=True).click()
            expect(zoom).to_have_text("100%")
            page.get_by_role("button", name="Zoom in", exact=True).click(click_count=3, delay=50)
            box = board.bounding_box()
            start = board.evaluate("el => [el.scrollLeft, el.scrollTop]")
            page.mouse.move(box["x"] + 22, box["y"] + 220)
            page.mouse.down()
            page.mouse.move(box["x"] + 8, box["y"] + 100, steps=8)
            page.mouse.up()
            end = board.evaluate("el => [el.scrollLeft, el.scrollTop]")
            assert end[1] > start[1], (start, end)
            camera = (zoom.inner_text(), end)
            page.evaluate("""() => {
                window.cardMutations = [];
                window.cardWatcher = new MutationObserver(records => records.forEach(r => {
                    const el = r.target.nodeType === Node.TEXT_NODE ? r.target.parentElement : r.target;
                    const card = el.closest('[data-node]'); if (card) window.cardMutations.push(card.dataset.node);
                }));
                window.cardWatcher.observe(document.querySelector('.canvas-cards'), {childList:true, subtree:true, attributes:true, characterData:true});
            }""")
            # A real server-side change guarantees an update; only Bob and the gate change visually.
            case.sw("--as", "cy", "send", "bob", "A second boundary note", "--kind", "experience")
            with case.board() as sw, sw.tx():
                sw.db.execute("UPDATE tasks SET state='running' WHERE id='T1'")
            page.wait_for_timeout(3600)
            expect(page.locator('[data-node="bob"]')).to_contain_text("Working")
            assert (zoom.inner_text(), board.evaluate("el => [el.scrollLeft, el.scrollTop]")) == camera
            assert page.evaluate("Object.entries(window.mounted).every(([s, el]) => document.querySelector(s) === el)")
            assert page.evaluate("[...window.originalCards].every(([id, el]) => document.querySelector('[data-node=\"' + id + '\"]') === el)")
            assert set(page.evaluate("window.cardMutations")) == {"bob", "gate"}
            assert page.evaluate("[...document.querySelectorAll('.canvas-edges > path')].every(el => window.originalEdges.get(el.getAttribute('data-edge')) === el)")
            expect(page.get_by_role("complementary", name="Selected participant")).to_contain_text("Working")
            page.evaluate("window.cardWatcher.disconnect()")
            checks.append("live update retains shell, canvas, controls, card and surviving connector elements; only Bob/gate cards mutate")
            checks.append("smooth curves for every factual relationship, with directional arrowheads; camera retained through live update")

            board.focus()
            board.press("f")
            assert int(zoom.inner_text().rstrip("%")) < 100
            board.press("0")
            expect(zoom).to_have_text("100%")
            board.press("+")
            expect(zoom).to_have_text("120%")
            board.press("-")
            expect(zoom).to_have_text("100%")
            box = board.bounding_box()
            page.mouse.move(box["x"] + 100, box["y"] + 120)
            page.keyboard.down("Control")
            page.mouse.wheel(0, -90)
            page.keyboard.up("Control")
            assert int(zoom.inner_text().rstrip("%")) > 100
            checks.append("canvas keyboard shortcuts and Ctrl+wheel zoom")

            search = page.get_by_role("searchbox", name="Find on canvas")
            search.fill("cy")
            expect(page.locator(".canvas-count")).to_have_text("1 match")
            search.press("Enter")
            expect(page).to_have_url(re.compile(r"#/team/cy$"))
            expect(page.get_by_role("complementary", name="Selected participant")).to_contain_text("Cy")
            page.get_by_role("button", name="Focus on selected participant and neighbours").click()
            expect(page.locator(".node.quiet")).not_to_have_count(0)
            search.fill("no such participant")
            expect(page.locator(".canvas-count")).to_have_text("0 matches")
            search.press("Enter")
            search.press("Escape")
            expect(search).to_have_value("")
            expect(board).to_be_focused()
            page.get_by_role("button", name="Focus on selected participant and neighbours").click()
            page.get_by_role("button", name="Fit team to screen (F)").click()
            before_lines = page.locator(".canvas-edges > path").count()
            page.get_by_role("button", name="Hide accountability lines", exact=True).click()
            assert page.locator(".canvas-edges > path").count() < before_lines
            page.get_by_role("button", name="Show accountability lines", exact=True).click()
            assert page.locator(".canvas-edges > path").count() == before_lines
            # Relationship links navigate the selected participant, not an invented graph.
            page.get_by_role("complementary", name="Selected participant").get_by_role("link", name="Ann", exact=False).click()
            expect(page).to_have_url(re.compile(r"#/team/ann$"))
            checks.append("search, no-result handling, focus, edge filters and inspector relationship navigation")

            page.get_by_role("button", name="Fit team to screen (F)").click()
            page.locator('[data-node="steward"]').click()
            agent_name = page.get_by_role("textbox", name="Agent name", exact=True)
            agent_name.fill("audit-worker")
            page.get_by_role("combobox", name="Agent CLI", exact=True).select_option("codex")
            page.evaluate("window.reviewerInput = document.querySelector('[aria-label=\"Agent name\"]')")
            board.focus()
            case.sw("--as", "cy", "send", "bob", "Keep the draft while refreshing", "--kind", "experience")
            page.wait_for_timeout(3400)
            assert page.evaluate("window.reviewerInput === document.querySelector('[aria-label=\"Agent name\"]')")
            expect(agent_name).to_have_value("audit-worker")
            expect(page.get_by_role("combobox", name="Agent CLI", exact=True)).to_have_value("codex")
            page.get_by_role("button", name="Review inboxes now", exact=True).click()
            expect(page.locator(".toast")).to_have_text("Inboxes reviewed.")
            expect(agent_name).to_have_value("audit-worker")
            assert page.evaluate("window.reviewerInput === document.querySelector('[aria-label=\"Agent name\"]')")
            checks.append("steward form and selected CLI survive live updates and a successful local inbox-review action")

            page.locator('[data-node="bob"]').click()
            expect(page.locator('[data-node="bob"] [role="progressbar"]')).to_have_attribute("aria-valuenow", "2")
            expect(page.locator('[data-node="bob"] [role="progressbar"]')).to_have_attribute("aria-valuemax", "2")
            # Untrusted API display text remains literal even in highlighted/search cards.
            def hostile(route):
                response = route.fetch()
                data = response.json()
                for node in data["nodes"]:
                    if node["id"] == "bob":
                        node["name"] = '<img src=x onerror="window.injected=1">'
                route.fulfill(response=response, json=data)

            page.route("**/api/team*", hostile)
            page.reload(wait_until="networkidle")
            expect(page.locator('[data-node="bob"]')).to_contain_text("<img src=x")
            assert page.locator(".node img").count() == 0
            assert page.evaluate("window.injected === undefined")
            page.unroute("**/api/team*", hostile)
            page.reload(wait_until="networkidle")
            checks.append("recorded step progress and untrusted display text under the production CSP")

            page.get_by_role("button", name="Reset zoom to 100% (0)").click()
            page.get_by_role("button", name="Zoom in", exact=True).click()
            page.get_by_role("combobox", name="Board", exact=True).select_option(other["id"])
            expect(page.locator(".node")).to_have_count(3)
            assert zoom.inner_text() != "120%"
            page.get_by_role("combobox", name="Board", exact=True).select_option(mine)
            expect(page.locator(".node")).to_have_count(7)
            expect(zoom).to_have_text("120%")
            checks.append("separate cameras per board, restored on return")

            dimensions = []
            for width in (1440, 1024, 820, 600, 390):
                page.set_viewport_size({"width": width, "height": 1000})
                page.get_by_role("button", name="Fit team to screen (F)").click()
                assert not page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"), width
                assert board.bounding_box()["height"] >= 200, (width, board.bounding_box())
                assert page.get_by_role("button", name="Focus on selected participant and neighbours").is_visible()
                dimensions.append(width)
                if width in (1440, 390):
                    page.screenshot(path=str(args.output / f"canvas-{width}.png"), full_page=True)
            # Phone starts at readable 100%, with native touch scrolling rather than a tiny whole graph.
            mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            phone = mobile.new_page()
            phone.on("pageerror", lambda e: errors.append(str(e)))
            phone.goto(f"http://127.0.0.1:{case.port}/?t={case.server.token}#/team/bob", wait_until="networkidle")
            expect(phone.get_by_label("Canvas zoom", exact=True)).to_have_text("100%")
            assert phone.locator(".node").count() == 7
            assert phone.get_by_role("button", name="Fit team to screen (F)").is_visible()
            phone.screenshot(path=str(args.output / "canvas-phone.png"), full_page=True)
            mobile.close()
            checks.append("responsive layout without horizontal page overflow at " + ", ".join(map(str, dimensions)) + "px; touch phone starts at 100%")
            assert not errors, errors
            browser.close()
        after = source_hashes()
        assert before == after, "Source changed during browser validation"
        report = {"ok": True, "browser": args.channel, "source_sha256": before, "checks": checks, "browser_errors": errors}
        (args.output / "browser.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        case.tearDown()


if __name__ == "__main__":
    main()
