# AppShare — vision discussion (saved 25 Nov 2026, to continue later)

Notes from the last five conversations about what AppShare should become. Nothing here has been built yet; the
open questions at the end are where to pick up.

## 1. The vision, in the owner's words

Not a form builder. **"Imagine I want an app or site like a simple game that 10 people can play instantly and get the
rankings — today I have to create it, then host it, and it needs a laptop. With this, I only give a prompt and tell the
selections/needs, and once made it can be shared as a link, like we share a document."**

Working summary (to be confirmed by the owner):
> Anyone describes **any small app** — a game, a quiz with rankings, a mini site, a tool — in plain words, maybe
> answers a few choices, and **immediately gets a working app with a link**. People open it on their phones and use it
> together. No coding, no hosting, **no laptop that has to stay on** — it lives online like a Google Doc.

**Open questions put to the owner (not answered yet):**
1. *Any* app (new screens and rules each time — e.g. a real game), or a growing family of app types?
2. Should apps live **in the cloud** (always online), not on the laptop?
3. Who makes apps — anyone from their phone (students, friends, teachers), or developers?
4. **Two or three example apps** exactly as someone would say them — the most useful input of all.

## 2. What AppShare already has (honest inventory)

**Prompt → live link works:** describe it (or pick a template) → the agent team builds it in ~15–20 s (Builder plans;
Data: questions and rules; Design: wording, colour, look; Access: who it's for) → the Validator checks it (no code is
generated, so it can't break) → instant draft link → change it in words → **Share** → live on any phone, no account
needed for public links, installable, updates live.

**What it can make today** — everything is one model: *people open it, fill something in, it's collected*:
forms and surveys (optionally anonymous) · polls (results after voting or always) · registrations/RSVPs with places ·
bookings with places per slot · requests with workflows (leave, tickets, claims) · file submissions with deadline.
Building blocks: text, long text, number, email, phone, date, choice, multi-choice, rating, file, info; deadline,
opening, anonymous, one/many per person, places, results visibility, statuses; 9 styles, 9 patterns, cover photo.

**Sharing like a doc:** people, groups, organisation, anyone with the link · roles owner/editor/viewer/submitter ·
WhatsApp, SMS, email, QR · three workspaces (university, office, general).
**After it's live:** responses per person, summaries and charts, CSV, who's missing; Insights, Review and Reminder
agents; notifications.

**Hosting:** runs **on the laptop** (Control Center + Tailscale public HTTPS). Links work only while the laptop is on.

**Cannot do yet:** games (scores, correct answers, rankings, rounds, timers) · real-time togetherness (everyone on the
same question at once) · custom screens/behaviour · "any app" · staying online without the laptop.

**Evidence of the gap:** asked for *"Simple guessing game, 5 rounds and calculates score per user. Then gives ranking
based on responses"*, AppShare built a form with five questions whose options are "Option A–D", no correct answers, no
score, no ranking — and its description **promised** a score and leaderboard. The agents must say when something
can't be built (honesty fix still to do).

## 3. Vision level — where AppShare stands

| Level | Meaning | Status |
|---|---|---|
| 1. Prompt → app | Describe in words, AI builds it, no code | ✅ done |
| 2. Live instantly, shared like a doc | Link, roles, groups, public, WhatsApp/QR, install, live updates | ✅ done |
| 3. Trustworthy | Validated, measured, safe, transparent, private | ✅ done |
| 4. Many kinds of apps | Quizzes, games, scores, rankings, timers | ❌ |
| 5. Together in real time | Live rounds, live leaderboard (Kahoot-style) | ❌ |
| 6. No laptop | Always online in the cloud | ❌ |
| 7. Any app you can imagine | Custom screens and behaviour per request | ❌ |

**Now: levels 1–3 of 7** — strong foundation (the hard part: reliable, shareable, measured), but not yet the "wow"
of *"make me a game and ten of us play it now"*.

| Gap | What it needs | Size |
|---|---|---|
| 4 | New blocks: correct answers + points, leaderboard, timer, rounds; agents learn them; honest "can't do yet" | medium (~a week) |
| 5 | Live session: host starts, everyone joins, host advances rounds, leaderboard updates on every phone (extends existing live updates) | medium–large |
| 6 | Cloud server (small VPS / free tier) + a real database | medium, a few $/month |
| 7 | Many more blocks, or AI-generated custom pieces in a sandbox (trades away some reliability) | large; a design choice |

**Suggested path:** 4 → 5 → 6 delivers the core promise; 7 can wait. Let the survey decide what comes first.

## 4. How good is the idea

**Good, with one big "but".** Real pain (fixed tools like Kahoot/Forms, or code-and-host yourself); the "share like a
Google Doc" framing is strong; the timing is right; **groups using an app together** is less served than one person
making one app.

**But it is a crowded race:** Claude artifacts (shareable, shared storage), Google (Gemini in Forms, AI Studio apps),
Lovable/Bolt/Replit (full apps with hosting). It wins only with a sharp angle:

| Their weakness | AppShare's angle |
|---|---|
| Generate code — results vary, things break | Reliable: checked building blocks |
| One creator, one app | Groups: shared data, roles, rankings, live together |
| General-purpose | Everyday group moments: classes, clubs, offices, friends |
| Hosting, plans, setup | Instant link, no account to answer, any phone |

| | Rating |
|---|---|
| Problem | strong, real, common |
| Originality | medium — crowded space, less-crowded combination |
| Feasibility | good (levels 4–6 realistic) |
| Final-year project | excellent (with the evaluation work) |
| Startup | possible only with a sharp focus |

**Overall ≈ 7.5/10.** Stay focused on *groups doing things together, reliably and instantly*. Strongest first use
case to test: *"a teacher says 'make a 10-question ranked quiz on heaps' and 40 students play it live in 30 seconds"* —
do that better than Kahoot, then expand.

## 5. Validation started

- **Survey (live):** *Quick apps for groups — 2-minute survey* — `<your HTTPS address>/a/<survey link>` (Control Center → Connect phones) (works while
  the laptop and Tailscale are on; closes 9 Dec 2026; AI review off). Analyse: `python -m evals.validation`.
- **Thresholds fixed in advance** (`evals/validation.py`): need ≥ 60% · would use (Yes) ≥ 40% · want games/quizzes
  ≥ 25% · real requests buildable today or with one block ≥ 50% · ≥ 25 answers.
- **Desk research and full plan:** `docs/VALIDATION.md`.

## Where to continue

1. Owner answers the four open questions in section 1 (especially 2–3 example apps).
2. Collect ≥ 25 survey answers → `python -m evals.validation` → part B (real requests through the agents, ≈ $1–2).
3. Plan level 4 in detail (game blocks + honest "can't do yet") for review before building.
