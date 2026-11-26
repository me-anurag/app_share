/* AppShare Control Center — rehearsal mode.
   Everything here is pretend data, always marked as such (sim: true):
   - "Rehearsal traffic" feeds fake phones into the Live view only (never the Monitor numbers).
   - Agent scenes replay a typical Builder / Insights run in the Agent theater. */
"use strict";

const Sim = (() => {
  // -------------------------------------------------------------- agent scenes
  function deadlineIn(days) {
    const d = new Date(Date.now() + days * 86400000);
    d.setHours(23, 59, 0, 0);
    return d.toISOString().slice(0, 16);
  }

  function scene(name) {
    if (name === "insights") {
      return [
        { after: 0, ev: { type: "agent_start", agent: "insights", user: "Prof. Sharma", message: "Who in 34ML hasn't submitted Assignment 3 yet?", app: "Assignment 3 Submission" } },
        { after: 400, ev: { type: "agent_llm_start", agent: "insights", step: 1 } },
        { after: 2100, ev: { type: "agent_llm_end", agent: "insights", step: 1, ms: 2100, tokens_in: 1890, tokens_out: 96, stop_reason: "tool_use" } },
        { after: 200, ev: { type: "agent_tool", agent: "insights", step: 1, tool: "get_overview", summary: "read the app overview" } },
        { after: 300, ev: { type: "agent_tool_result", agent: "insights", step: 1, tool: "get_overview", ok: true, summary: "1 responses of 5 expected", items: ["Responses: 1", "Expected: 5", "Deadline: Wed 23:59"] } },
        { after: 200, ev: { type: "agent_tool", agent: "insights", step: 1, tool: "list_missing", summary: "find who hasn't responded" } },
        { after: 300, ev: { type: "agent_tool_result", agent: "insights", step: 1, tool: "list_missing", ok: true, summary: "4 not submitted", items: ["Ananya Gupta", "Diya Patel", "Kabir Verma", "Rohan Das"] } },
        { after: 300, ev: { type: "agent_llm_start", agent: "insights", step: 2 } },
        { after: 1900, ev: { type: "agent_llm_end", agent: "insights", step: 2, ms: 1900, tokens_in: 2140, tokens_out: 74, stop_reason: "end_turn" } },
        { after: 200, ev: { type: "agent_reply", agent: "insights", ms: 5600, text: "4 of 5 students in 34ML haven't submitted yet: Ananya Gupta, Diya Patel, Kabir Verma and Rohan Das. Only Aarav Singh has submitted. The deadline is Wednesday at 23:59." } },
      ];
    }
    if (name === "review") {
      return [
        { after: 0, ev: { type: "agent_start", agent: "review", user: "Diya Patel", message: "Review Diya Patel's submission to “Assignment 3 — 34ML”.", app: "Assignment 3 — 34ML" } },
        { after: 300, ev: { type: "agent_llm_start", agent: "review", step: 1 } },
        { after: 1200, ev: { type: "agent_llm_end", agent: "review", step: 1, ms: 1200, tokens_in: 1640, tokens_out: 60, stop_reason: "tool_use", model: "claude-haiku-5-5" } },
        { after: 150, ev: { type: "agent_tool", agent: "review", step: 1, tool: "get_assignment", summary: "read the assignment" } },
        { after: 150, ev: { type: "agent_tool_result", agent: "review", step: 1, tool: "get_assignment", ok: true, summary: "assignment read" } },
        { after: 150, ev: { type: "agent_tool", agent: "review", step: 1, tool: "read_submission", summary: "read the submission" } },
        { after: 200, ev: { type: "agent_tool_result", agent: "review", step: 1, tool: "read_submission", ok: true, summary: "1 file · 642 words read" } },
        { after: 300, ev: { type: "agent_llm_start", agent: "review", step: 2 } },
        { after: 1100, ev: { type: "agent_llm_end", agent: "review", step: 2, ms: 1100, tokens_in: 2890, tokens_out: 40, stop_reason: "tool_use", model: "claude-haiku-5-5" } },
        { after: 150, ev: { type: "agent_tool", agent: "review", step: 2, tool: "compare_with_others", summary: "compare with other submissions" } },
        { after: 300, ev: { type: "agent_tool_result", agent: "review", step: 2, tool: "compare_with_others", ok: true, summary: "1 possible copy", items: ["Aarav Singh · identical file"] } },
        { after: 300, ev: { type: "agent_llm_start", agent: "review", step: 3 } },
        { after: 1000, ev: { type: "agent_llm_end", agent: "review", step: 3, ms: 1000, tokens_in: 3010, tokens_out: 88, stop_reason: "tool_use", model: "claude-haiku-5-5" } },
        { after: 150, ev: { type: "agent_tool", agent: "review", step: 3, tool: "submit_review", verdict: "problem", summary: "This file is identical to Aarav Singh's submission.", flags: ["Identical file to Aarav Singh (aarav_report.pdf)"] } },
        { after: 200, ev: { type: "agent_tool_result", agent: "review", step: 3, tool: "submit_review", ok: true, summary: "handed back" } },
        { after: 200, ev: { type: "agent_reply", agent: "review", ms: 4700, text: "Flagged for Prof. Sharma: Diya's file is identical to Aarav's submission." } },
      ];
    }
    if (name === "reminder") {
      return [
        { after: 0, ev: { type: "agent_start", agent: "reminder", user: "the schedule", message: "The deadline for “Assignment 3 — 34ML” is tomorrow.", app: "Assignment 3 — 34ML" } },
        { after: 300, ev: { type: "agent_llm_start", agent: "reminder", step: 1 } },
        { after: 1000, ev: { type: "agent_llm_end", agent: "reminder", step: 1, ms: 1000, tokens_in: 1210, tokens_out: 44, stop_reason: "tool_use", model: "claude-haiku-5-5" } },
        { after: 150, ev: { type: "agent_tool", agent: "reminder", step: 1, tool: "get_overview", summary: "read the app overview" } },
        { after: 150, ev: { type: "agent_tool_result", agent: "reminder", step: 1, tool: "get_overview", ok: true, summary: "2 responses of 5 expected", items: ["Responses: 2", "Expected: 5", "Deadline: tomorrow 23:59"] } },
        { after: 150, ev: { type: "agent_tool", agent: "reminder", step: 1, tool: "list_missing", summary: "find who hasn't responded" } },
        { after: 200, ev: { type: "agent_tool_result", agent: "reminder", step: 1, tool: "list_missing", ok: true, summary: "3 not submitted", items: ["Ananya Gupta", "Kabir Verma", "Rohan Das"] } },
        { after: 300, ev: { type: "agent_llm_start", agent: "reminder", step: 2 } },
        { after: 1200, ev: { type: "agent_llm_end", agent: "reminder", step: 2, ms: 1200, tokens_in: 1530, tokens_out: 96, stop_reason: "tool_use", model: "claude-haiku-5-5" } },
        { after: 150, ev: { type: "agent_tool", agent: "reminder", step: 2, tool: "send_reminders", summary: "3 reminders · “Assignment 3 closes tomorrow”" } },
        { after: 200, ev: { type: "agent_tool_result", agent: "reminder", step: 2, tool: "send_reminders", ok: true, summary: "sent 3", items: ["Ananya Gupta", "Kabir Verma", "Rohan Das"] } },
        { after: 300, ev: { type: "agent_llm_start", agent: "reminder", step: 3 } },
        { after: 700, ev: { type: "agent_llm_end", agent: "reminder", step: 3, ms: 700, tokens_in: 1700, tokens_out: 30, stop_reason: "end_turn", model: "claude-haiku-5-5" } },
        { after: 150, ev: { type: "agent_reply", agent: "reminder", ms: 4100, text: "Reminded Ananya, Kabir and Rohan that Assignment 3 closes tomorrow at 23:59." } },
      ];
    }
    // the build team: Builder hands out the brief; Data + Access work in parallel; Design follows Data
    const due = deadlineIn(5);
    const brief = "Assignment 3 portal for 34ML · PDF or DOCX · due Friday 23:59";
    const fields = [{ type: "info", label: "Instructions" }, { type: "file", label: "Assignment file" }, { type: "long_text", label: "Comments" }];
    const H = "claude-haiku-5-5";
    return [
      { after: 0, ev: { type: "agent_start", agent: "builder", user: "Prof. Sharma", message: "Make a site that receives Assignment 3 for section 34ML. Only PDF or DOCX, deadline this Friday 11:59 PM." } },
      { after: 300, ev: { type: "agent_llm_start", agent: "builder", step: 1 } },
      { after: 1900, ev: { type: "agent_llm_end", agent: "builder", step: 1, ms: 1900, tokens_in: 3120, tokens_out: 210, stop_reason: "tool_use", model: "claude-opus-5-5" } },
      { after: 100, ev: { type: "agent_tool", agent: "builder", step: 1, tool: "ask_data_agent", summary: brief, to: "data" } },
      { after: 100, ev: { type: "agent_tool", agent: "builder", step: 1, tool: "ask_access_agent", summary: brief, to: "access" } },
      { after: 100, ev: { type: "agent_tool", agent: "builder", step: 1, tool: "ask_design_agent", summary: brief, to: "design" } },
      { run: "data", after: 100, ev: { type: "agent_start", agent: "data", user: "Prof. Sharma", message: brief } },
      { run: "access", after: 60, ev: { type: "agent_start", agent: "access", user: "Prof. Sharma", message: brief } },
      { run: "design", after: 60, ev: { type: "agent_start", agent: "design", user: "Prof. Sharma", message: brief } },
      { run: "data", after: 100, ev: { type: "agent_llm_start", agent: "data", step: 1 } },
      { run: "access", after: 50, ev: { type: "agent_llm_start", agent: "access", step: 1 } },
      { run: "data", after: 900, ev: { type: "agent_llm_end", agent: "data", step: 1, ms: 900, tokens_in: 1400, tokens_out: 180, stop_reason: "tool_use", model: H } },
      { run: "data", after: 80, ev: { type: "agent_tool", agent: "data", step: 1, tool: "check_fields", summary: "check 3 fields", fields } },
      { run: "data", after: 80, ev: { type: "agent_tool_result", agent: "data", step: 1, tool: "check_fields", ok: false, summary: "1 problems", problems: ["closes_at 2025-11-28T23:59 is in the past"] } },
      { run: "access", after: 200, ev: { type: "agent_llm_end", agent: "access", step: 1, ms: 1100, tokens_in: 980, tokens_out: 30, stop_reason: "tool_use", model: H } },
      { run: "access", after: 60, ev: { type: "agent_tool", agent: "access", step: 1, tool: "list_groups", summary: "read the group directory" } },
      { run: "access", after: 80, ev: { type: "agent_tool_result", agent: "access", step: 1, tool: "list_groups", ok: true, summary: "4 groups", items: ["34MK · 3", "34ML · 5", "Coding Club · 2", "Faculty · 2"] } },
      { run: "design", after: 100, ev: { type: "agent_llm_start", agent: "design", step: 1 } },
      { run: "data", after: 300, ev: { type: "agent_llm_start", agent: "data", step: 2 } },
      { run: "design", after: 500, ev: { type: "agent_llm_end", agent: "design", step: 1, ms: 800, tokens_in: 1250, tokens_out: 25, stop_reason: "tool_use", model: H } },
      { run: "design", after: 60, ev: { type: "agent_tool", agent: "design", step: 1, tool: "get_fields", summary: "read the Data agent's fields" } },
      { run: "data", after: 700, ev: { type: "agent_llm_end", agent: "data", step: 2, ms: 1000, tokens_in: 1700, tokens_out: 190, stop_reason: "tool_use", model: H } },
      { run: "data", after: 60, ev: { type: "agent_tool", agent: "data", step: 2, tool: "submit_fields", summary: "deliver 3 fields", fields, closes_at: due } },
      { run: "data", after: 60, ev: { type: "agent_tool_result", agent: "data", step: 2, tool: "submit_fields", ok: true, summary: "handed back to the Builder" } },
      { run: "data", after: 60, ev: { type: "agent_reply", agent: "data", ms: 2300, text: "submitted" } },
      { after: 60, ev: { type: "agent_tool_result", agent: "builder", step: 1, tool: "ask_data_agent", ok: true, summary: "3 fields · due Friday" } },
      { run: "design", after: 60, ev: { type: "agent_tool_result", agent: "design", step: 1, tool: "get_fields", ok: true, summary: "3 fields received", items: ["Instructions", "Assignment file", "Comments"] } },
      { run: "access", after: 100, ev: { type: "agent_llm_start", agent: "access", step: 2 } },
      { run: "access", after: 800, ev: { type: "agent_llm_end", agent: "access", step: 2, ms: 800, tokens_in: 1210, tokens_out: 60, stop_reason: "tool_use", model: H } },
      { run: "access", after: 60, ev: { type: "agent_tool", agent: "access", step: 2, tool: "submit_access", summary: "34ML (submitter)", share: ["34ML (submitter)"] } },
      { run: "access", after: 60, ev: { type: "agent_tool_result", agent: "access", step: 2, tool: "submit_access", ok: true, summary: "handed back to the Builder" } },
      { run: "access", after: 60, ev: { type: "agent_reply", agent: "access", ms: 2100, text: "submitted" } },
      { after: 60, ev: { type: "agent_tool_result", agent: "builder", step: 1, tool: "ask_access_agent", ok: true, summary: "34ML (submitter)" } },
      { run: "design", after: 100, ev: { type: "agent_llm_start", agent: "design", step: 2 } },
      { run: "design", after: 800, ev: { type: "agent_llm_end", agent: "design", step: 2, ms: 800, tokens_in: 1600, tokens_out: 30, stop_reason: "tool_use", model: H } },
      { run: "design", after: 60, ev: { type: "agent_tool", agent: "design", step: 2, tool: "check_color", summary: "is #9fd6ff readable?", color: "#9fd6ff" } },
      { run: "design", after: 60, ev: { type: "agent_tool_result", agent: "design", step: 2, tool: "check_color", ok: false, summary: "contrast 1.6:1 — too light" } },
      { run: "design", after: 200, ev: { type: "agent_llm_start", agent: "design", step: 3 } },
      { run: "design", after: 700, ev: { type: "agent_llm_end", agent: "design", step: 3, ms: 700, tokens_in: 1700, tokens_out: 30, stop_reason: "tool_use", model: H } },
      { run: "design", after: 60, ev: { type: "agent_tool", agent: "design", step: 3, tool: "check_color", summary: "is #1f5f7a readable?", color: "#1f5f7a" } },
      { run: "design", after: 60, ev: { type: "agent_tool_result", agent: "design", step: 3, tool: "check_color", ok: true, summary: "contrast 7.1:1 — readable" } },
      { run: "design", after: 200, ev: { type: "agent_llm_start", agent: "design", step: 4 } },
      { run: "design", after: 900, ev: { type: "agent_llm_end", agent: "design", step: 4, ms: 900, tokens_in: 1800, tokens_out: 260, stop_reason: "tool_use", model: H } },
      { run: "design", after: 60, ev: { type: "agent_tool", agent: "design", step: 4, tool: "submit_design", summary: "“Assignment 3 — 34ML” in #1f5f7a", title: "Assignment 3 — 34ML", theme_color: "#1f5f7a",
          description: "Upload your report as one PDF or DOCX (max 10 MB) by Friday 23:59. You can replace it until then." } },
      { run: "design", after: 60, ev: { type: "agent_tool_result", agent: "design", step: 4, tool: "submit_design", ok: true, summary: "handed back to the Builder" } },
      { run: "design", after: 60, ev: { type: "agent_reply", agent: "design", ms: 4900, text: "submitted" } },
      { after: 60, ev: { type: "agent_tool_result", agent: "builder", step: 1, tool: "ask_design_agent", ok: true, summary: "“Assignment 3 — 34ML” · #1f5f7a" } },
      { after: 200, ev: { type: "agent_llm_start", agent: "builder", step: 2 } },
      { after: 1200, ev: { type: "agent_llm_end", agent: "builder", step: 2, ms: 1200, tokens_in: 4200, tokens_out: 40, stop_reason: "tool_use", model: "claude-opus-5-5" } },
      { after: 100, ev: { type: "agent_tool", agent: "builder", step: 2, tool: "save_app", summary: "save the team's draft", team: true } },
      { after: 200, ev: { type: "agent_tool_result", agent: "builder", step: 2, tool: "save_app", ok: true, summary: "valid ✓ saved as /a/Xk3pQ9", link: "/a/Xk3pQ9" } },
      { after: 200, ev: { type: "agent_llm_start", agent: "builder", step: 3 } },
      { after: 1300, ev: { type: "agent_llm_end", agent: "builder", step: 3, ms: 1300, tokens_in: 4500, tokens_out: 90, stop_reason: "end_turn", model: "claude-opus-5-5" } },
      { after: 100, ev: { type: "agent_reply", agent: "builder", ms: 11800, text: "Done — the team built “Assignment 3 — 34ML”: one PDF or DOCX up to 10 MB, closing Friday at 23:59. 34ML is suggested as the audience; check the preview and press Share." } },
    ];
  }

  // -------------------------------------------------------------- rehearsal traffic (Live view only)
  const DEVICES = [
    { id: "sim-1", kind: "phone", label: "Android phone", user: "Aarav Singh", via: "local network" },
    { id: "sim-2", kind: "phone", label: "iPhone", user: "Diya Patel", via: "local network" },
    { id: "sim-3", kind: "laptop", label: "Windows laptop", user: "Prof. Sharma", via: "local network" },
    { id: "sim-4", kind: "phone", label: "Android phone", user: "Kabir Verma", via: "internet" },
    { id: "sim-5", kind: "phone", label: "Android phone", user: "Isha Rao", via: "local network" },
  ];
  let timer = null, joined = 0, n = 0;

  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function send(ev) { Live.onEvent({ id: 0, ts: Date.now(), sim: true, ...ev }); }

  function tick() {
    // devices join one by one at the start
    if (joined < DEVICES.length && (n === 0 || Math.random() < 0.35)) {
      const d = DEVICES[joined++];
      send({ type: "device_new", device: d.id, device_kind: d.kind, device_label: d.label, user: d.user, via: d.via });
      send({ type: "http", method: "GET", path: "/", kind: "page", status: 200, ms: 4, device: d.id, device_kind: d.kind, device_label: d.label, user: d.user });
      setTimeout(() => send({ type: "login", user: d.user }), 600);
    } else if (joined) {
      const d = DEVICES[Math.floor(Math.random() * joined)];
      const base = { device: d.id, device_kind: d.kind, device_label: d.label, user: d.user };
      const r = Math.random();
      if (r < 0.28) send({ type: "http", method: "GET", path: "/a/Xk3pQ9", kind: "page", status: 200, ms: 3, ...base });
      else if (r < 0.62) send({ type: "http", method: "GET", path: pick(["/api/apps", "/api/me", "/api/a/Xk3pQ9"]), kind: "data", status: 200, ms: 6, ...base });
      else if (r < 0.76) {
        send({ type: "http", method: "POST", path: "/api/a/Xk3pQ9/submit", kind: "submit", status: 200, ms: 41, ...base });
        setTimeout(() => send({ type: "submission", user: d.user, title: "Assignment 3 Submission", updated: Math.random() < .3, files: [{ name: pick(["report.pdf", "assignment3.docx", "final.pdf"]), size: 180000 + Math.floor(Math.random() * 900000) }] }), 900);
      } else if (r < 0.84) {
        send({ type: "http", method: "POST", path: "/api/a/Xk3pQ9/submit", kind: "submit", status: 422, ms: 12, ...base });
        setTimeout(() => send({ type: "submission_rejected", user: d.user, title: "Assignment 3 Submission", blocked_file: true, reasons: ["'photo.pdf' does not look like a real .pdf file"] }), 900);
      } else if (r < 0.9) {
        send({ type: "http", method: "GET", path: "/api/a/Xk3pQ9", kind: "data", status: 404, ms: 3, ...base, user: "Isha Rao" });
        setTimeout(() => send({ type: "access_denied", user: "Isha Rao", app: "Assignment 3 Submission", needed: "submitter", had: "no access" }), 600);
      } else {
        send({ type: "http", method: "POST", path: "/api/agent/build", kind: "agent", status: 200, ms: 5200, ...base });
        send({ type: "agent_llm_start" });
        setTimeout(() => send({ type: "agent_llm_end" }), 1600);
      }
    }
    n++;
    timer = setTimeout(tick, 450 + Math.random() * 900);
  }

  function startTraffic() {
    if (timer) return;
    joined = 0; n = 0;
    document.body.classList.add("sim-on");
    document.getElementById("liveSimBadge").classList.remove("hidden");
    tick();
  }
  function stopTraffic() {
    clearTimeout(timer); timer = null;
    document.body.classList.remove("sim-on");
    document.getElementById("liveSimBadge").classList.add("hidden");
    Live.removeSimDevices();
  }

  CC.on("init", () => {
    const t = document.getElementById("simToggle");
    t.onchange = () => (t.checked ? startTraffic() : stopTraffic());
  });

  return { scene, startTraffic, stopTraffic };
})();
