"""UI smoke test: the phone app and the Control Center load and render without script errors.

  python -m tests.test_ui_smoke

Phone pages run on a throwaway server (port 8767, seeded data, no API key). The Control Center tabs are checked
only if it is running on this laptop (port 7000); otherwise that part is skipped. Needs Playwright + Chrome.
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
    tmp = tempfile.mkdtemp(prefix="appshare-ui-")
    env = {**os.environ, "APPSHARE_DATA": tmp, "APPSHARE_MODE": "university", "ANTHROPIC_API_KEY": "", "PYTHONIOENCODING": "utf-8"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8767", "--log-level", "warning"],
                           cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                if httpx.get("http://127.0.0.1:8767/api/ping", timeout=2).status_code == 200:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel="chrome", headless=True)
            except Exception as e:  # noqa: BLE001
                print(f"SKIPPED: Chrome not available ({type(e).__name__})")
                return 0
            ctx = b.new_context(viewport={"width": 400, "height": 860}, is_mobile=True)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.request.post("http://127.0.0.1:8767/api/login", data={"email": "dr.mehta@riverside.edu"})
            apps = pg.request.get("http://127.0.0.1:8767/api/apps").json()
            first = (apps.get("mine") or apps.get("apps") or [{}])[0] if isinstance(apps, dict) else apps[0]
            print("Phone app:")
            for path, sel, what in (("/", "body", "Home"), (f"/manage/{first.get('id')}", "#storyBtn, .utabs", "the owner's page"),
                                    (f"/a/{first.get('slug')}", "form, .card", "an app as people see it"), ("/install", "#step", "the Install page")):
                errs.clear()
                pg.goto("http://127.0.0.1:8767" + path)
                try:
                    pg.wait_for_selector(sel, timeout=15000)
                    pg.wait_for_timeout(800)
                    ok = True
                except Exception:  # noqa: BLE001
                    ok = False
                expect(ok and not errs, f"{what} ({path}) renders with no script errors{' — ' + errs[0][:80] if errs else ''}")
            print("Control Center:")
            try:
                running = httpx.get("http://127.0.0.1:7000/api/status", timeout=2).status_code == 200
            except Exception:  # noqa: BLE001
                running = False
            if not running:
                print("  (skipped: the Control Center isn't running on this laptop)")
            else:
                cc = b.new_page(viewport={"width": 1400, "height": 1000})
                cerrs = []
                cc.on("pageerror", lambda e: cerrs.append(str(e)))
                cc.goto("http://127.0.0.1:7000/")
                for tab, sel in (("live", "#scene"), ("monitor", "#view-monitor .kpi-strip"), ("agents", "#view-agents .panel"), ("flow", "#flList")):
                    cerrs.clear()
                    cc.click(f'.modes [data-mode="{tab}"]')            # switch tabs the way a person does
                    try:
                        cc.wait_for_selector(sel, timeout=15000)
                        cc.wait_for_timeout(1200)
                        ok = True
                    except Exception:  # noqa: BLE001
                        ok = False
                    expect(ok and not cerrs, f"{tab} tab renders with no script errors{' — ' + cerrs[0][:80] if cerrs else ''}")
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
