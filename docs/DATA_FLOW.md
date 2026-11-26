# What AppShare sends to the AI (data-flow statement)

AppShare's agents call the Claude API (Anthropic) over HTTPS. Everything else — the database, uploaded files,
responses, the trace store — stays on the server laptop. This page lists, per agent, exactly what leaves the
laptop in a model call. It is written from the code (`backend/agents.py`) and **tested**: `tests/test_minimisation.py`
records every message all seven agents would send across a full build, an Insights question, a reminder run and an
anonymous review, and fails if any email address or anonymous file name appears in them.

## Which company receives it

By default every agent calls **Anthropic (Claude)**. In the Control Center (**AI provider**) the owner of the server
can switch some or all agents to **Groq** (free tier, open models) — `APPSHARE_AI_MODE` = `claude` | `groq` | `mixed`.
An agent switched to Groq sends **exactly the same data listed below**, but to Groq instead of Anthropic, under Groq's
terms. The Groq key is sent only in the request's Authorization header; it is never logged or stored in traces
(tested: `tests/test_providers.py`). Claude-only features (thinking, prompt caching) are not used with Groq.

## Always sent with every call

- The agent's instructions (system prompt): fixed text, plus the organisation's name and workspace type.
- The list of tools the agent may use (names and argument descriptions).
- The current local date and time (so "due Friday" can be resolved).

## Per agent

| Agent | Sent to the API | Personal data in it | Never sent |
|---|---|---|---|
| **Builder** | The owner's request and earlier messages in that conversation; the specialists' results; for edits, the app's current spec and who it is shared with | The owner's request text; names of groups/people the app is shared with | Email addresses, responses, files, other apps |
| **Data** | The Builder's brief | Only what the owner typed | Directory, responses |
| **Design** | The brief; the Data agent's field list | None beyond the brief | Directory, responses |
| **Access** | The brief; the workspace's group list (names, kinds, member counts); people-search results | **Names and job titles**, each with an internal reference (`u12`) | **Email addresses** |
| **Insights** | App overview; responses (answers, time, status); who hasn't responded | Normal apps: respondents' **names, groups and answers**. Anonymous apps: answers only, dates only, generic file names | Email addresses, file contents, exact times on anonymous apps |
| **Review** | The assignment; one submission's answers; **up to 3,500 characters of text from each uploaded file**; similarity results against classmates | The submitter's name (or "An anonymous respondent"); classmates' names when a copy is found (normal apps only); the file text | Email addresses, the files' bytes, file names on anonymous apps |
| **Reminder** | App overview; the people who haven't responded | **Names**, each with an internal reference; the server turns references back into people | **Email addresses** |

## Never sent

Email addresses, passwords (AppShare has none), session tokens, the API key, uploaded files as files, the database,
other apps' data, other workspaces' data, the trace store, and data of apps the requesting person can't access
(every tool checks access first).

## Protections around it

- **Minimum necessary per agent:** each agent only has tools for its own job; Data and Design never see the
  directory; no agent can read another app; people are referred to by internal references, not email addresses.
- **Anonymity:** anonymous apps never give names, emails, exact times or file names to any agent, the owner's screen,
  downloads or the CSV export (tested: `tests/test_responsible.py`, `tests/test_minimisation.py`).
- **People are told:** an app shows the person answering when an AI assistant will read their answers or file
  ("it can only flag things — a person makes every decision"), and on anonymous apps reminds them not to put their
  name in answers, files or file names.
- **Untrusted text is fenced:** file text and answers are marked as data, never instructions (`backend/guard.py`).
- **Local records are redacted:** the trace store never keeps answers, file text or full email addresses.
- **Cost and abuse limits:** daily AI budget and per-person hourly limit (`backend/limits.py`).

## Open points (for a real deployment)

- **Retention at the provider:** how long Anthropic or Groq keeps request data, and whether it is used for training,
  is governed by each provider's current terms for API customers — check them before real use, especially before
  switching agents that handle responses (Insights, Review, Reminder) to a free tier.
- **Names still go to the API on normal (non-anonymous) apps**, because questions like "who hasn't submitted?" need
  them. Replacing names with references and mapping them back in the answer would remove this too.
- **File text goes to the API for every reviewed submission.** People are told on the app; an organisation may also
  want the Review agent switched off per app.
- **The text inside an anonymous file** can still contain the author's name; the notice asks people not to.
- **Response order** of anonymous apps is kept (numbered "Response 1, 2…", dates only).
