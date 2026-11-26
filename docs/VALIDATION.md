# Validating the AppShare idea and vision

**The vision:** describe a small app in words — a poll, sign-up, quiz, a game with rankings, a booking — and get a link
that anyone can open on their phone and use together, instantly, like sharing a Google Doc. No coding, no hosting,
no laptop to set up.

**What has to be true for it to be worth building** — and how each is tested:

| # | Question | How it is tested |
|---|---|---|
| 1 | Do people often need quick shared apps for a group? | Survey (part A) |
| 2 | What kinds of apps do they want? | Survey: kinds + free-text requests |
| 3 | Is "describe it → link" better than what they use today? | Survey: tools used, annoyances, would they switch |
| 4 | Can AppShare actually build what people ask for? | Part B: run real requests through the agents |
| 5 | Does someone already do this well? | Part C: desk research (below) |

## Success thresholds — fixed on 2026-11-25, before any answer arrived

| Signal | Validated if | Why this bar |
|---|---|---|
| Need | ≥ 60% needed a quick group app in the last month | A frequent need, not a rare one |
| Interest | ≥ 40% answer **Yes** (not Maybe) to using AppShare instead | Habit is strong; "maybe" doesn't count |
| Fit | ≥ 50% of real requests buildable today or with one planned building block | Otherwise the engine can't deliver the vision |
| Direction | ≥ 25% want quizzes or games with scores/rankings | Justifies building game blocks next |
| Sample | ≥ 25 answers | Below that, intervals are too wide to decide |

The thresholds live in `evals/validation.py` and are not changed after answers come in. Missing one is a result too:
it says what to change (the audience, the kinds of app, or the vision).

## Part A — the survey (running)

Built with AppShare itself (dogfooding), so the survey also tests the product. Open to anyone with the link, no
account needed, closes **9 December 2026**. Twelve questions: role · needed one last month? · kinds needed · tools used
· what annoyed them · **"describe an app you'd like to make right now"** · words or clicks? · group size · would you use
this instead? · why · one must-have · name (optional). The AI reviewer is switched off for this survey (no AI reads
the answers; no cost per answer).

**Share it:** in AppShare, open *Quick apps for groups — 2-minute survey* → Send link (WhatsApp, email, QR).
Aim for 25–40 answers from students, teachers and friends.

**Analyse any time (free):** `python -m evals.validation` — prints each signal with its 95% interval against the
fixed targets, and exports the free-text requests to `data/evals/requests.csv`.

## Part B — can the engine build what people ask for? (after the survey)

1. Take every answer to "describe an app you'd like to make" (`data/evals/requests.csv`).
2. Give each one to the Builder (≈ $0.05 per request; ≈ $1–2 for 30) and record what it built.
3. Classify each: **buildable today** · **buildable with one planned block** (scores/leaderboard, timer, live rounds,
   teams…) · **not possible with a spec engine** (needs custom code or graphics).
4. Report the shares with 95% intervals; the "fit" threshold above decides.
5. The same requests become a new evaluation set made of real users' words.

## Part C — what already exists (desk research, November 2026)

| Kind of tool | Examples | What they do | Where AppShare differs |
|---|---|---|---|
| AI form creation | Google Forms "Help me create" (Gemini) | Generates a form or quiz from a prompt; quizzes get correct answers and points. Needs an eligible Workspace / AI plan; desktop; can't edit an existing form by prompt | Beyond forms: bookings with places, approval workflows, AI review of submissions, targeted reminders, anonymity guarantees; free to self-host |
| Quiz games | Kahoot, Quizizz (now Wayground) | AI generates quiz questions from a topic or document; live leaderboards | One fixed format (quiz); AppShare's vision is any small app from one description |
| AI app builders | Lovable, Bolt, Replit Agent (~$20–25/month) | Generate a full app as code with hosting and a database included | They write code (results vary; you review and debug it); AppShare fills a checked spec, so apps are reliable and instantly live |
| AI chat mini-apps | Claude artifacts | Interactive mini-apps from a prompt, shareable by link; shared storage and multiplayer editing on some plans | General-purpose and code-based; AppShare is purpose-built for group data, roles, rankings and responses |
| Prompt-to-app with sharing | Taskade Genesis, Zite, Base44 | Apps from a prompt, published to a shareable URL | Mostly code-generated; AppShare emphasises reliability, access control and measured agents |
| AI game makers | Oriverse, Makko AI | Multiplayer games from a prompt, shared by link | Games only; AppShare targets everyday group needs (classes, offices, friends) |

**Reading of the market:** prompt-to-app with a shareable link is a crowded, fast-moving space, so the *generic* idea
is not new. The open gap is the combination: **instant, reliable (no generated code), multi-user apps with shared
data, roles and rankings, for everyday group tasks, on any phone**. That combination is exactly what part A and
part B test. Most sources are vendor or comparison blogs from 2025–2026; details (plans, prices, limits) change
often and should be checked on each vendor's site.

Sources: [Google Forms help — Create a form with Gemini](https://support.google.com/docs/answer/16346789) ·
[Workspace Updates — quizzes with Gemini (Jul 2026)](https://workspaceupdates.googleblog.com/2026/07/use-gemini-in-google-forms-to-quickly-create-a-new-quiz.html?hl=en) ·
[Kahoot AI tools](https://kahoot.com/ai-tools/) · [Quizizz AI](https://quizizz.com/quizizz-ai?lng=en) ·
[Lovable vs Bolt vs Replit (2026)](https://vibecoding.app/blog/bolt-vs-lovable-vs-replit) ·
[Replit pricing 2026](https://latenode.com/blog/replit-pricing) · [Lovable pricing 2026](https://latenode.com/blog/lovable-pricing) ·
[Claude artifacts help](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them) ·
[Claude artifacts multiplayer (AlphaSignal)](https://alphasignal.ai/news/anthropic-makes-claude-artifacts-multiplayer-so-teams-can-build-together) ·
[Free AI app builders 2026 (Taskade)](https://www.taskade.com/blog/free-ai-app-builders) ·
[AI web app builders 2026 (Zite)](https://www.zite.com/blog/ai-web-app-builder) ·
[Best AI game makers (Chatforce)](https://chatforce.com/blog/best-ai-game-makers-compared)

## Already known from the project itself

When asked for *"a simple guessing game, 5 rounds, scores per user, then rankings"*, AppShare built a form with
placeholder options and **promised** a score and leaderboard it cannot produce — the engine has no scoring or
ranking yet, and the agents didn't say so. Two consequences, independent of the survey: the agents must say plainly
when something can't be built yet, and game-type requests are the first gap to measure in part B.
