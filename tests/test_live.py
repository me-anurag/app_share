"""Live updates and speed: open screens update by themselves within seconds; files are compressed and cached.

  python -m tests.test_live      (throwaway server on port 8769; needs Playwright + Chrome, otherwise skipped)
"""
import os
import subprocess
import sys
import tempfile
import time

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIPPED: Playwright is not installed")
        return 0
    import httpx
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = "http://127.0.0.1:8769"
    tmp = tempfile.mkdtemp(prefix="appshare-live-")
    env = {**os.environ, "APPSHARE_DATA": tmp, "APPSHARE_MODE": "university", "ANTHROPIC_API_KEY": "", "PYTHONIOENCODING": "utf-8"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8769", "--log-level", "warning"],
                           cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                if httpx.get(base + "/api/ping", timeout=2).status_code == 200:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        print("Speed:")
        page = httpx.get(base + "/login").text
        stamped = [s for s in __import__("re").findall(r'"(/static/[^"]+\?v=[0-9a-f]+)"', page)]
        expect(len(stamped) >= 2, f"pages link their files with version stamps ({len(stamped)} found)")
        r = httpx.get(base + stamped[0], headers={"Accept-Encoding": "gzip"})
        expect(r.headers.get("content-encoding") == "gzip", "files are sent compressed (gzip)")
        expect("immutable" in r.headers.get("cache-control", ""), "stamped files are cached long-term")
        expect(httpx.get(base + "/api/apps", headers={"Accept-Encoding": "gzip"}).status_code in (200, 401), "API still answers with compression on")

        import re as _re
        cj = open(os.path.join(root, "frontend", "common.js"), encoding="utf-8").read()
        sw = open(os.path.join(root, "frontend", "sw.js"), encoding="utf-8").read()
        av = _re.search(r'const APP_VERSION = "(v\d+)"', cj)
        sv = _re.search(r'const VERSION = "appshare-(v\d+)"', sw)
        expect(av and sv and av.group(1) == sv.group(1), f"the app shows the same version its offline cache uses ({av.group(1) if av else '?'} / {sv.group(1) if sv else '?'})")
        expect("AppShare " in httpx.get(base + "/static/common.js").text and "versionLine()" in httpx.get(base + "/login").text,
               "the version is shown on the sign-in page and in the profile sheet")

        print("Live updates (pushed, no refresh):")
        owner = httpx.Client(base_url=base, timeout=30)
        owner.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
        apps = owner.get("/api/apps").json()
        app = next(a for a in (apps.get("mine") if isinstance(apps, dict) else apps) if a.get("status") == "published")
        detail = owner.get(f"/api/a/{app['slug']}").json()
        student = httpx.Client(base_url=base, timeout=30)
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel="chrome", headless=True)
            except Exception as e:  # noqa: BLE001
                print(f"SKIPPED: Chrome not available ({type(e).__name__})")
                return 0
            pg = b.new_context(viewport={"width": 400, "height": 860}, is_mobile=True).new_page()
            pg.request.post(base + "/api/login", data={"email": "dr.mehta@riverside.edu"})
            pg.goto(base + f"/manage/{app['id']}")
            pg.wait_for_selector(".utabs", timeout=20000)
            pg.wait_for_timeout(1500)
            before = pg.inner_text("#pane")
            # a status change by the owner in another tab must show here too: use a response from a student
            who = next((p_["email"] for p_ in owner.get(f"/api/apps/{app['id']}/responses").json().get("missing", [])), None)
            if who:
                student.post("/api/login", json={"email": who}).raise_for_status()
                fields = [f for f in detail["spec"]["fields"] if f["type"] not in ("info", "file", "checkbox")]
                data = {f["id"]: (f.get("options") or ["x"])[0] if f["type"] in ("radio", "select") else ("3" if f["type"] in ("number", "rating") else "Live test") for f in fields}
                t0 = time.time()
                code = student.post(f"/api/a/{app['slug']}/submit", data=data).status_code
                took = None
                for _ in range(40):
                    pg.wait_for_timeout(100)
                    if pg.inner_text("#pane") != before:
                        took = time.time() - t0
                        break
                expect(code == 200 and took is not None and took < 2.0, f"the owner's open page updated by itself {'in %.1f s' % took if took else '— NOT within 4 s'}")
            pg.goto(base + "/")
            pg.wait_for_timeout(1500)
            n0 = pg.evaluate("document.querySelector('[data-inbox-n]')?.textContent || '0'")
            t0 = time.time()
            owner.post(f"/api/apps/{app['id']}/share", json={"entries": [], "link_access": "org", "publish": True})   # a change that bumps
            import sqlite3
            db = sqlite3.connect(os.path.join(tmp, "university", "appshare.db"))
            uid = db.execute("SELECT id FROM users WHERE email = 'dr.mehta@riverside.edu'").fetchone()[0]
            db.execute("INSERT INTO notifications (user_id, kind, title, body) VALUES (?, 'response', 'Live test', 'x')", (uid,))
            db.commit()
            db.close()
            owner.post(f"/api/apps/{app['id']}/share", json={"entries": [], "link_access": "org", "publish": True})
            took = None
            for _ in range(40):
                pg.wait_for_timeout(100)
                if pg.evaluate("document.querySelector('[data-inbox-n]')?.textContent || '0'") != n0:
                    took = time.time() - t0
                    break
            expect(took is not None and took < 2.0, f"the notification count updated by itself {'in %.1f s' % took if took else '— NOT within 4 s'}")
            b.close()
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:  # noqa: BLE001
            srv.kill()
    print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
