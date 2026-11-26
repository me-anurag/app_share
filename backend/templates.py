"""Starting points for each workspace mode.

A template is a complete, valid app: it can be created instantly (no AI needed), or handed to the
agent team as a starting point ("customize"). Deadlines are relative (closes_in_days).
"""
from datetime import datetime, timedelta

from .db import MODE
from .spec import validate_spec

F = lambda id, type, label, **kw: {"id": id, "type": type, "label": label, **kw}   # noqa: E731

UNIVERSITY = [
    {"id": "assignment", "name": "Assignment submission", "icon": "inbox", "blurb": "Collect files by a deadline; replace until it closes.",
     "prompt": "Assignment submission portal for my section, PDF or DOCX only, due next Friday 11:59 pm.",
     "spec": {"title": "Assignment submission", "kind": "assignment", "closes_in_days": 7,
              "description": "Upload your work as one PDF or DOCX (max 10 MB). You can replace it until the deadline.",
              "fields": [F("file", "file", "Your file", required=True, accept=[".pdf", ".docx"], max_mb=10), F("note", "long_text", "Notes for the grader")]}},
    {"id": "feedback", "name": "Anonymous course feedback", "icon": "message", "blurb": "Ratings and comments; names are never shown.",
     "prompt": "Anonymous mid-semester feedback for my course with ratings for clarity and pace and two open questions.",
     "spec": {"title": "Course feedback", "kind": "feedback", "anonymous": True, "closes_in_days": 7,
              "description": "Anonymous — the instructor sees answers, never names.",
              "fields": [F("clarity", "rating", "How clear are the lectures?", required=True),
                         F("pace", "radio", "The pace is…", options=["Too slow", "About right", "Too fast"], required=True),
                         F("keep", "long_text", "What should stay the same?"), F("change", "long_text", "What should change?")]}},
    {"id": "event", "name": "Event registration", "icon": "users", "blurb": "Sign-ups with a seat limit that closes when full.",
     "prompt": "Registration for a guest lecture next Wednesday, 120 seats, ask for department and year.",
     "spec": {"title": "Event registration", "kind": "registration", "max_responses": 100, "closes_in_days": 10,
              "description": "Register to reserve your seat. Places are limited.",
              "fields": [F("dept", "select", "Department", options=["CSE", "ECE", "ME", "Civil", "Other"], required=True),
                         F("year", "radio", "Year", options=["1", "2", "3", "4"], required=True), F("q", "short_text", "A question for the speaker")]}},
    {"id": "slots", "name": "Lab or office-hour slots", "icon": "clock", "blurb": "People pick a time; each slot has limited places.",
     "prompt": "Office hours booking for next week with four 30-minute slots, two students per slot.",
     "spec": {"title": "Book a slot", "kind": "booking", "closes_in_days": 5, "description": "Pick one slot. Full slots can't be chosen.",
              "fields": [F("slot", "radio", "Slot", required=True, options=["Mon 2:00", "Mon 2:30", "Wed 11:00", "Wed 11:30"],
                           limits={"Mon 2:00": 2, "Mon 2:30": 2, "Wed 11:00": 2, "Wed 11:30": 2}), F("topic", "short_text", "What do you want to discuss?")]}},
    {"id": "poll", "name": "Quick class poll", "icon": "chart", "blurb": "One question; students see results after voting.",
     "prompt": "Quick poll asking my class which day works for the extra lecture, show results after voting.",
     "spec": {"title": "Quick poll", "kind": "poll", "show_results": "after_submit", "closes_in_days": 3,
              "description": "Vote once; you'll see the results straight after.",
              "fields": [F("choice", "radio", "Which works best?", required=True, options=["Option A", "Option B", "Option C"])]}},
    {"id": "request", "name": "Requests with tracking", "icon": "list", "blurb": "Complaints or requests that move Open → Resolved.",
     "prompt": "Hostel maintenance request form with location, problem type and a photo, tracked Open, In progress, Resolved.",
     "spec": {"title": "Request form", "kind": "request", "responses_per_person": "many", "statuses": ["Open", "In progress", "Resolved"],
              "description": "Send a request. You'll be notified as it moves along.",
              "fields": [F("where", "short_text", "Where?", required=True), F("details", "long_text", "Details", required=True),
                         F("photo", "file", "Photo (optional)", accept=[".jpg", ".jpeg", ".png"], max_mb=8)]}},
    {"id": "checkin", "name": "Class check-in", "icon": "check", "blurb": "A 10-second attendance check with one question.",
     "prompt": "Attendance check-in for today's lecture that closes in 15 minutes with one question about today's topic.",
     "spec": {"title": "Today's check-in", "kind": "form", "closes_in_days": 1, "description": "Tap submit to mark yourself present.",
              "fields": [F("here", "checkbox", "Attendance", options=["I'm present"], required=True), F("doubt", "short_text", "Any doubt from today?")]}},
    {"id": "club", "name": "Club membership drive", "icon": "users", "blurb": "Recruit members with interests and availability.",
     "prompt": "Coding Club membership form asking interests, experience level and weekly availability.",
     "spec": {"title": "Join the club", "kind": "sign-up", "description": "Tell us a little about yourself.",
              "fields": [F("interest", "checkbox", "Interested in", options=["Competitive programming", "Web", "AI / ML", "Open source"]),
                         F("level", "radio", "Experience", options=["Beginner", "Intermediate", "Advanced"], required=True),
                         F("why", "long_text", "Why do you want to join?")]}},
]

