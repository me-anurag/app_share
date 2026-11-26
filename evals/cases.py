"""The evaluation tasks: realistic requests with exactly checkable expectations.

Each build task has:
  prompt       the request as a person would type it
  paraphrase   the same request reworded (for consistency across wording)
  level        1 simple · 2 moderate · 3 complex (rules interacting: places per slot, workflows, files)
  checks       what must be true of the saved app, each owned by the agent responsible for it
  reference    a hand-written correct answer (spec + shares). Used to test the checks themselves and by `fake` mode.

Insights / Reminder tasks are checked against ground truth read from the database at run time (exact counts and names).
All dates are absolute so a recording can be replayed and re-checked on any day.
"""

# check kinds: field · choice · rule · closes · no_identity · max_fields · statuses · share · title_has
BUILD = [
    # ------------------------------------------------------------------ university
    dict(id="U1-feedback", ws="university", level=1, owner="dr.mehta@riverside.edu",
         prompt="Anonymous mid-semester feedback for my Data Structures course, section 34ML: rate the lectures from 1 to 5 and leave any comments.",
         paraphrase="I want 34ML to tell me honestly how my Data Structures lectures are going — no names. A 1-5 rating and a comments box.",
         checks=[("data", "rule", "anonymous", True), ("data", "field", {"type": "rating"}), ("data", "field", {"type": "long_text"}),
                 ("data", "no_identity"), ("data", "max_fields", 4),
                 ("access", "share", {"type": "group", "name": "34ML", "role": "submitter"})],
         reference=dict(spec={"title": "Data Structures — mid-semester feedback", "kind": "feedback", "anonymous": True, "theme_color": "#3b4f7a",
                              "description": "Anonymous. Tell me how the lectures are going.",
                              "fields": [{"id": "lectures", "type": "rating", "label": "How are the lectures?", "required": True},
                                         {"id": "comments", "type": "long_text", "label": "Any comments?"}]},
                        shares=[{"type": "group", "name": "34ML", "role": "submitter"}])),
    dict(id="U2-assignment", ws="university", level=2, owner="dr.mehta@riverside.edu",
         prompt="Assignment 3 upload for 34ML: PDF or DOCX only, max 10 MB, due 12 December 2026 at 5pm. Students can resubmit until the deadline.",
         paraphrase="Collect Assignment 3 from section 34ML as a PDF or Word file (10 MB limit). Deadline 5 pm on 12 Dec 2026; replacing the file before then is fine.",
         checks=[("data", "field", {"type": "file", "accept": [".pdf", ".docx"], "max_mb": 10}), ("data", "closes", "2026-12-12T17:00"),
                 ("data", "rule", "allow_edit_after_submit", True), ("data", "no_identity"),
                 ("access", "share", {"type": "group", "name": "34ML", "role": "submitter"})],
         reference=dict(spec={"title": "Assignment 3 upload", "kind": "assignment", "closes_at": "2026-12-12T17:00", "allow_edit_after_submit": True,
                              "theme_color": "#1f5f7a", "description": "Upload one PDF or DOCX, up to 10 MB.",
                              "fields": [{"id": "report", "type": "file", "label": "Your report", "required": True, "accept": [".pdf", ".docx"], "max_mb": 10}]},
                        shares=[{"type": "group", "name": "34ML", "role": "submitter"}])),
    dict(id="U3-lab-slots", ws="university", level=3, owner="dr.mehta@riverside.edu",
         prompt="Lab slot booking for 34MK: slots Monday 2pm, Tuesday 2pm and Wednesday 10am, 3 students per slot, one booking per student, closes 30 November 2026.",
         paraphrase="Section 34MK needs to pick a lab slot — Mon 2 pm, Tue 2 pm or Wed 10 am. Max three people in each, each student books once. Bookings close on 30 Nov 2026.",
         checks=[("data", "choice", {"options": ["mon", "tue", "wed"], "limits": 3}), ("data", "rule", "responses_per_person", "one"),
                 ("data", "closes", "2026-11-30"), ("data", "no_identity"),
                 ("access", "share", {"type": "group", "name": "34MK", "role": "submitter"})],
         reference=dict(spec={"title": "Lab slot booking", "kind": "booking", "description": "Pick one lab slot. Three places per slot.", "closes_at": "2026-11-30T23:59", "responses_per_person": "one", "theme_color": "#2f6f5e",
                              "fields": [{"id": "slot", "type": "radio", "label": "Your slot", "required": True,
                                          "options": ["Mon 2pm", "Tue 2pm", "Wed 10am"], "limits": {"Mon 2pm": 3, "Tue 2pm": 3, "Wed 10am": 3}}]},
                        shares=[{"type": "group", "name": "34MK", "role": "submitter"}])),
    dict(id="U4-techfest", ws="university", level=2, owner="ms.kapoor@riverside.edu",
         prompt="TechFest 2026 hackathon registration open to everyone at the university, 60 places, ask for the team name and the track (AI, Web or IoT).",
         paraphrase="Registration for the TechFest 2026 hackathon — anyone in the university can sign up, only 60 spots. Need their team name and which track: AI, Web, IoT.",
         checks=[("data", "rule", "max_responses", 60), ("data", "field", {"type": "short_text", "label": "team"}),
                 ("data", "choice", {"options": ["ai", "web", "iot"]}), ("access", "share", {"type": "org"})],
         reference=dict(spec={"title": "TechFest 2026 — hackathon registration", "kind": "registration", "description": "Register your team. 60 places.", "max_responses": 60, "theme_color": "#6a3fa0",
                              "fields": [{"id": "team", "type": "short_text", "label": "Team name", "required": True},
                                         {"id": "track", "type": "radio", "label": "Track", "required": True, "options": ["AI", "Web", "IoT"]}]},
                        shares=[{"type": "org", "role": "submitter"}])),
    # ------------------------------------------------------------------ office
    dict(id="O1-leave", ws="office", level=3, owner="ananya.rao@northwind.co",
         prompt="Leave requests for the Engineering team: start date, end date, leave type (sick, casual or earned) and a reason. Managers approve or reject them. People can file as many as they need.",
         paraphrase="Engineering should be able to apply for leave — from/to dates, which kind (sick/casual/earned), why. The Managers group decides approve/reject. Multiple requests per person.",
         checks=[("data", "field", {"type": "date", "count": 2}), ("data", "choice", {"options": ["sick", "casual", "earned"]}),
                 ("data", "rule", "responses_per_person", "many"), ("data", "statuses", ["approv", "reject"]),
                 ("access", "share", {"type": "group", "name": "Engineering", "role": "submitter"}),
                 ("access", "share", {"type": "group", "name": "Managers", "role": "editor"})],
         reference=dict(spec={"title": "Leave request", "kind": "request", "description": "Apply for leave; a manager approves or rejects it.", "responses_per_person": "many", "statuses": ["Pending", "Approved", "Rejected"], "theme_color": "#2f5d62",
                              "fields": [{"id": "start", "type": "date", "label": "Start date", "required": True},
                                         {"id": "end", "type": "date", "label": "End date", "required": True},
                                         {"id": "type", "type": "radio", "label": "Leave type", "required": True, "options": ["Sick", "Casual", "Earned"]},
                                         {"id": "reason", "type": "long_text", "label": "Reason"}]},
                        shares=[{"type": "group", "name": "Engineering", "role": "submitter"}, {"type": "group", "name": "Managers", "role": "editor"}])),
    dict(id="O2-lunch-poll", ws="office", level=1, owner="vikram@northwind.co",
         prompt="Team lunch poll for the Platform team: pizza, biryani or salad. Show the results after people vote.",
         paraphrase="Quick vote for the Platform team on lunch — pizza, biryani, or salad? Let them see the tally once they've voted.",
         checks=[("data", "choice", {"options": ["pizza", "biryani", "salad"]}), ("data", "rule", "show_results", "after_submit"),
                 ("data", "max_fields", 2), ("access", "share", {"type": "group", "name": "Platform team", "role": "submitter"})],
         reference=dict(spec={"title": "Team lunch poll", "kind": "poll", "description": "Vote for Friday lunch.", "show_results": "after_submit", "theme_color": "#9a4a24",
                              "fields": [{"id": "food", "type": "radio", "label": "Lunch?", "required": True, "options": ["Pizza", "Biryani", "Salad"]}]},
                        shares=[{"type": "group", "name": "Platform team", "role": "submitter"}])),
    dict(id="O3-expenses", ws="office", level=3, owner="sara@northwind.co",
         prompt="Expense claims for all staff: receipt upload (PDF or a photo), amount, date of the expense. Statuses Submitted, Approved, Paid. Finance updates the status.",
         paraphrase="Everyone at the company should be able to claim expenses: attach the receipt (PDF/image), the amount and the date spent. It goes Submitted → Approved → Paid, handled by Finance.",
         checks=[("data", "field", {"type": "file", "accept_has": [".pdf", ".jpg|.jpeg|.png"]}), ("data", "field", {"type": "number"}),
                 ("data", "field", {"type": "date"}), ("data", "statuses", ["submit", "approv", "paid"]), ("data", "rule", "responses_per_person", "many"),
                 ("access", "share", {"type": "org|group:All staff", "role": "submitter"}), ("access", "share", {"type": "group", "name": "Finance", "role": "editor"})],
         reference=dict(spec={"title": "Expense claim", "kind": "request", "description": "Attach the receipt; Finance updates the status.", "responses_per_person": "many", "statuses": ["Submitted", "Approved", "Paid"], "theme_color": "#4a5a2e",
                              "fields": [{"id": "receipt", "type": "file", "label": "Receipt", "required": True, "accept": [".pdf", ".jpg", ".png"], "max_mb": 10},
                                         {"id": "amount", "type": "number", "label": "Amount", "required": True},
                                         {"id": "spent_on", "type": "date", "label": "Date of expense", "required": True}]},
                        shares=[{"type": "org", "role": "submitter"}, {"type": "group", "name": "Finance", "role": "editor"}])),
    # ------------------------------------------------------------------ general (public links, no accounts)
    dict(id="G1-rsvp", ws="general", level=1, owner="riya@example.com",
         prompt="RSVP for my birthday party on 20 December 2026: will you come, and how many guests are you bringing?",
         paraphrase="Are you coming to my birthday on 20 Dec 2026? Need a yes/no and the number of people they'll bring.",
         checks=[("data", "field", {"type": "short_text", "label": "name"}), ("data", "choice", {"options": ["yes", "no"]}),
                 ("data", "field", {"type": "number"}), ("access", "share", {"type": "public"})],
         reference=dict(spec={"title": "Birthday RSVP", "kind": "rsvp", "description": "Let me know if you can come.", "theme_color": "#a8452f", "closes_at": "2026-12-19T23:59",
                              "fields": [{"id": "name", "type": "short_text", "label": "Your name", "required": True},
                                         {"id": "coming", "type": "radio", "label": "Will you come?", "required": True, "options": ["Yes", "No"]},
                                         {"id": "guests", "type": "number", "label": "How many guests?", "min": 0}]},
                        shares=[{"type": "public", "role": "submitter"}])),
    dict(id="G2-workshop", ws="general", level=2, owner="alex@example.com",
         prompt="Sourdough workshop sign-up: two sessions on Saturday 12 December 2026, 10am and 2pm, 8 places each. Ask for name and email.",
         paraphrase="Sign-ups for my sourdough class on Sat 12 Dec 2026 — a 10 am and a 2 pm session, eight spots in each. I need their name and email address.",
         checks=[("data", "choice", {"options": ["10", "2"], "limits": 8}), ("data", "field", {"type": "email"}),
                 ("data", "field", {"type": "short_text", "label": "name"}), ("access", "share", {"type": "public"})],
         reference=dict(spec={"title": "Sourdough workshop", "kind": "registration", "description": "Pick a session. Eight places each.", "theme_color": "#5a6b2e",
                              "fields": [{"id": "name", "type": "short_text", "label": "Name", "required": True},
                                         {"id": "email", "type": "email", "label": "Email", "required": True},
                                         {"id": "session", "type": "radio", "label": "Session", "required": True, "options": ["10am", "2pm"], "limits": {"10am": 8, "2pm": 8}}]},
                        shares=[{"type": "public", "role": "submitter"}])),
]

# Questions to the Insights agent and a Reminder run, on a seeded app whose true answers come from the database.
ASSIGNMENT = "Assignment 3 — Data Structures"
OTHER = [
    dict(id="I1-count", ws="university", level=1, kind="insights", owner="prof.sharma@riverside.edu", app=ASSIGNMENT, truth="count",
         prompt="How many students have submitted so far?", paraphrase="What's the submission count right now?"),
    dict(id="I2-missing", ws="university", level=2, kind="insights", owner="prof.sharma@riverside.edu", app=ASSIGNMENT, truth="missing",
         prompt="Who hasn't submitted yet?", paraphrase="List the people who still owe me this assignment."),
    dict(id="R1-remind", ws="university", level=2, kind="reminder", owner="prof.sharma@riverside.edu", app=ASSIGNMENT, truth="missing",
         prompt="(scheduled reminder before the deadline)", paraphrase=None),
]

for c in BUILD:
    c["kind"] = "build"

ALL = BUILD + OTHER
