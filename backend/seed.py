"""Demo workspaces, so each mode looks lived-in the moment it opens.

University - Riverside University: CSE and ECE departments, sections 34ML / 34MK / 23EC, Year 3,
             clubs, faculty and the admin office; apps for teaching, feedback, events, labs and facilities.
Office     - Northwind Labs: departments and teams, managers; leave, IT help desk, expenses, surveys, events.
Personal   - Riya and friends: public-link apps (RSVP, polls, customer feedback, a workshop) answered by guests.
Everything here is fictional.
"""
import json
import os
import secrets
from datetime import datetime, timedelta

from .db import UPLOAD_DIR, add_user, dumps
from .spec import validate_spec


def make_pdf(text):
    """A small valid one-page PDF with real text (for seeded file uploads)."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)
    return out


def _when(days=0, hours=0):
    return (datetime.now() + timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M")


def _ts(hours_ago):
    return (datetime.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


class Seeder:
    def __init__(self, conn):
        self.conn = conn

    def uid(self, email):
        return self.conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]

    def gid(self, name):
        return self.conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()[0]

    def app(self, owner, spec, shares=(), link="restricted", status="published"):
        clean, errors = validate_spec(spec)
        assert not errors, (spec.get("title"), errors)
        slug = secrets.token_urlsafe(6).replace("_", "x").replace("-", "y")
        app_id = self.conn.execute(
            "INSERT INTO apps (slug, owner_id, title, spec, status, link_access, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, self.uid(owner), clean["title"], dumps(clean), status, link, _ts(30), _ts(20))).lastrowid
        for kind, name, role in shares:
            pid = self.gid(name) if kind == "group" else self.uid(name)
            self.conn.execute("INSERT INTO permissions (app_id, principal_type, principal_id, role) VALUES (?, ?, ?, ?)",
                              (app_id, kind, pid, role))
        return app_id, clean

    def respond(self, app_id, who, data, hours_ago=5, status=None, note=None, guest=None, file=None):
        """who: an email, or None with guest=(name, email). file=(field_id, filename, text)."""
        uid = self.uid(who) if who else None
        sid = self.conn.execute(
            "INSERT INTO submissions (app_id, user_id, guest_key, guest_name, guest_email, data, status, status_note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, '{}', ?, ?, ?, ?)",
            (app_id, uid, secrets.token_hex(6) if not uid else None, (guest or (None, None))[0], (guest or (None, None))[1],
             status, note, _ts(hours_ago), _ts(max(0, hours_ago - 1) if status else hours_ago))).lastrowid
        if file:
            fid_name, fname, text = file
            folder = os.path.join(UPLOAD_DIR, str(app_id), str(sid))
            os.makedirs(folder, exist_ok=True)
            body = make_pdf(text)
            path = os.path.join(folder, f"{secrets.token_hex(4)}_{fname}")
            with open(path, "wb") as fh:
                fh.write(body)
            file_id = self.conn.execute(
                "INSERT INTO files (app_id, submission_id, user_id, field_id, original_name, stored_path, size) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (app_id, sid, uid, fid_name, fname, path, len(body))).lastrowid
            data = {**data, fid_name: {"file_id": file_id, "name": fname, "size": len(body)}}
        self.conn.execute("UPDATE submissions SET data = ? WHERE id = ?", (dumps(data), sid))
        return sid


# --------------------------------------------------------------------------- University

def seed_university(conn):
    kinds = {"CSE Department": "department", "ECE Department": "department", "34ML": "section", "34MK": "section",
             "23EC": "section", "Year 3": "year", "Year 2": "year", "All students": "everyone", "Faculty": "staff",
             "Admin office": "staff", "Coding Club": "club", "Photography Club": "club"}
    desc = {"34ML": "B.Tech CSE · Year 3 · Section ML", "34MK": "B.Tech CSE · Year 3 · Section MK",
            "23EC": "B.Tech ECE · Year 2", "Year 3": "All third-year students", "Year 2": "All second-year students",
            "All students": "Every enrolled student", "Faculty": "Teaching staff", "Admin office": "Administration and student affairs",
            "CSE Department": "Computer Science & Engineering", "ECE Department": "Electronics & Communication",
            "Coding Club": "Student coding club", "Photography Club": "Student photography club"}
    D = "@riverside.edu"
    cse3 = ["CSE Department", "Year 3", "All students"]
    people = [
        ("prof.sharma", "Prof. Sharma", "Professor & Head · CSE", "faculty", 1, ["Faculty", "CSE Department"]),
        ("dr.mehta", "Dr. Mehta", "Assistant Professor · CSE", "faculty", 0, ["Faculty", "CSE Department"]),
        ("dr.iyer", "Dr. Iyer", "Associate Professor · ECE", "faculty", 0, ["Faculty", "ECE Department"]),
        ("ms.kapoor", "Ms. Kapoor", "Student Affairs · Admin office", "staff", 0, ["Admin office"]),
        ("aarav", "Aarav Singh", "Student · 34ML", "student", 0, ["34ML"] + cse3),
        ("diya", "Diya Patel", "Student · 34ML", "student", 0, ["34ML"] + cse3),
        ("kabir", "Kabir Verma", "Student · 34ML", "student", 0, ["34ML"] + cse3),
        ("ananya", "Ananya Gupta", "Student · 34ML", "student", 0, ["34ML"] + cse3),
        ("rohan", "Rohan Das", "Student · 34ML", "student", 0, ["34ML", "Coding Club"] + cse3),
        ("isha", "Isha Rao", "Student · 34MK", "student", 0, ["34MK"] + cse3),
        ("vivaan", "Vivaan Joshi", "Student · 34MK", "student", 0, ["34MK", "Coding Club"] + cse3),
        ("meera", "Meera Nair", "Student · 34MK", "student", 0, ["34MK", "Photography Club"] + cse3),
        ("arjun", "Arjun Menon", "Student · 34MK", "student", 0, ["34MK"] + cse3),
        ("sneha", "Sneha Kulkarni", "Student · 23EC", "student", 0, ["23EC", "ECE Department", "Year 2", "All students"]),
        ("farhan", "Farhan Ali", "Student · 23EC", "student", 0, ["23EC", "ECE Department", "Year 2", "All students", "Photography Club"]),
        ("tara", "Tara Bose", "Student · 23EC", "student", 0, ["23EC", "ECE Department", "Year 2", "All students"]),
    ]
    for e, name, title, kind, admin, groups in people:
        add_user(conn, e + D, name, groups, admin, title, kind, kinds, desc)
    s = Seeder(conn)
    u = lambda e: e + D

    a, _ = s.app(u("prof.sharma"), {
        "title": "Assignment 3 — Data Structures", "kind": "assignment", "closes_at": _when(4), "theme_color": "#1f5f7a",
        "description": "Upload your Assignment 3 report (trees and heaps) as one PDF or DOCX, up to 10 MB. You can replace it until the deadline.",
        "fields": [{"id": "report", "type": "file", "label": "Your report", "required": True, "accept": [".pdf", ".docx"], "max_mb": 10},
                   {"id": "comments", "type": "long_text", "label": "Anything the grader should know?"}]},
        [("group", "34ML", "submitter"), ("user", u("dr.mehta"), "viewer")])
    s.respond(a, u("aarav"), {"comments": "Implemented the AVL rotations iteratively."}, 20,
              file=("report", "aarav_assignment3.pdf", "Assignment 3: AVL trees and binary heaps. Rotations, insertion, deletion and heapify are analysed below."))
    s.respond(a, u("ananya"), {"comments": ""}, 6,
              file=("report", "ananya_A3.pdf", "Binary heaps and AVL trees - complexity analysis and test results for insertion and deletion."))

    a, _ = s.app(u("dr.mehta"), {
        "title": "Mid-semester feedback — Data Structures", "kind": "feedback", "anonymous": True, "closes_at": _when(6), "theme_color": "#4b5d8a",
        "description": "Help me improve the second half of the course. This is anonymous: I see answers, never names.",
        "fields": [{"id": "clarity", "type": "rating", "label": "How clear are the lectures?", "required": True},
                   {"id": "pace", "type": "radio", "label": "The pace is…", "options": ["Too slow", "About right", "Too fast"], "required": True},
                   {"id": "helps", "type": "checkbox", "label": "What helps you most?", "options": ["Live coding", "Slides", "Lab sessions", "Practice problems", "Office hours"]},
                   {"id": "change", "type": "long_text", "label": "One thing you would change"}]},
        [("group", "34ML", "submitter"), ("group", "34MK", "submitter")])
    for who, c, p, h, ch, t in [
        ("aarav", 4, "About right", ["Live coding", "Lab sessions"], "More practice problems before quizzes.", 30),
        ("diya", 5, "About right", ["Live coding"], "", 26), ("kabir", 3, "Too fast", ["Slides", "Office hours"], "Slow down on graph algorithms.", 22),
        ("isha", 4, "Too fast", ["Practice problems"], "Share solutions after labs.", 18), ("vivaan", 5, "About right", ["Live coding", "Practice problems"], "", 9),
        ("meera", 3, "Too fast", ["Lab sessions", "Office hours"], "Recap the previous lecture for five minutes.", 4)]:
        s.respond(a, u(who), {"clarity": c, "pace": p, "helps": h, "change": ch}, t)

    a, _ = s.app(u("ms.kapoor"), {
        "title": "TechFest 2026 — Hackathon registration", "kind": "registration", "max_responses": 60, "closes_at": _when(10), "theme_color": "#6a3fa0",
        "description": "24-hour hackathon on 12–13 December in the main auditorium. Teams of 1–4. Places are limited to 60 teams.",
        "fields": [{"id": "team", "type": "short_text", "label": "Team name", "required": True},
                   {"id": "size", "type": "radio", "label": "Team size", "options": ["1", "2", "3", "4"], "required": True},
                   {"id": "track", "type": "select", "label": "Track", "options": ["Web", "AI / ML", "IoT", "Open"], "required": True},
                   {"id": "needs", "type": "checkbox", "label": "We need", "options": ["Hardware kit", "Cloud credits", "A mentor"]}]},
        [("group", "All students", "submitter"), ("group", "Admin office", "editor")], link="org")
    for who, team, size, track, needs, t in [("rohan", "Null Pointers", "3", "AI / ML", ["Cloud credits"], 40), ("vivaan", "Byte Me", "4", "Web", [], 33),
                                             ("sneha", "Circuit Breakers", "2", "IoT", ["Hardware kit", "A mentor"], 12), ("diya", "Heap of Trouble", "2", "Open", ["A mentor"], 3)]:
        s.respond(a, u(who), {"team": team, "size": size, "track": track, "needs": needs}, t)

    a, _ = s.app(u("dr.mehta"), {
        "title": "Computer Networks lab — choose your slot", "kind": "booking", "closes_at": _when(2), "theme_color": "#2f6f5e",
        "description": "Pick one lab slot for next week. Each slot has 3 places; full slots can't be chosen.",
        "fields": [{"id": "slot", "type": "radio", "label": "Lab slot", "required": True, "options": ["Mon 2–4 pm", "Wed 10–12 am", "Fri 2–4 pm"],
                    "limits": {"Mon 2–4 pm": 3, "Wed 10–12 am": 3, "Fri 2–4 pm": 3}},
                   {"id": "partner", "type": "short_text", "label": "Lab partner (optional)"}]},
        [("group", "34MK", "submitter")])
    for who, slot, t in [("isha", "Mon 2–4 pm", 10), ("arjun", "Mon 2–4 pm", 8), ("meera", "Wed 10–12 am", 5)]:
        s.respond(a, u(who), {"slot": slot, "partner": ""}, t)

    a, _ = s.app(u("prof.sharma"), {
        "title": "Year 3 elective — which would you take?", "kind": "poll", "show_results": "after_submit", "closes_at": _when(5), "theme_color": "#8a4b2a",
        "description": "Helps the department plan next semester's electives. You'll see the results after voting.",
        "fields": [{"id": "elective", "type": "radio", "label": "Your first choice", "required": True,
                    "options": ["Cloud Computing", "Computer Vision", "Blockchain", "Human–Computer Interaction"]}]},
        [("group", "Year 3", "submitter")])
    for who, e, t in [("aarav", "Computer Vision", 30), ("kabir", "Cloud Computing", 20), ("ananya", "Computer Vision", 15),
                      ("isha", "Human–Computer Interaction", 12), ("vivaan", "Cloud Computing", 6), ("arjun", "Computer Vision", 2)]:
        s.respond(a, u(who), {"elective": e}, t)

    a, _ = s.app(u("ms.kapoor"), {
        "title": "Campus maintenance request", "kind": "request", "responses_per_person": "many", "theme_color": "#7a5a1e",
        "statuses": ["Open", "In progress", "Resolved"],
        "description": "Report anything broken on campus. You'll get a notification as it moves from Open to Resolved.",
        "fields": [{"id": "where", "type": "select", "label": "Where?", "required": True, "options": ["Hostel A", "Hostel B", "Library", "Labs", "Classrooms", "Canteen"]},
                   {"id": "what", "type": "radio", "label": "Type of problem", "required": True, "options": ["Electrical", "Plumbing", "Furniture", "Wi-Fi / Internet", "Cleaning", "Other"]},
                   {"id": "details", "type": "long_text", "label": "What's wrong?", "required": True},
                   {"id": "photo", "type": "file", "label": "Photo (optional)", "accept": [".jpg", ".jpeg", ".png"], "max_mb": 8}]},
        [("group", "All students", "submitter"), ("group", "Faculty", "submitter"), ("group", "Admin office", "editor")], link="org")
    s.respond(a, u("kabir"), {"where": "Hostel B", "what": "Wi-Fi / Internet", "details": "No Wi-Fi on the 3rd floor since Monday."}, 50, status="In progress", note="Router replacement ordered.")
    s.respond(a, u("sneha"), {"where": "Labs", "what": "Electrical", "details": "Two sockets dead at bench 4 in the electronics lab."}, 30, status="Resolved", note="Fixed on Wednesday.")
    s.respond(a, u("dr.iyer"), {"where": "Classrooms", "what": "Furniture", "details": "Projector screen in C-204 is stuck."}, 3, status="Open")

    a, _ = s.app(u("meera"), {
        "title": "Photography Club — sunrise photo walk", "kind": "sign-up", "max_responses": 15, "closes_at": _when(3), "theme_color": "#3d5a73",
        "description": "Saturday 6 am at the main gate. Phones are fine. 15 places.",
        "fields": [{"id": "camera", "type": "radio", "label": "What will you bring?", "options": ["Phone", "Camera", "Both"], "required": True},
                   {"id": "first", "type": "radio", "label": "First photo walk?", "options": ["Yes", "No"]}]},
        [("group", "Photography Club", "submitter"), ("group", "All students", "submitter")], link="org")
    for who, cam, f, t in [("farhan", "Camera", "No", 14), ("tara", "Phone", "Yes", 7), ("arjun", "Phone", "Yes", 2)]:
        s.respond(a, u(who), {"camera": cam, "first": f}, t)


# --------------------------------------------------------------------------- Office

def seed_office(conn):
    kinds = {"Engineering": "department", "Design": "department", "Sales": "department", "People & HR": "department",
             "Finance": "department", "IT": "team", "Platform team": "team", "Managers": "team", "All staff": "everyone"}
    desc = {"Engineering": "Software engineering", "Design": "Product design", "Sales": "Sales and accounts",
            "People & HR": "People operations", "Finance": "Finance and accounts", "IT": "IT support",
            "Platform team": "Backend platform squad", "Managers": "People managers", "All staff": "Everyone at Northwind Labs"}
    D = "@northwind.co"
    people = [
        ("ananya.rao", "Ananya Rao", "Head of People", "manager", 1, ["People & HR", "Managers"]),
        ("vikram", "Vikram Shah", "Engineering Manager", "manager", 0, ["Engineering", "Managers", "Platform team"]),
        ("sara", "Sara Thomas", "Finance Lead", "manager", 0, ["Finance", "Managers"]),
        ("kiran", "Kiran Das", "IT Administrator", "employee", 0, ["IT"]),
        ("priya", "Priya Nair", "Product Designer", "employee", 0, ["Design"]),
        ("arjun", "Arjun Mehta", "Backend Engineer", "employee", 0, ["Engineering", "Platform team"]),
        ("rahul", "Rahul Verma", "Frontend Engineer", "employee", 0, ["Engineering", "Platform team"]),
        ("dev", "Dev Patel", "QA Engineer", "employee", 0, ["Engineering"]),
        ("neha", "Neha Gupta", "Account Executive", "employee", 0, ["Sales"]),
        ("omar", "Omar Khan", "Sales Manager", "manager", 0, ["Sales", "Managers"]),
    ]
    for e, name, title, kind, admin, groups in people:
        add_user(conn, e + D, name, groups + ["All staff"], admin, title, kind, kinds, desc)
    s = Seeder(conn)
    u = lambda e: e + D

    a, _ = s.app(u("ananya.rao"), {
        "title": "Leave request", "kind": "request", "responses_per_person": "many", "statuses": ["Pending", "Approved", "Rejected"], "theme_color": "#2f5d62",
        "description": "Request time off. Your manager approves it here and you'll be notified either way.",
        "fields": [{"id": "type", "type": "select", "label": "Type of leave", "required": True, "options": ["Casual", "Sick", "Earned", "Work from home"]},
                   {"id": "from", "type": "date", "label": "From", "required": True}, {"id": "to", "type": "date", "label": "To", "required": True},
                   {"id": "reason", "type": "long_text", "label": "Reason"}, {"id": "cover", "type": "short_text", "label": "Who covers for you?"}]},
        [("group", "All staff", "submitter"), ("group", "Managers", "editor")], link="org")
    d = lambda n: (datetime.now() + timedelta(days=n)).strftime("%Y-%m-%d")
    s.respond(a, u("arjun"), {"type": "Earned", "from": d(10), "to": d(14), "reason": "Family trip.", "cover": "Rahul"}, 48, status="Approved", note="Enjoy! — Vikram")
    s.respond(a, u("priya"), {"type": "Casual", "from": d(3), "to": d(3), "reason": "Moving house.", "cover": ""}, 20, status="Pending")
    s.respond(a, u("neha"), {"type": "Work from home", "from": d(1), "to": d(2), "reason": "Plumber visit.", "cover": "Omar"}, 4, status="Pending")

    a, _ = s.app(u("kiran"), {
        "title": "IT help desk", "kind": "request", "responses_per_person": "many", "statuses": ["Open", "In progress", "Resolved"], "theme_color": "#33507a",
        "description": "Anything not working? Tell IT. You'll see the status of your ticket here.",
        "fields": [{"id": "cat", "type": "radio", "label": "Category", "required": True, "options": ["Laptop", "Access & accounts", "Network", "Software", "Other"]},
                   {"id": "urgency", "type": "radio", "label": "How urgent?", "required": True, "options": ["Low", "Normal", "Blocking my work"]},
                   {"id": "problem", "type": "long_text", "label": "Describe the problem", "required": True},
                   {"id": "shot", "type": "file", "label": "Screenshot (optional)", "accept": [".png", ".jpg", ".jpeg", ".pdf"], "max_mb": 8}]},
        [("group", "All staff", "submitter"), ("group", "IT", "editor")], link="org")
    s.respond(a, u("rahul"), {"cat": "Access & accounts", "urgency": "Blocking my work", "problem": "Can't log in to the staging VPN."}, 26, status="Resolved", note="Certificate renewed.")
    s.respond(a, u("dev"), {"cat": "Laptop", "urgency": "Normal", "problem": "Battery drains in under two hours."}, 9, status="In progress", note="Replacement battery arriving Thursday.")
    s.respond(a, u("neha"), {"cat": "Software", "urgency": "Low", "problem": "Need a CRM licence for the new territory."}, 1, status="Open")

    a, _ = s.app(u("sara"), {
        "title": "Expense claim", "kind": "request", "responses_per_person": "many", "statuses": ["Submitted", "Approved", "Paid"], "theme_color": "#4a5a2e",
        "description": "Claim work expenses with a receipt. Paid claims arrive with the next salary run.",
        "fields": [{"id": "date", "type": "date", "label": "Date of expense", "required": True},
                   {"id": "cat", "type": "select", "label": "Category", "required": True, "options": ["Travel", "Meals with clients", "Software", "Equipment", "Other"]},
                   {"id": "amount", "type": "number", "label": "Amount (₹)", "required": True, "min": 1},
                   {"id": "receipt", "type": "file", "label": "Receipt", "required": True, "accept": [".pdf", ".jpg", ".jpeg", ".png"], "max_mb": 10},
                   {"id": "notes", "type": "short_text", "label": "Notes"}]},
        [("group", "All staff", "submitter"), ("group", "Finance", "editor")], link="org")
    s.respond(a, u("neha"), {"date": d(-6), "cat": "Meals with clients", "amount": 2400, "notes": "Lunch with Acme team"}, 70, status="Paid",
              file=("receipt", "acme_lunch_receipt.pdf", "Receipt: Lunch for 3, total 2400 INR, paid by card."))
    s.respond(a, u("arjun"), {"date": d(-2), "cat": "Travel", "amount": 860, "notes": "Cab to the client site"}, 10, status="Submitted",
              file=("receipt", "cab_receipt.pdf", "Ride receipt: 860 INR, 23 km, card payment."))

    a, _ = s.app(u("ananya.rao"), {
        "title": "Q4 engagement pulse", "kind": "survey", "anonymous": True, "closes_at": _when(7), "theme_color": "#6b3f5e",
        "description": "Five minutes, completely anonymous. Results are shared with everyone as a summary.",
        "fields": [{"id": "recognised", "type": "rating", "label": "I feel recognised for my work", "required": True},
                   {"id": "tools", "type": "rating", "label": "I have what I need to do my job well", "required": True},
                   {"id": "recommend", "type": "number", "label": "How likely are you to recommend Northwind as a workplace? (0–10)", "min": 0, "max": 10, "required": True},
                   {"id": "change", "type": "long_text", "label": "One thing we should change"}]},
        [("group", "All staff", "submitter")], link="org")
    for who, r1, r2, rec, ch, t in [("arjun", 4, 3, 8, "Fewer meetings on Fridays.", 40), ("rahul", 5, 4, 9, "", 30), ("priya", 3, 3, 6, "Better design-review rituals.", 22),
                                    ("neha", 4, 2, 7, "Faster laptop refresh.", 15), ("dev", 3, 4, 7, "", 9), ("omar", 4, 4, 8, "More cross-team demos.", 3)]:
        s.respond(a, u(who), {"recognised": r1, "tools": r2, "recommend": rec, "change": ch}, t)

    a, _ = s.app(u("vikram"), {
        "title": "Friday team lunch — where to?", "kind": "poll", "show_results": "after_submit", "closes_at": _when(1), "theme_color": "#9a4a24",
        "description": "Platform team lunch this Friday at 1 pm. Most votes wins.",
        "fields": [{"id": "place", "type": "radio", "label": "Pick one", "required": True, "options": ["Thai Garden", "Burger Lab", "South Spice", "Order in"]}]},
        [("group", "Platform team", "submitter")])
    for who, p, t in [("arjun", "South Spice", 6), ("rahul", "Burger Lab", 4), ("vikram", "South Spice", 2)]:
        s.respond(a, u(who), {"place": p}, t)

    a, _ = s.app(u("priya"), {
        "title": "Workshop: designing for accessibility", "kind": "registration", "max_responses": 16, "closes_at": _when(5), "theme_color": "#2e5e8a",
        "description": "A 90-minute hands-on session. Pick a session; each has 8 places.",
        "fields": [{"id": "session", "type": "radio", "label": "Session", "required": True, "options": ["Tue 3 pm", "Thu 11 am"], "limits": {"Tue 3 pm": 8, "Thu 11 am": 8}},
                   {"id": "role", "type": "select", "label": "Your role", "options": ["Engineering", "Design", "Sales", "Other"]},
                   {"id": "hope", "type": "short_text", "label": "What do you hope to learn?"}]},
        [("group", "All staff", "submitter")], link="org")
    for who, ses, role, t in [("rahul", "Tue 3 pm", "Engineering", 20), ("dev", "Tue 3 pm", "Engineering", 12), ("neha", "Thu 11 am", "Sales", 6), ("omar", "Thu 11 am", "Sales", 2)]:
        s.respond(a, u(who), {"session": ses, "role": role, "hope": ""}, t)


# --------------------------------------------------------------------------- Personal (general)

def seed_general(conn):
    kinds = {"Book club": "list"}
    D = "@example.com"
    people = [("riya", "Riya Kapoor", "Organizer", "member", 1, []), ("sam", "Sam Lee", "", "member", 0, ["Book club"]),
              ("alex", "Alex Morgan", "Owner · Corner Bakery", "member", 0, []), ("jo", "Jo Fernandes", "", "member", 0, ["Book club"])]
    for e, name, title, kind, admin, groups in people:
        add_user(conn, e + D, name, groups, admin, title, kind, kinds, {"Book club": "Monthly book club"})
    s = Seeder(conn)
    u = lambda e: e + D

    a, _ = s.app(u("riya"), {
        "title": "Riya's 30th — are you coming?", "kind": "rsvp", "max_responses": 40, "closes_at": _when(12), "theme_color": "#a8452f",
        "description": "Saturday 14 December, 7 pm at The Courtyard. Let me know by the 10th!",
        "fields": [{"id": "name", "type": "short_text", "label": "Your name", "required": True},
                   {"id": "coming", "type": "radio", "label": "Will you come?", "required": True, "options": ["Yes", "Maybe", "Can't make it"]},
                   {"id": "plus", "type": "number", "label": "How many people with you?", "min": 0, "max": 3},
                   {"id": "food", "type": "checkbox", "label": "Food preferences", "options": ["Vegetarian", "Vegan", "Gluten-free", "No preference"]},
                   {"id": "note", "type": "short_text", "label": "A note for Riya"}]},
        link="public")
    for n, c, p, f, note, t in [("Kavya", "Yes", 1, ["Vegetarian"], "Can't wait!", 50), ("Sam Lee", "Yes", 0, ["No preference"], "", 40),
                                ("Neil", "Maybe", 0, [], "Back from travel that day.", 30), ("Zara", "Yes", 2, ["Vegan"], "", 18), ("Tom", "Can't make it", 0, [], "Happy birthday!", 5)]:
        s.respond(a, None, {"name": n, "coming": c, "plus": p, "food": f, "note": note}, t, guest=(n, None))

    a, _ = s.app(u("sam"), {
        "title": "Book club — next month's book", "kind": "poll", "show_results": "always", "closes_at": _when(4), "theme_color": "#4a3f73",
        "description": "Vote for January's book. Results are visible to everyone.",
        "fields": [{"id": "book", "type": "radio", "label": "Which book?", "required": True,
                    "options": ["The Remains of the Day", "Piranesi", "Klara and the Sun", "The Overstory"]},
                   {"id": "name", "type": "short_text", "label": "Your name (optional)"}]},
        [("group", "Book club", "submitter")], link="public")
    for n, b, t in [("Jo", "Piranesi", 30), ("Mira", "Klara and the Sun", 25), ("Dev", "Piranesi", 20), ("Ana", "The Overstory", 12),
                    ("Lee", "Piranesi", 8), ("Kim", "Klara and the Sun", 3)]:
        s.respond(a, None, {"book": b, "name": n}, t, guest=(n, None))

    a, _ = s.app(u("alex"), {
        "title": "Corner Bakery — how did we do?", "kind": "feedback", "anonymous": True, "theme_color": "#8a5a2b",
        "description": "Thanks for visiting! Two quick ratings help us bake better.",
        "fields": [{"id": "taste", "type": "rating", "label": "Taste", "required": True},
                   {"id": "service", "type": "rating", "label": "Service", "required": True},
                   {"id": "fav", "type": "select", "label": "What did you have?", "options": ["Sourdough", "Croissant", "Cinnamon roll", "Coffee", "Other"]},
                   {"id": "say", "type": "long_text", "label": "Anything else?"}]},
        link="public")
    for ta, se, fav, say, t in [(5, 4, "Croissant", "Best croissant in town.", 40), (4, 5, "Coffee", "", 30), (5, 3, "Sourdough", "Queue was long on Sunday.", 20),
                                (3, 4, "Cinnamon roll", "A bit too sweet for me.", 9), (5, 5, "Croissant", "", 2)]:
        s.respond(a, None, {"taste": ta, "service": se, "fav": fav, "say": say}, t, guest=("Guest", None))

    a, _ = s.app(u("alex"), {
        "title": "Weekend sourdough workshop", "kind": "registration", "closes_at": _when(8), "theme_color": "#5a6b2e",
        "description": "Learn to bake sourdough at Corner Bakery. Pick a morning; 6 places each.",
        "fields": [{"id": "name", "type": "short_text", "label": "Your name", "required": True},
                   {"id": "email", "type": "email", "label": "Email (for directions)", "required": True},
                   {"id": "day", "type": "radio", "label": "Morning", "required": True, "options": ["Saturday 9 am", "Sunday 9 am"], "limits": {"Saturday 9 am": 6, "Sunday 9 am": 6}}]},
        link="public")
    for n, day, t in [("Priya", "Saturday 9 am", 20), ("Omar", "Saturday 9 am", 12), ("Lena", "Sunday 9 am", 4)]:
        s.respond(a, None, {"name": n, "email": f"{n.lower()}@example.com", "day": day}, t, guest=(n, f"{n.lower()}@example.com"))


def seed(conn, mode):
    {"university": seed_university, "office": seed_office, "general": seed_general}[mode](conn)