OFFICE = [
    {"id": "leave", "name": "Leave request", "icon": "list", "blurb": "Pending → Approved or Rejected, with notifications.",
     "prompt": "Leave request form for my team: type, dates, reason; managers approve or reject.",
     "spec": {"title": "Leave request", "kind": "request", "responses_per_person": "many", "statuses": ["Pending", "Approved", "Rejected"],
              "description": "Request time off; you'll be notified of the decision.",
              "fields": [F("type", "select", "Type", options=["Casual", "Sick", "Earned", "Work from home"], required=True),
                         F("from", "date", "From", required=True), F("to", "date", "To", required=True), F("reason", "long_text", "Reason")]}},
    {"id": "it", "name": "IT help desk", "icon": "wrench", "blurb": "Tickets tracked Open → In progress → Resolved.",
     "prompt": "IT support ticket form with category, urgency, description and optional screenshot.",
     "spec": {"title": "IT help desk", "kind": "request", "responses_per_person": "many", "statuses": ["Open", "In progress", "Resolved"],
              "description": "Tell IT what's wrong; track your ticket here.",
              "fields": [F("cat", "radio", "Category", options=["Laptop", "Access", "Network", "Software", "Other"], required=True),
                         F("urgency", "radio", "Urgency", options=["Low", "Normal", "Blocking"], required=True),
                         F("problem", "long_text", "Describe the problem", required=True), F("shot", "file", "Screenshot", accept=[".png", ".jpg", ".pdf"], max_mb=8)]}},
    {"id": "expense", "name": "Expense claim", "icon": "inbox", "blurb": "Amount and receipt; Submitted → Approved → Paid.",
     "prompt": "Expense claim form with date, category, amount in rupees and a required receipt; finance approves and marks paid.",
     "spec": {"title": "Expense claim", "kind": "request", "responses_per_person": "many", "statuses": ["Submitted", "Approved", "Paid"],
              "description": "Claim a work expense with its receipt.",
              "fields": [F("date", "date", "Date", required=True), F("cat", "select", "Category", options=["Travel", "Meals", "Software", "Other"], required=True),
                         F("amount", "number", "Amount (₹)", min=1, required=True), F("receipt", "file", "Receipt", accept=[".pdf", ".jpg", ".png"], required=True)]}},
    {"id": "pulse", "name": "Anonymous pulse survey", "icon": "message", "blurb": "A short engagement check-in; no names.",
     "prompt": "Anonymous monthly pulse survey with three ratings and one open question.",
     "spec": {"title": "Pulse survey", "kind": "survey", "anonymous": True, "closes_in_days": 7, "description": "Anonymous and quick.",
              "fields": [F("mood", "rating", "How was your month?", required=True), F("load", "radio", "Workload", options=["Too light", "About right", "Too heavy"], required=True),
                         F("change", "long_text", "One thing we should change")]}},
    {"id": "poll", "name": "Team poll", "icon": "chart", "blurb": "Decide quickly; everyone sees the result.",
     "prompt": "Team poll for the offsite venue with four options, results visible after voting.",
     "spec": {"title": "Team poll", "kind": "poll", "show_results": "after_submit", "closes_in_days": 2,
              "fields": [F("pick", "radio", "Your pick", required=True, options=["Option A", "Option B", "Option C"])]}},
    {"id": "workshop", "name": "Training sessions", "icon": "users", "blurb": "Sessions with a fixed number of places each.",
     "prompt": "Registration for an internal training with two sessions of 10 places each.",
     "spec": {"title": "Training registration", "kind": "registration", "closes_in_days": 7,
              "fields": [F("session", "radio", "Session", required=True, options=["Session 1", "Session 2"], limits={"Session 1": 10, "Session 2": 10}),
                         F("goal", "short_text", "What do you want to get out of it?")]}},
    {"id": "room", "name": "Meeting room booking", "icon": "clock", "blurb": "Book a room and time; full slots disappear.",
     "prompt": "Book the large meeting room for next week, one-hour slots, one booking per slot.",
     "spec": {"title": "Book the meeting room", "kind": "booking", "responses_per_person": "many",
              "fields": [F("slot", "select", "Slot", required=True, options=["Mon 10–11", "Mon 3–4", "Tue 11–12", "Thu 2–3"],
                           limits={"Mon 10–11": 1, "Mon 3–4": 1, "Tue 11–12": 1, "Thu 2–3": 1}), F("purpose", "short_text", "Purpose", required=True)]}},
    {"id": "onboarding", "name": "New-joiner checklist", "icon": "check", "blurb": "First-week checklist new joiners tick off.",
     "prompt": "Onboarding checklist for new joiners in their first week.",
     "spec": {"title": "First-week checklist", "kind": "form",
              "fields": [F("done", "checkbox", "Done so far", options=["Laptop set up", "Accounts working", "Met my buddy", "Read the handbook", "Payroll details submitted"]),
                         F("help", "long_text", "Anything you need help with?")]}},
]

