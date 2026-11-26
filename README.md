# AppShare

Create and share small apps (feedback forms, registrations, polls, slot bookings, requests with approvals,
RSVPs, submissions) as easily as sharing a doc. You describe the app in plain language (or start from a
template), a team of agents builds it, and you share it with people, groups, your whole organization, or anyone
with the link, each with an access level.

## Three workspaces

| Workspace | Demo organization | Who shares with whom | Example apps (seeded, with responses) |
|---|---|---|---|
| **University** | Riverside University (`@riverside.edu`) | Faculty, staff and students; sections (34ML, 34MK, 23EC), years, departments, clubs | Assignment upload (34ML), anonymous mid-semester feedback, TechFest registration with 60 places, lab slot booking (3 per slot), elective poll with results after voting, campus maintenance requests (Open → In progress → Resolved), a student-run club sign-up |
| **Office** | Northwind Labs (`@northwind.co`) | Managers and employees; departments, teams | Leave requests (Pending → Approved/Rejected by managers), IT help desk, expense claims with receipts, anonymous engagement pulse, team lunch poll, workshop with limited sessions |
| **General** | Anyone (`@example.com` demo people, open sign-up) | Shared by link, like a public Doc; guests answer without an account | Birthday RSVP, book club poll with public results, bakery feedback (anonymous), sourdough workshop sign-up |

Pick the workspace in the Control Center (power screen or **Connect phones → Workspace**), or set
`APPSHARE_MODE=university|office|general`. Each workspace keeps its own data in `data/<workspace>/`.

What any app can do (the agents choose these from your description): anonymous answers, one or many responses
per person, a total cap and per-option places (slots), results shown never / after answering / always, a status
workflow with notifications to the requester, open and close dates, file uploads with type and size checks.

## How it works

```
 You: "assignment portal for 34ML, PDF/DOCX, due Friday"
          │
          ▼
 Builder agent (Claude + tools) ──► list_groups / search_people   (real org directory)
          │                     └─► save_app(spec)                 (validated by the engine)
          ▼
 App spec (JSON) ──► Engine: renders the UI, stores responses and files, unique link,
                     deadline + file-type checks, role-based access
          ▼
 Share dialog (pre-filled by the agent) ──► 34ML members see it under "Shared with me"
          ▼
 Insights agent: "who hasn't submitted?" ──► reads responses through tools
```

The agents never write code. They fill in a spec that the engine already knows how to run, which keeps apps
fast to create and reliable.

## The agents

| Agent | When it runs | What it does | Its tools |
|---|---|---|---|
| **Builder** (lead) | You ask for an app | Writes a brief, hands it to the build team, saves the result; small edits it does itself | `ask_data_agent`, `ask_design_agent`, `ask_access_agent`, `get_current_app`, `save_app` |
| **Data** | Asked by the Builder | Designs what the app collects: fields, types, file rules, deadline | `check_fields`, `submit_fields` |
| **Design** | Asked by the Builder | Designs how it reads and looks: title, instructions, wording, order, colour (checks contrast) | `get_fields`, `check_color`, `submit_design` |
| **Access** | Asked by the Builder | Finds the real groups/people and proposes roles | `list_groups`, `search_people`, `submit_access` |
| **Insights** | The owner asks a question | Answers questions about responses | `get_overview`, `list_responses`, `list_missing` |
| **Review** | After every submission (background) | Reads the file and answers, flags empty / wrong / copied work for the owner | `get_assignment`, `read_submission`, `compare_with_others`, `submit_review` |
| **Reminder** | 24 h and 2 h before a deadline, or **Remind now** | Reminds only the people who haven't submitted (in-app notification) | `get_overview`, `list_missing`, `send_reminders` |

Data and Access work in parallel; Design starts as soon as Data's fields are ready. The specialists run on a
faster model (`APPSHARE_SPECIALIST_MODEL`, default `claude-haiku-5-5`); the Builder and Insights use
`APPSHARE_MODEL` (default `claude-opus-5-5`). The **Validator** is plain code, not an agent: it checks every app
before it is saved, and the agents' own check tools use it too.

**Roles:** owner, editor (change and share), viewer (see responses), submitter (fill in). Share with a person,
a group, or anyone in the organization who has the link.

## Run it (Control Center — recommended for demos)

```powershell
pip install -r requirements.txt
python -m launcher          # or double-click "Start Control Center.bat"
```

