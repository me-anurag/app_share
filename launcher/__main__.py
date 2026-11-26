"""Start the AppShare Control Center:   python -m launcher   [--autostart] [--no-browser]"""
import argparse
import atexit
import threading
import time
import webbrowser

import uvicorn

from .control import CONTROL_PORT, SERVER, app, shutdown_children


def main():
    parser = argparse.ArgumentParser(description="AppShare Control Center")
    parser.add_argument("--autostart", action="store_true", help="turn the AppShare server on right away")
    parser.add_argument("--no-browser", action="store_true", help="don't open the Control Center in a browser")
    parser.add_argument("--local-only", action="store_true", help="with --autostart: don't allow phones to connect")
    args = parser.parse_args()

    atexit.register(shutdown_children)
    url = f"http://127.0.0.1:{CONTROL_PORT}"
    print(f"\n  AppShare Control Center  ->  {url}\n  (keep this window open; Ctrl+C stops everything)\n")

    def after_boot():
        time.sleep(1.2)
        if args.autostart:
            try:
                SERVER.start(lan=not args.local_only)
            except Exception as e:  # port busy etc. - the UI shows the state
                print("  Could not start the server:", getattr(e, "detail", e))
        if not args.no_browser:
            webbrowser.open(url)

    threading.Thread(target=after_boot, daemon=True).start()
    try:
        # Bound to 127.0.0.1 on purpose: only this laptop can control the server.
        uvicorn.run(app, host="127.0.0.1", port=CONTROL_PORT, log_level="warning")
    finally:
        shutdown_children()


if __name__ == "__main__":
    main()
