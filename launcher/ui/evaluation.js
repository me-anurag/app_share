/* AppShare Control Center — Evaluation: every number from the 8 chapter topics, how it was obtained, the evidence behind
   it, and four ways to check it on the spot (reproduce, scoring audit, fingerprints, self-test) plus an examiner's own task.
   Everything is read from data/evals/ through /api/eval/*; nothing on this page is typed by hand. */
"use strict";

const Evaluation = (() => {
  const $ = id => document.getElementById(id);
  const E = s => CC.esc(s);
  let S = null, poll = null, armed = false, armTimer = null;
  const KIND = {
    live: ["Live", "The real agents on the real API"],
    replayed: ["Replayed", "Recorded live replies, scored again by the current code (free, identical every time)"],
    measured: ["Measured", "No AI model involved: tests, the scanner, load — measured on this laptop"],
    "self-test": ["Self-test", "A scripted stand-in played the answers: proves the measuring and guard code works, not model quality"],
    missing: ["Not measured", "Not measured yet"],
  };
  const badge = k => `<span class="ev-badge k-${E(k)}" title="${E((KIND[k] || [k, ""])[1])}">${E((KIND[k] || [k])[0])}</span>`;
  const pct = w => w ? `${(w.rate * 100).toFixed(1)}%` : "—";
  const usd = v => v == null ? "—" : `$${(+v).toFixed(4)}`;

  // ------------------------------------------------------------------ skeleton
  function skeleton() {
    $("view-evaluation").innerHTML = `
      <div class="panel ev-head">
        <div><h2>Evaluation</h2><p class="sub">Every number comes from a result file in <code>data/evals/</code>. Tap any number for the evidence behind it.
          Below, four ways to check the numbers on the spot, and a task you can set yourself.</p></div>
        <div class="ev-legend">${Object.keys(KIND).map(badge).join("")}</div>
      </div>
      <div class="ev-trust" id="evTrust"></div>
      <div class="panel ev-job hidden" id="evJob"></div>
      <div class="panel ev-details" id="evDetails"></div>
      <div class="ev-cats" id="evCats"></div>
      <div class="panel" id="evExam"></div>
      <div class="panel" id="evHist"></div>
      <div class="ev-drawer-bg hidden" id="evDrawerBg"><aside class="ev-drawer" id="evDrawer" role="dialog" aria-modal="true"></aside></div>`;
    $("evDrawerBg").onclick = e => { if (e.target.id === "evDrawerBg" || e.target.closest("[data-close]")) closeDrawer(); };
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
    exam();
  }

  async function load() {
    try { S = await CC.api("/api/eval/summary"); }
    catch (e) { $("evCats").innerHTML = `<div class="panel">${E(e.message)}</div>`; return; }
    trust(); details(); cats(); hist(); job(S.job);
  }

  // ------------------------------------------------------------------ the four proofs
  function trust() {
    const A = S.audit, R = S.reproduce, K = S.seals;
    const tests = S.categories.find(c => c.id === "testing").metrics;
    const gate = tests.find(m => m.id === "tests.all"), self = tests.find(m => m.id === "selftest");
    $("evTrust").innerHTML = `
      <div class="panel ev-proof">
        <div class="ev-p-t"><span class="ev-n">1</span>Reproduce</div>
        <p>Feed the recorded replies of the live run through today's code again. Every run and check should come out the same.</p>
        <div class="ev-p-v ${R ? (R.identical_runs === R.runs && R.identical_checks === R.checks ? "ok" : "bad") : ""}">
          ${R ? `${R.identical_runs}/${R.runs} runs · ${R.identical_checks}/${R.checks} checks identical` : "Not reproduced yet"}</div>
        <div class="ev-p-s">${R ? `checked ${E(R.when)} · from ${E(R.source)}` : "Free · about 30 seconds · no API calls"}</div>
        <div class="ev-p-a"><button class="btn sm primary" data-job="reproduce">Reproduce now</button>${R ? `<button class="btn sm" data-ev="reproduce">Details</button>` : ""}</div>
      </div>
      <div class="panel ev-proof">
        <div class="ev-p-t"><span class="ev-n">2</span>Scoring audit</div>
        <p>The headline numbers were re-scored after the checks were corrected. Both scorings, and every difference, are shown.</p>
        ${A.available ? `<div class="ev-p-v">At the live run <b>${pct(A.live_metrics.success)}</b> → re-scored <b>${pct(A.replay_metrics.success)}</b></div>
          <div class="ev-p-s">${A.flipped} check corrected · ${A.added} added · ${A.removed} removed · ${A.runs_changed} runs changed</div>`
          : `<div class="ev-p-v">No live run with a replay yet</div>`}
        <div class="ev-p-a"><button class="btn sm" id="evAudit" ${A.available ? "" : "disabled"}>See every change</button></div>
      </div>
      <div class="panel ev-proof">
        <div class="ev-p-t"><span class="ev-n">3</span>Fingerprints</div>
        <p>Each result file has a SHA-256 fingerprint. Editing a sealed file by hand shows up here as “modified”.</p>
        <div class="ev-p-v ${K.modified.length || K.missing.length ? "bad" : K.sealed ? "ok" : ""}">
          ${K.sealed ? `${K.match}/${K.sealed} files match${K.modified.length ? ` · ${K.modified.length} modified` : ""}${K.missing.length ? ` · ${K.missing.length} missing` : ""}` : "Nothing sealed yet"}</div>
        <div class="ev-p-s">${K.sealed ? `sealed since ${E(K.first_sealed)}` : ""}${K.unsealed.length ? ` · ${K.unsealed.length} new file(s) not sealed` : ""}
          · ${K.committed ? `in git: ${E(K.committed)}` : "<b>not committed to git yet</b>"}</div>
        <div class="ev-p-a"><button class="btn sm" id="evSeal" ${K.unsealed.length ? "" : "disabled"}>Seal new files</button><button class="btn sm" data-ev-info="seals">What this proves</button></div>
      </div>
      <div class="panel ev-proof">
        <div class="ev-p-t"><span class="ev-n">4</span>The tools test themselves</div>
        <p>A deliberately broken run must be caught, and every offline test must pass — no API key needed.</p>
        <div class="ev-p-v ${/caught/.test(self.value) && !/NOT/.test(self.value) ? "ok" : ""}">${E(self.value)}</div>
        <div class="ev-p-s">${E(gate.value)}</div>
        <div class="ev-p-a"><button class="btn sm" data-job="selftest">Run self-test</button><button class="btn sm" data-job="tests">Run the tests</button></div>
      </div>`;
    $("evTrust").querySelectorAll("[data-job]").forEach(b => b.onclick = () => start({ kind: b.dataset.job }));
    $("evTrust").querySelectorAll("[data-ev]").forEach(b => b.onclick = () => openMetric({ id: b.dataset.ev, label: "Reproduce: differences", kind: "measured" }));
    $("evAudit").onclick = openAudit;
    $("evSeal").onclick = async () => { try { await CC.api("/api/eval/seal", {}); CC.toast("New result files sealed", "ok"); load(); } catch (e) { CC.toast(e.message, "bad"); } };
    $("evTrust").querySelector("[data-ev-info=seals]").onclick = () => drawer(`<h3>What the fingerprints prove</h3>
      <p>${E(K.note)}</p><p>Commit <code>evals/SEALS.json</code> to git and push it: the fingerprints and their date then sit in a public history that
      can't be rewritten quietly. Anyone can recompute a file's fingerprint (for example with <code>certutil -hashfile results.json SHA256</code>) and compare.</p>
      ${K.modified.length ? `<h4>Modified since sealed</h4><ul>${K.modified.map(m => `<li><code>${E(m)}</code></li>`).join("")}</ul>` : ""}
      ${K.unsealed.length ? `<h4>Not sealed yet</h4><ul>${K.unsealed.slice(0, 40).map(m => `<li><code>${E(m)}</code></li>`).join("")}</ul>` : ""}`);
  }

  function details() {
    const D = S.run_details;
    if (!D) { $("evDetails").innerHTML = `<p class="sub">No live run yet.</p>`; return; }
    $("evDetails").innerHTML = `<div class="ev-det">
        <div><span class="label">Live run</span><b>${E(D.started)} → ${E(D.finished?.slice(11))}</b></div>
        <div><span class="label">Models</span><b>${E(D.models?.main)} · ${E(D.models?.specialist)}</b></div>
        <div><span class="label">Runs</span><b>${E(D.jobs)}</b></div>
        <div><span class="label">Calculated cost</span><b>${usd(D.cost_usd)}</b></div>
        <div><span class="label">Code now</span><b>git ${E(D.git_now || "—")}</b></div>
        <div><span class="label">Headline source</span><b>${E(S.quality_source)}</b></div>
      </div>${D.code_note ? `<p class="ev-warn">${E(D.code_note)} Independent check for that run: your Anthropic usage page for 25 Nov should show roughly the same spend.</p>` : ""}`;
  }

  // ------------------------------------------------------------------ the eight categories
  function cats() {
    $("evCats").innerHTML = S.categories.map(c => `<section class="panel ev-cat"><h3>${E(c.title)}</h3>
        <div class="ev-rows">${c.metrics.map((m, i) => `<button class="ev-row" data-cat="${c.id}" data-i="${i}">
          <span class="ev-l">${E(m.label).replace(/\*([^*]+)\*/g, "<i>$1</i>")}${m.note ? `<small>${E(m.note)}</small>` : ""}</span>
          <span class="ev-v"><b>${E(m.value)}</b>${m.n ? `<small>${m.k}/${m.n}</small>` : ""}</span>
          ${m.n ? `<span class="ev-ci" title="95% interval ${Math.round(m.lo * 100)}–${Math.round(m.hi * 100)}%"><i style="left:${m.lo * 100}%;width:${(m.hi - m.lo) * 100}%"></i><b style="left:${m.rate * 100}%"></b></span>` : `<span class="ev-ci none"></span>`}
          ${badge(m.kind)}</button>`).join("")}</div></section>`).join("");
    $("evCats").querySelectorAll(".ev-row").forEach(b => b.onclick = () => openMetric(S.categories.find(c => c.id === b.dataset.cat).metrics[+b.dataset.i]));
  }

  // ------------------------------------------------------------------ drawers
  function drawer(html) { $("evDrawer").innerHTML = `<button class="icon-btn ev-x" data-close aria-label="Close">${CC.icon("x")}</button>${html}`; $("evDrawerBg").classList.remove("hidden"); }
  function closeDrawer() { $("evDrawerBg")?.classList.add("hidden"); }

  async function openMetric(m) {
    drawer(`<h3>${E(m.label)}</h3><div class="ev-big">${E(m.value || "")}${m.n ? `<small>${m.k} of ${m.n} · 95% interval ${Math.round(m.lo * 100)}–${Math.round(m.hi * 100)}%</small>` : ""}</div>
      <p>${badge(m.kind)} ${E((KIND[m.kind] || ["", ""])[1])}</p>
      ${m.how ? `<h4>How it is calculated</h4><p class="ev-mono">${E(m.how)}</p>` : ""}
      ${m.source ? `<h4>Source</h4><p class="ev-mono">${E(m.source)}</p>` : ""}${m.note ? `<p class="ev-warn">${E(m.note)}</p>` : ""}
      <h4>Evidence</h4><div id="evEvid" class="sub">Loading…</div>`);
    try {
      const ev = await CC.api(`/api/eval/evidence?id=${encodeURIComponent(m.id)}`);
      $("evEvid").innerHTML = ev.rows.length ? `${ev.note ? `<p class="sub">${E(ev.note)}</p>` : ""}<div class="ev-tbl-wrap"><table class="ev-tbl"><thead><tr>${ev.columns.map(c => `<th>${E(c)}</th>`).join("")}</tr></thead>
        <tbody>${ev.rows.map(r => `<tr ${r.run ? `data-run="${E(r.run)}" class="click"` : ""}>${r.cells.map(c => `<td class="${c === "FAIL" || /^FAIL/.test(c) ? "bad" : c === "pass" ? "ok" : ""}">${E(c === true ? "yes" : c === false ? "no" : c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
        : `<p class="sub">${E(ev.note)}</p>`;
      $("evEvid").querySelectorAll("[data-run]").forEach(tr => tr.onclick = () => openRun(tr.dataset.run));
    } catch (e) { $("evEvid").textContent = e.message; }
  }

  async function openRun(key) {
    const r = await CC.api(`/api/eval/run?key=${encodeURIComponent(key)}`);
    drawer(`<h3>${E(r.case)} · ${E(r.variant)} ${r.idx + 1}</h3>
      <h4>The request</h4><p class="ev-quote">${E(r.prompt)}</p>
      <h4>The agent's reply</h4><p class="ev-quote">${E(r.reply || r.error || "—")}</p>
      <h4>Checks</h4><ul class="ev-checks">${(r.checks || []).map(c => `<li class="${c.passed ? "ok" : "bad"}"><b>${c.passed ? "✓" : "✗"}</b><span>${E(c.agent)}: ${E(c.check)}${c.detail ? `<small>${E(c.detail)}</small>` : ""}</span></li>`).join("")}</ul>
      ${r.reason_texts?.length ? `<h4>Reasons the agents gave</h4><ul class="ev-checks">${r.reason_texts.map(x => `<li><b>·</b><span>${E(x.agent)} (${E(x.tool)}): ${E(x.reason)}</span></li>`).join("")}</ul>` : ""}
      <p class="sub">${r.wall_ms ? `${(r.wall_ms / 1000).toFixed(1)} s` : ""} · ${r.totals ? `${r.totals.llm_calls} model calls · ${r.totals.tool_calls} tool calls · ${usd(r.totals.cost)}` : ""} · agents: ${E((r.agents_used || []).join(", "))}</p>`);
  }

  async function openAudit() {
    const A = await CC.api("/api/eval/audit");
    drawer(`<h3>Scoring audit: the live run, scored twice</h3><p>${E(A.note)}</p>
      <table class="ev-tbl"><thead><tr><th></th><th>Task success</th><th>Checks passed</th></tr></thead><tbody>
        <tr><td>Scored at the live run<br><small class="ev-mono">${E(A.live)}</small></td><td>${pct(A.live_metrics.success)} (${A.live_metrics.success.k}/${A.live_metrics.success.n})</td><td>${pct(A.live_metrics.checks)} (${A.live_metrics.checks.k}/${A.live_metrics.checks.n})</td></tr>
        <tr><td>Re-scored by today's checks<br><small class="ev-mono">${E(A.replay)}</small></td><td>${pct(A.replay_metrics.success)} (${A.replay_metrics.success.k}/${A.replay_metrics.success.n})</td><td>${pct(A.replay_metrics.checks)} (${A.replay_metrics.checks.k}/${A.replay_metrics.checks.n})</td></tr></tbody></table>
      <h4>Checks whose result changed (${A.flipped.length})</h4>
      ${A.flipped.map(f => `<div class="ev-flip"><b>${E(f.check)}</b>: ${f.from ? "pass" : "fail"} → ${f.to ? "pass" : "fail"} in ${f.count} runs
        <p class="sub">The reply sentences it was about — judge for yourself whether they claim the app was shared:</p>
        <ul class="ev-checks">${f.examples.map(x => `<li><b>·</b><span><small>${E(x.run)}</small> “${E(x.text)}”</span></li>`).join("")}</ul></div>`).join("") || "<p class='sub'>None.</p>"}
      <h4>Checks added (${A.added.length})</h4><ul class="ev-checks">${A.added.map(a => `<li><b>+</b><span>${E(a.check)} — ${a.count} runs, ${a.passed} passed</span></li>`).join("") || "<li>None.</li>"}</ul>
      <h4>Checks removed (${A.removed.length})</h4><ul class="ev-checks">${A.removed.map(a => `<li><b>−</b><span>${E(a.check)} — ${a.count} runs</span></li>`).join("") || "<li><b>·</b><span>None — no check was dropped to raise the score.</span></li>"}</ul>
      <h4>Runs whose pass/fail changed (${A.success_changed.length})</h4><p class="sub">${A.success_changed.map(x => `${E(x.run)}: ${x.live ? "pass" : "fail"} → ${x.replay ? "pass" : "fail"}`).join(" · ")}</p>`);
  }

  // ------------------------------------------------------------------ jobs (reproduce, self-test, tests, examiner)
  async function start(body) {
    try { job(await CC.api("/api/eval/job", body)); watch(); }
    catch (e) { CC.toast(e.message, "bad"); }
  }
  function watch() {
    clearInterval(poll);
    poll = setInterval(async () => {
      let j;
      try { j = await CC.api("/api/eval/job"); } catch { return; }
      job(j);
      if (!j.running) { clearInterval(poll); load(); if (j.kind?.startsWith("examiner")) examResult(j.result); }
    }, 800);
  }
  const JOBNAME = { reproduce: "Reproducing the live run from its recording", selftest: "Harness self-test", tests: "Offline regression gate",
                    examiner: "Your task — the real agents are building it", "examiner-replay": "Re-scoring your task from its recording" };
  function job(j) {
    const el = $("evJob");
    if (!j || !j.kind) { el.classList.add("hidden"); return; }
    el.classList.remove("hidden");
    const r = j.result;
    let res = "";
    if (!j.running && r) {
      if (j.kind === "reproduce") res = `${r.identical_runs}/${r.runs} runs and ${r.identical_checks}/${r.checks} checks identical to the earlier scoring`;
      else if (j.kind === "selftest") res = r.caught.length ? `Broken run caught: ${r.caught.join(", ")} · ${r.runs - r.caught.length} correct runs passed` : "The broken run was NOT caught";
      else if (j.kind === "tests") res = `${r.checks} checks in ${r.suites} suites · ${r.failed ? r.failed + " failing" : "all pass"}`;
      else res = `${r.success ? "PASS" : "FAIL"} · ${r.checks.filter(c => c.passed).length}/${r.checks.length} checks · ${usd(r.cost_usd)}`;
    }
    el.innerHTML = `<div class="ev-job-h"><b>${E(JOBNAME[j.kind] || j.kind)}</b><span class="${j.running ? "run" : j.ok ? "ok" : "bad"}">${j.running ? "running…" : j.ok ? "done" : "failed"}</span>
        <span class="sub">started ${E(j.started)}</span></div>${res ? `<div class="ev-job-r">${E(res)}</div>` : ""}
      <pre class="ev-log">${E(j.log.join("\n"))}</pre>`;
    const lg = el.querySelector(".ev-log"); lg.scrollTop = lg.scrollHeight;
  }

  // ------------------------------------------------------------------ the examiner's own task
  const TYPES = [["short_text", "Short text"], ["long_text", "Long text"], ["number", "Number"], ["email", "Email"], ["phone", "Phone"], ["date", "Date"],
                 ["radio", "One choice"], ["checkbox", "Several choices"], ["file", "File upload"], ["rating", "Rating 1–5"]];
  function exam() {
    $("evExam").innerHTML = `<div class="panel-head"><div><h2>Test it yourself</h2><p class="sub">Type any request and say what a correct app must have.
        The real agents build it, and the same exact checks as the evaluation mark it — plus six automatic checks every build gets.</p></div></div>
      <div class="ev-ex">
        <div class="ev-ex-l">
          <label class="label" for="exReq">The request</label>
          <textarea id="exReq" rows="3" placeholder="e.g. A sign-up for the robotics workshop for section 34ML, 20 places, closes 12 December 2026, ask which session: morning or afternoon."></textarea>
          <div class="ev-f2"><label><span class="label">Workspace</span><select id="exWs"><option value="university">University (Riverside)</option><option value="office">Office (Northwind)</option><option value="general">Personal</option></select></label>
            <label><span class="label">Title mentions</span><input id="exTitle" placeholder="optional word"></label></div>
          <span class="label">It must ask</span><div class="ev-chips" id="exTypes">${TYPES.map(([t, l]) => `<button type="button" data-t="${t}">${l}</button>`).join("")}</div>
          <div class="ev-f2"><label><span class="label">File types</span><input id="exAccept" placeholder=".pdf, .docx"></label><label><span class="label">Max file MB</span><input id="exMb" type="number" min="1" max="25"></label></div>
          <div class="ev-f2"><label><span class="label">Choice options</span><input id="exChoice" placeholder="morning, afternoon"></label><label><span class="label">Places per option</span><input id="exEach" type="number" min="1"></label></div>
        </div>
        <div class="ev-ex-r">
          <div class="ev-f2"><label><span class="label">Deadline</span><input id="exDate" type="date"></label><label><span class="label">at (optional)</span><input id="exTime" type="time"></label></div>
          <div class="ev-f2"><label><span class="label">Total places</span><input id="exTotal" type="number" min="1"></label>
            <label><span class="label">Responses per person</span><select id="exPer"><option value="">don't check</option><option value="one">one</option><option value="many">many</option></select></label></div>
          <div class="ev-f2"><label><span class="label">Anonymous</span><select id="exAnon"><option value="">don't check</option><option value="1">yes</option><option value="0">no</option></select></label>
            <label><span class="label">Statuses</span><input id="exStat" placeholder="pending, approved"></label></div>
          <div class="ev-f2"><label><span class="label">Shared with</span><select id="exAud"><option value="">don't check</option><option value="group">a group</option><option value="org">everyone in the organisation</option><option value="public">anyone with the link</option></select></label>
            <label><span class="label">Group name / role</span><span class="ev-pair"><input id="exGroup" placeholder="34ML"><select id="exRole"><option value="submitter">fills it in</option><option value="viewer">viewer</option><option value="editor">editor</option></select></span></label></div>
          <label class="ev-check"><input type="checkbox" id="exNoId" checked> Don't ask signed-in people for their name or email</label>
          <div class="ev-preview" id="exPrev"></div>
          <div class="ev-ex-go"><button class="btn primary" id="exGo">Build it with the real agents · ≈ $0.05</button><span class="sub" id="exHint"></span></div>
        </div>
      </div>
      <div id="exResult"></div>`;
    $("exTypes").querySelectorAll("button").forEach(b => b.onclick = () => { b.classList.toggle("on"); preview(); });
    $("evExam").querySelectorAll("input, select, textarea").forEach(i => i.addEventListener("input", preview));
    $("exGo").onclick = go;
    preview();
  }
  const list = v => v.split(",").map(x => x.trim()).filter(Boolean);
  function expect() {
    const e = {}, v = id => $(id).value.trim();
    const types = [...$("exTypes").querySelectorAll(".on")].map(b => b.dataset.t);
    if (types.length) e.fields = types;
    if (v("exAccept")) e.file_accept = list(v("exAccept")).map(x => x.startsWith(".") ? x : "." + x);
    if (v("exMb")) e.file_max_mb = +v("exMb");
    if (v("exChoice")) e.choice = list(v("exChoice"));
    if (v("exEach")) e.places_each = +v("exEach");
    if (v("exDate")) e.deadline = v("exDate") + (v("exTime") ? "T" + v("exTime") : "");
    if (v("exTotal")) e.total_places = +v("exTotal");
    if (v("exPer")) e.per_person = v("exPer");
    if (v("exAnon")) e.anonymous = v("exAnon") === "1";
    if (v("exStat")) e.statuses = list(v("exStat"));
    if (v("exAud") === "group" && v("exGroup")) e.audience = { type: "group", name: v("exGroup"), role: v("exRole") };
    else if (v("exAud") === "org" || v("exAud") === "public") e.audience = { type: v("exAud") };
    if ($("exNoId").checked) e.no_identity = true;
    if (v("exTitle")) e.title_has = v("exTitle");
    return e;
  }
  function preview() {
    const e = expect(), out = [];
    (e.fields || []).forEach(t => out.push(`asks a ${TYPES.find(x => x[0] === t)[1].toLowerCase()} question${t === "file" && (e.file_accept || e.file_max_mb) ? ` (${[(e.file_accept || []).join(", "), e.file_max_mb ? e.file_max_mb + " MB" : ""].filter(Boolean).join(", ")})` : ""}`));
    if (e.choice) out.push(`a choice of ${e.choice.join(" / ")}${e.places_each ? `, ${e.places_each} places each` : ""}`);
    if (e.deadline) out.push(`closes ${e.deadline.replace("T", " ")}`);
    if (e.total_places) out.push(`${e.total_places} places in total`);
    if (e.per_person) out.push(`${e.per_person} response per person`);
    if (e.anonymous !== undefined) out.push(e.anonymous ? "anonymous" : "not anonymous");
    if (e.statuses) out.push(`statuses ${e.statuses.join(" → ")}`);
    if (e.audience) out.push(e.audience.type === "group" ? `shared with ${e.audience.name} (${e.audience.role})` : e.audience.type === "org" ? "shared with everyone" : "anyone with the link");
    if (e.no_identity) out.push("doesn't ask signed-in people for name/email");
    if (e.title_has) out.push(`title mentions “${e.title_has}”`);
    $("exPrev").innerHTML = `<span class="label">Your checks (${out.length}) + 6 automatic</span><ul>${out.map(x => `<li>${E(x)}</li>`).join("") || "<li class='sub'>Add at least one expectation.</li>"}</ul>
      <small class="sub">Automatic: readable colour · title and instructions · app saved · reply doesn't claim it was shared · reply's dates true · reply's places true</small>`;
    $("exGo").disabled = !$("exReq").value.trim() || !out.length;
  }
  function go() {
    if (!armed) {                                    // two taps: the second one spends money
      armed = true; $("exGo").textContent = "Tap again to spend ≈ $0.05"; $("exGo").classList.add("danger");
      clearTimeout(armTimer); armTimer = setTimeout(() => { armed = false; $("exGo").textContent = "Build it with the real agents · ≈ $0.05"; $("exGo").classList.remove("danger"); }, 5000);
      return;
    }
    armed = false; clearTimeout(armTimer);
    $("exGo").textContent = "Build it with the real agents · ≈ $0.05"; $("exGo").classList.remove("danger");
    $("exResult").innerHTML = `<p class="sub">Building… the agents are working (about 20 seconds). Watch the Agent theater or Flow tab to see them.</p>`;
    start({ kind: "examiner", job: { request: $("exReq").value.trim(), workspace: $("exWs").value, expect: expect() }, confirm_cost: true });
  }
  function examResult(r, where = $("exResult")) {
    if (!r) { where.innerHTML = `<p class="ev-warn">The task didn't finish — see the log above.</p>`; return; }
    const mine = r.checks.slice(0, r.examiner_checks), auto = r.checks.slice(r.examiner_checks);
    const li = c => `<li class="${c.passed ? "ok" : "bad"}"><b>${c.passed ? "✓" : "✗"}</b><span>${E(c.agent)}: ${E(c.check)}${c.detail ? `<small>${E(c.detail)}</small>` : ""}</span></li>`;
    where.innerHTML = `<div class="ev-exres ${r.success ? "ok" : "bad"}"><div class="ev-big">${r.success ? "PASS" : "FAIL"}<small>${r.checks.filter(c => c.passed).length} of ${r.checks.length} checks · ${(r.wall_ms / 1000).toFixed(1)} s · ${usd(r.cost_usd)} · ${E((r.agents || []).join(", "))}</small></div>
      <div class="ev-f2"><div><h4>Your checks</h4><ul class="ev-checks">${mine.map(li).join("")}</ul><h4>Automatic checks</h4><ul class="ev-checks">${auto.map(li).join("")}</ul></div>
        <div><h4>What was built</h4><p><b>${E(r.app?.title || "—")}</b> · ${E(r.app?.kind || "")}${r.app?.closes_at ? ` · closes ${E(r.app.closes_at.replace("T", " "))}` : ""}</p>
          <ul class="ev-checks">${(r.app?.fields || []).map(f => `<li><b>·</b><span>${E(f)}</span></li>`).join("")}</ul>
          <p class="sub">Shared with: ${E((r.app?.share || []).join(", ") || "—")}</p>
          <h4>The reply</h4><p class="ev-quote">${E(r.reply || r.error || "—")}</p>
          ${r.folder ? `<p class="sub">Recorded in <code>${E(r.folder)}</code> — it can be re-scored for free.</p><button class="btn sm" data-replay="${E(r.folder)}">Re-score from the recording</button>` : ""}</div></div></div>`;
    where.querySelector("[data-replay]")?.addEventListener("click", e => start({ kind: "examiner-replay", folder: e.target.dataset.replay }));
  }

  // ------------------------------------------------------------------ history
  function hist() {
    $("evHist").innerHTML = `<div class="panel-head"><div><h2>Every evaluation run</h2><p class="sub">Kept, not overwritten — nothing is cherry-picked. Newest first.</p></div></div>
      <div class="ev-tbl-wrap"><table class="ev-tbl"><thead><tr><th>When</th><th>Kind</th><th>How</th><th>Result</th><th>Folder</th></tr></thead><tbody>
      ${S.history.map(h => `<tr ${/examiner/.test(h.kind) ? `class="click" data-folder="${E(h.folder)}"` : ""}><td class="nowrap">${E(h.when)}</td><td>${E(h.kind)}</td><td>${badge(h.label)}</td><td>${E(h.head)}</td><td class="ev-mono">${E(h.folder)}</td></tr>`).join("")}
      </tbody></table></div>`;
    $("evHist").querySelectorAll("[data-folder]").forEach(tr => tr.onclick = async () => {
      const R = await CC.api(`/api/eval/folder?folder=${encodeURIComponent(tr.dataset.folder)}`);
      drawer(`<h3>Examiner task</h3><p class="ev-quote">${E(R.result.request)}</p><div id="evExD"></div>`);
      examResult({ ...R.result, folder: tr.dataset.folder.endsWith("-replay") ? null : tr.dataset.folder }, $("evExD"));
    });
  }

  CC.on("init", skeleton);
  CC.on("mode", m => { if (m === "evaluation") load(); });
  return { load };
})();