The **Control Center** opens at http://127.0.0.1:7000 (only on the server laptop). Press the power button to
start AppShare. Add the Claude API key under **Connect phones → Agent API key** (or set `ANTHROPIC_API_KEY`).

It has three modes:

| Mode | What it shows |
|---|---|
| **Live server** | Animated server: phones and laptops on the left, a firewall, a 4-blade server rack (web, auth, engine, AI) with LEDs and fans, and the database, file storage, agents and Claude cloud. Every real request travels as a glowing packet; blocked uploads and denied access flash red. A QR code lets phones connect. |
| **Monitor** | What the server tracks: devices online, uptime, requests per minute (stacked by type, with hover and a table view), connected devices, apps with response progress, security blocks, agent calls and tokens, busiest endpoints, and a live request log with filters. |
| **Agent theater** | The Builder and Insights agents as animated robots: thinking with Claude, using tools (directory cards, the app blueprint assembling field by field), the Validator stamping VALID or REJECTED, and the reply — with a plain-language narration and a step timeline. |

**Rehearsal:** "Rehearsal traffic" (Live) and "Builder/Insights demo" (Agent theater) play pretend data so you
can show the animations without phones or an API key. Both are clearly labelled as simulations and never
change the Monitor numbers.

Without the Control Center you can still run the server directly: `uvicorn backend.main:app --host 0.0.0.0`.

The sign-in page lists the demo people of the current workspace. University: sign in as **Dr. Mehta** to see
anonymous feedback results, as **Ms. Kapoor** to move maintenance requests along, or as a 34ML student (Diya
Patel) to see what's due. Office: **Vikram Shah** approves leave, **Priya Nair** requests it. General: open a
shared link on a phone without signing in.

## Installing on phones needs an https address

Phones only install apps (and only open shared links inside the installed app) from an **https** address.
Install a tunnel tool once, then press **Connect phones → Get internet address** in the Control Center:

- **Tailscale Funnel** (recommended): `winget install Tailscale.Tailscale`, sign in, and enable Funnel once.
  You get a fixed address like `https://your-pc.your-tailnet.ts.net` with no warning page, so phones can install
  the app. It stays on after the Control Center closes, and the Control Center picks it up again on start.
- **cloudflared** (free, no account): `winget install Cloudflare.cloudflared`. No warning page, but the address
  changes each time you start it.
- **ngrok** free static domain: a fixed address, but ngrok's free "Visit Site" warning page stops Android from
  installing the app, so use it only for opening links.

While the internet address is on, every link AppShare copies or sends uses it automatically.

**The QR code opens the Install page** (`/install`). It works out where it was opened and shows the one step
that works there. A camera or scanner "quick view" can't install apps, so the page shows an **Open in Chrome**
button. In Chrome it shows **Install AppShare**. iPhone and Samsung Internet get their own steps. On Vivo, Oppo,
Xiaomi and similar phones, Chrome may also need the **Home screen shortcuts** permission (Settings → Apps → Chrome
→ Permissions).

## Phones connect (and reconnect) automatically

- Scan the QR code in the Control Center with the phone on the same Wi-Fi or on the laptop's hotspot.
- The app checks in with the server every few seconds. If the server goes off, it shows "Server offline ·
  reconnecting…" and comes back by itself as soon as you press power again.
- An installed app remembers its address, so keep the address the same: use the **laptop's Mobile Hotspot**
  (the laptop is always `192.168.137.1`, http only) or **Tailscale Funnel** (a fixed HTTPS address). The HTTPS
  address also lets phones install the app and connect from any network.

Optional settings: `APPSHARE_MODEL` (default `claude-opus-5-5`), `APPSHARE_EFFORT` (default `low` for fast
replies; `medium` or `high` for harder requests), `APPSHARE_ORG` (organization name), `APPSHARE_DATA` (data folder).

## On a phone

AppShare is an installable web app (PWA). Scan the Control Center's QR code (or open `https://<address>/install`)
and follow the one step the Install page shows. The full flow works on the phone:
describe the app in **Create**, check it in **Preview**, press **Share**, and use **Send** to post the link to
WhatsApp or email.

To test on your own phone during development, run the server so the phone can reach it
(`uvicorn backend.main:app --host 0.0.0.0`) and open `http://<your-PC's-IP>:8000` on the same Wi-Fi.
Installing as an app requires HTTPS (or localhost), so for the install button on a real phone either deploy it or
use a tunnel (Tailscale Funnel or cloudflared, see above).

