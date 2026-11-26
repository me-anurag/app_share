"""Load and concurrency test of the AppShare server (free: no API calls).

  python -m evals.load

Starts a separate AppShare server on port 8765 with a throwaway seeded database and the load-test stand-in model
(fixed delay per call, see evals/load_fake.py), then measures:
  reads      N people opening apps at the same time   -> requests/s, p50/p95/p99 latency, errors
  writes     N people submitting responses at once    -> submissions/s, latency, errors (SQLite's single writer)
  agents     K app builds started at the same moment  -> time per build, queuing, errors
Numbers are for THIS laptop, one server process; the report says so.
"""
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
LLM_MS = 800
UNI = ["prof.sharma", "dr.mehta", "dr.iyer", "ms.kapoor", "aarav", "diya", "kabir", "ananya", "rohan", "isha", "vivaan", "meera",
       "arjun", "sneha", "farhan", "tara"]


def pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1) if xs else None


def setup(tmp):
    """Seed a database and one public app that takes many responses (guests), before the server starts."""
    code = ("from backend import main\nfrom backend.db import connect\nfrom backend.seed import Seeder\n"
            "c = connect(); s = Seeder(c)\n"
            "a, _ = s.app('dr.mehta@riverside.edu', {'title': 'Load test sign-up', 'kind': 'registration', 'responses_per_person': 'many',"
            " 'description': 'x', 'fields': [{'id': 'name', 'type': 'short_text', 'label': 'Your name', 'required': True},"
            " {'id': 'pick', 'type': 'radio', 'label': 'Pick', 'options': ['A', 'B'], 'required': True}]}, [], link='public')\n"
            "print(c.execute('SELECT slug FROM apps WHERE id = ?', (a,)).fetchone()[0]); c.commit()\n")
    env = {**os.environ, "APPSHARE_DATA": tmp, "APPSHARE_MODE": "university"}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return out.stdout.strip().splitlines()[-1]


def run_level(n, seconds, work):
    """n workers loop `work(i)` for `seconds`; returns latencies (ms) and error count."""
    lat, errs, lock = [], [0], threading.Lock()
    stop = time.time() + seconds

    def loop(i):
        while time.time() < stop:
            t0 = time.perf_counter()
            try:
                ok = work(i)
            except Exception:  # noqa: BLE001
                ok = False
            ms = (time.perf_counter() - t0) * 1000
            with lock:
                lat.append(ms)
                if not ok:
                    errs[0] += 1
    th = [threading.Thread(target=loop, args=(i,)) for i in range(n)]
    t0 = time.time()
    for t in th:
        t.start()
    for t in th:
        t.join()
    took = time.time() - t0
    return {"users": n, "requests": len(lat), "per_second": round(len(lat) / took, 1), "p50_ms": pct(lat, .5), "p95_ms": pct(lat, .95),
            "p99_ms": pct(lat, .99), "max_ms": round(max(lat), 1) if lat else None, "errors": errs[0],
            "error_rate": round(errs[0] / max(1, len(lat)), 4)}


def main():
    tmp = tempfile.mkdtemp(prefix="appshare-load-")
    slug = setup(tmp)
    env = {**os.environ, "APPSHARE_DATA": tmp, "APPSHARE_MODE": "university", "APPSHARE_LOAD_TEST_FAKE_LLM_MS": str(LLM_MS),
           "ANTHROPIC_API_KEY": "load-test-not-a-key", "APPSHARE_USER_AGENT_RUNS_PER_HOUR": "100000", "APPSHARE_DAILY_BUDGET_USD": "100000",
           "PYTHONIOENCODING": "utf-8"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                if httpx.get(BASE + "/api/ping", timeout=2).status_code == 200:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        clients = []
        for u in UNI:
            c = httpx.Client(base_url=BASE, timeout=60)
            c.post("/api/login", json={"email": u + "@riverside.edu"}).raise_for_status()
            clients.append(c)
        guests = [httpx.Client(base_url=BASE, timeout=60) for _ in range(50)]
        R = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "machine": os.environ.get("COMPUTERNAME", "this laptop"), "server": "1 uvicorn process",
             "fake_llm_ms_per_call": LLM_MS, "reads": [], "writes": [], "agents": []}

        print("Reads — people opening an app and their app list:")
        for n in (1, 10, 25, 50):
            def read(i):
                c = clients[i % len(clients)]
                return c.get(f"/api/a/{slug}").status_code == 200 and c.get("/api/apps").status_code == 200
            r = run_level(n, 8, read)
            R["reads"].append(r)
            print(f"  {n:>3} people · {r['per_second']:>6}/s · p50 {r['p50_ms']} ms · p95 {r['p95_ms']} ms · p99 {r['p99_ms']} ms · errors {r['errors']}")

        print("Writes — people submitting responses at the same time:")
        for n in (10, 25, 50):
            def write(i):
                return guests[i].post(f"/api/a/{slug}/submit", data={"name": f"Guest {i}", "pick": "A"}).status_code == 200
            r = run_level(n, 8, write)
            R["writes"].append(r)
            print(f"  {n:>3} people · {r['per_second']:>6}/s · p50 {r['p50_ms']} ms · p95 {r['p95_ms']} ms · p99 {r['p99_ms']} ms · errors {r['errors']}")

        print(f"Agents — app builds started at the same moment (stand-in model, {LLM_MS} ms per call):")
        for k in (1, 4, 8, 16):
            times, errs = [], [0]

            def one(i):
                c = clients[i % len(clients)]
                t0 = time.perf_counter()
                try:
                    r = c.post("/api/agent/build", json={"message": f"load test app {i}"}).json()
                    if r.get("error") or not r.get("app"):
                        errs[0] += 1
                except Exception:  # noqa: BLE001
                    errs[0] += 1
                times.append((time.perf_counter() - t0) * 1000)
            t0 = time.time()
            th = [threading.Thread(target=one, args=(i,)) for i in range(k)]
            for t in th:
                t.start()
            for t in th:
                t.join()
            wall = time.time() - t0
            r = {"builds": k, "wall_s": round(wall, 2), "p50_s": round(statistics.median(times) / 1000, 2), "max_s": round(max(times) / 1000, 2),
                 "errors": errs[0], "builds_per_minute": round(k / wall * 60, 1)}
            R["agents"].append(r)
            print(f"  {k:>3} builds · all done in {r['wall_s']} s · each {r['p50_s']} s median, {r['max_s']} s slowest · errors {r['errors']}")
        single = R["agents"][0]["p50_s"]
        R["notes"] = {"ideal_build_s": round(5 * LLM_MS / 1000, 2),
                      "explanation": "a build makes 5 model calls on its critical path (Builder 3, Design 2 after Data), so with the stand-in "
                                     f"one build cannot take less than about {5 * LLM_MS / 1000:.1f} s; anything above that is queuing in the server."}
        print(f"\n  (one build alone took {single} s; the critical path is ≈ {5 * LLM_MS / 1000:.1f} s of model calls)")
        out = os.path.join(ROOT, "data", "evals", time.strftime("%Y%m%d-%H%M%S") + "-load")
        os.makedirs(out, exist_ok=True)
        json.dump(R, open(os.path.join(out, "load.json"), "w", encoding="utf-8"), indent=1)
        print(f"\nResults: {os.path.join(out, 'load.json')}")
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:  # noqa: BLE001
            srv.kill()


if __name__ == "__main__":
    main()