GENERAL = [
    {"id": "rsvp", "name": "Party RSVP", "icon": "users", "blurb": "Guests answer with one link; no account needed.",
     "prompt": "RSVP for my birthday dinner next Saturday at 8 pm, ask plus-ones and food preferences.",
     "spec": {"title": "Are you coming?", "kind": "rsvp", "closes_in_days": 10,
              "fields": [F("name", "short_text", "Your name", required=True), F("coming", "radio", "Coming?", options=["Yes", "Maybe", "No"], required=True),
                         F("plus", "number", "Bringing anyone? (number)", min=0, max=3), F("food", "checkbox", "Food", options=["Vegetarian", "Vegan", "No preference"])]}},
    {"id": "poll", "name": "Poll for a group", "icon": "chart", "blurb": "Everyone votes from a link; results are live.",
     "prompt": "Poll for my friends to pick a weekend trip destination, show results to everyone.",
     "spec": {"title": "Let's decide", "kind": "poll", "show_results": "always", "closes_in_days": 3,
              "fields": [F("pick", "radio", "Your vote", required=True, options=["Option A", "Option B", "Option C"]), F("name", "short_text", "Your name (optional)")]}},
    {"id": "feedback", "name": "Customer feedback", "icon": "message", "blurb": "Anonymous ratings from a QR code or link.",
     "prompt": "Anonymous customer feedback for my café with ratings for food and service.",
     "spec": {"title": "How did we do?", "kind": "feedback", "anonymous": True,
              "fields": [F("overall", "rating", "Overall", required=True), F("again", "radio", "Would you come back?", options=["Yes", "Maybe", "No"]),
                         F("say", "long_text", "Anything else?")]}},
    {"id": "signup", "name": "Class or workshop sign-up", "icon": "clock", "blurb": "Pick a date; each has limited places.",
     "prompt": "Sign-up for my weekend yoga class with two batches of 8.",
     "spec": {"title": "Sign up", "kind": "registration", "closes_in_days": 7,
              "fields": [F("name", "short_text", "Name", required=True), F("email", "email", "Email", required=True),
                         F("batch", "radio", "Batch", required=True, options=["Saturday", "Sunday"], limits={"Saturday": 8, "Sunday": 8})]}},
    {"id": "potluck", "name": "Potluck — who brings what", "icon": "list", "blurb": "Each dish can be claimed once or twice.",
     "prompt": "Potluck sign-up where each dish can be brought by at most two people.",
     "spec": {"title": "Potluck — who brings what?", "kind": "sign-up", "responses_per_person": "many",
              "fields": [F("name", "short_text", "Your name", required=True),
                         F("dish", "radio", "I'll bring", required=True, options=["Salad", "Main", "Dessert", "Drinks"],
                           limits={"Salad": 2, "Main": 2, "Dessert": 2, "Drinks": 2})]}},
    {"id": "contact", "name": "Contact form", "icon": "message", "blurb": "Let anyone send you a message.",
     "prompt": "Contact form for my portfolio website.",
     "spec": {"title": "Get in touch", "kind": "form", "responses_per_person": "many",
              "fields": [F("name", "short_text", "Name", required=True), F("email", "email", "Email", required=True), F("msg", "long_text", "Message", required=True)]}},
]

ALL = {"university": UNIVERSITY, "office": OFFICE, "general": GENERAL}


def for_mode(mode=MODE):
    return ALL[mode]


def build_spec(tpl):
    """Turn a template into a validated spec (relative deadline -> real date)."""
    spec = dict(tpl["spec"])
    days = spec.pop("closes_in_days", None)
    if days:
        spec["closes_at"] = (datetime.now() + timedelta(days=days)).replace(hour=23, minute=59).strftime("%Y-%m-%dT%H:%M")
    clean, errors = validate_spec(spec)
    return clean, errors


def find(tid, mode=MODE):
    return next((t for t in ALL[mode] if t["id"] == tid), None)