After changing files in `frontend/`, bump `VERSION` in `frontend/sw.js` so installed apps pick up the new files.

## Project layout

| Path | What it does |
|---|---|
| `backend/agents.py` | All seven agents: prompts, tools, the shared tool loop (parallel hand-offs), review/reminder runs |
| `backend/filetext.py` | Reads PDF / DOCX text and detects copied files for the Review agent |
| `backend/spec.py` | App spec validation, deadline window, server-side file and answer checks |
| `backend/access.py` | Effective role resolution (user, group, org link), audience |
| `backend/main.py` | API routes: login, apps, share, submit, files, responses, CSV export |
| `backend/db.py` | SQLite schema, workspace mode and vocabulary |
| `backend/seed.py` | Demo people, groups, apps and responses for each workspace |
| `backend/templates.py` | Ready-made templates per workspace (8 university, 8 office, 6 general) |
| `backend/monitor.py` | Live monitor: requests, devices, agent steps, streamed to the Control Center |
| `frontend/` | Phone-first PWA: Home / Create / Inbox (`index.html`), the app renderer people answer (`app.html`), the owner page with Summary, Responses, Ask and Edit (`manage.html`) |
| `launcher/control.py` | Control Center backend: start/stop the server, logs, addresses, QR codes, https tunnel (Tailscale / cloudflared / ngrok) |
| `launcher/ui/` | Control Center screens: `live.js`, `monitor.js`, `theater.js`, rehearsal data in `sim.js` |

Data lives in `data/<workspace>/` (SQLite file and uploads). **Reset demo data** in the Control Center
recreates the current workspace.

## Measuring the agents

Every app has a saved **journey** (`backend/trace.py`): the request, every agent run, model call (tokens, calculated
cost, time), tool call (arguments and result), Validator verdict, retry, and the agents' stated reasons — plus what
happened after sharing. Answers and file text are redacted before saving. See it in the Control Center's **Flow** tab
(key 4); app owners see a plain version under **How this app was built** on the app's Overview.

The evaluation suite (`evals/`) runs 12 realistic tasks across the three workspaces with exact checks:

```powershell
python -m evals.run --mode fake                    # harness self-test: no API, proves the checks catch mistakes
python -m evals.run --mode live --estimate         # cost estimate from real measured runs
python -m evals.run --mode live --yes              # real agents (≈ $1.20); records every reply
python -m evals.run --mode replay --from data\evals\<live run>   # reproduce a live run free, no API key
python -m tests.run_all                            # every offline test suite, one command (the regression gate)
python -m evals.safety --mode fake | live --yes    # prompt-injection and chat attacks, guardrails off vs on (live ≈ $0.80)
python -m evals.review_eval --mode fake | live --yes   # Review agent accuracy + fairness across names (live ≈ $0.05)
python -m evals.heldout                            # the injection scanner on attacks it was never tuned on
python -m evals.load                               # load and concurrency test (free: stand-in model)
python -m evals.system_card                        # writes docs/SYSTEM_CARD.md from the measured results
```

Reports land in `data/evals/<time>-<mode>/` (`report.html`, `report.md`, `results.json`, `cassettes/`).
`docs/SYSTEM_CARD.md` is the evaluation report (generated, no hand-typed numbers); `docs/DATA_FLOW.md` lists exactly
what each agent sends to the API.

**AI provider:** Claude by default. In the Control Center (Connect phones → **AI provider**) switch all agents to
**Groq's free tier** or choose per agent (**Mixed**); add a free key from console.groq.com there. Compare them on the
same tasks: `python -m evals.run --mode live --ai groq --yes` ($0 on the free tier).

**AI limits** (checked before any model call): `APPSHARE_DAILY_BUDGET_USD` (default 3.00, calculated spend per day) and
`APPSHARE_USER_AGENT_RUNS_PER_HOUR` (default 30 per person). The Monitor shows the budget and alerts.

## Members and groups

An admin (Prof. Sharma, Ananya Rao, Riya Kapoor) can import members from the profile menu
(**Import members (CSV)**):

```
email,name,groups,title
student1@riverside.edu,Student One,34ML,Student · 34ML
student2@riverside.edu,Student Two,34ML;Coding Club,Student · 34ML
```

## Deliberately minimal for now

- Login is email only, with no password. Replace with your organization's SSO before real use.
- No email notifications yet. Shared apps appear on each person's Home, and status changes and reminders arrive
  in the in-app Inbox.
