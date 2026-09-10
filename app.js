"use strict";

/* ================================================================
   Demonstration Coverage & Extrapolation — App Logic
   ================================================================ */

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

/* ================================================================
   TASK DEFINITIONS
   ================================================================ */

const TASKS = [
  {
    id: "parity-shift",
    name: "Even / Odd Rule",
    rule: (n) => (n % 2 === 0 ? n + 2 : n * 3),
    categories: [
      { id: "even", label: "Even numbers", test: (n) => n % 2 === 0, transform: "n + 2" },
      { id: "odd",  label: "Odd numbers",  test: (n) => n % 2 !== 0, transform: "n × 3" },
    ],
    demos: [
      { input: 2,  output: 4,  cat: "even", critical: false },
      { input: 4,  output: 6,  cat: "even", critical: false },
      { input: 1,  output: 3,  cat: "odd",  critical: true },
      { input: 3,  output: 9,  cat: "odd",  critical: false },
    ],
    testInputs: [3, 6, 5, 8, 1, 10, 7, 4],
    defaultTestInput: 3,
    guidedStart: [0, 2],
    guidedCritical: 2,
    candidateRules: [
      { name: "Rule A: add 2 to everything", desc: "Apply n + 2 to every input",  trueRule: false, predict: (n) => n + 2 },
      { name: "Rule B: triple everything",   desc: "Apply n × 3 to every input",  trueRule: false, predict: (n) => n * 3 },
      { name: "Rule C: even +2, odd ×3",     desc: "The parity-dependent rule",   trueRule: true,  predict: (n) => (n % 2 === 0 ? n + 2 : n * 3) },
    ],
  },
  {
    id: "size-rule",
    name: "Small / Large Rule",
    rule: (n) => (n <= 5 ? n * 2 : n - 1),
    categories: [
      { id: "small", label: "Small (≤5)", test: (n) => n <= 5, transform: "n × 2" },
      { id: "large", label: "Large (>5)", test: (n) => n > 5,  transform: "n − 1" },
    ],
    demos: [
      { input: 2,  output: 4,  cat: "small", critical: false },
      { input: 4,  output: 8,  cat: "small", critical: false },
      { input: 6,  output: 5,  cat: "large", critical: true },
      { input: 8,  output: 7,  cat: "large", critical: false },
    ],
    testInputs: [6, 9, 3, 7, 2, 10, 4, 5],
    defaultTestInput: 6,
    guidedStart: [0, 2],
    guidedCritical: 2,
    candidateRules: [
      { name: "Rule A: double everything", desc: "Apply n × 2 to every input", trueRule: false, predict: (n) => n * 2 },
      { name: "Rule B: subtract 1",        desc: "Apply n − 1 to every input", trueRule: false, predict: (n) => n - 1 },
      { name: "Rule C: small ×2, large −1", desc: "The size-dependent rule",  trueRule: true,  predict: (n) => (n <= 5 ? n * 2 : n - 1) },
    ],
  },
  {
    id: "low-high",
    name: "Low / High Rule",
    rule: (n) => (n <= 4 ? n + 10 : n - 2),
    categories: [
      { id: "low",  label: "Low (≤4)", test: (n) => n <= 4, transform: "n + 10" },
      { id: "high", label: "High (>4)", test: (n) => n > 4,  transform: "n − 2" },
    ],
    demos: [
      { input: 2,  output: 12, cat: "low",  critical: false },
      { input: 4,  output: 14, cat: "low",  critical: false },
      { input: 6,  output: 4,  cat: "high", critical: true },
      { input: 8,  output: 6,  cat: "high", critical: false },
    ],
    testInputs: [6, 8, 3, 9, 2, 7, 4, 10],
    defaultTestInput: 6,
    guidedStart: [0, 2],
    guidedCritical: 2,
    candidateRules: [
      { name: "Rule A: add 10",      desc: "Apply n + 10 to every input", trueRule: false, predict: (n) => n + 10 },
      { name: "Rule B: subtract 2",  desc: "Apply n − 2 to every input",  trueRule: false, predict: (n) => n - 2 },
      { name: "Rule C: low +10, high −2", desc: "The magnitude rule",     trueRule: true,  predict: (n) => (n <= 4 ? n + 10 : n - 2) },
    ],
  },
];

/* ================================================================
   STATE
   ================================================================ */

const state = {
  currentTaskId: "parity-shift",
  selectedDemos: new Set(),
  testInput: 3,
  learnerState: null,
  learnerSteps: null,
  step: 1,
  guidedPhase: "run",
  isFreeExplore: false,
  learnerRan: false,
};

function currentTask() {
  return TASKS.find((t) => t.id === state.currentTaskId);
}

/* ================================================================
   TOY RECURRENT LEARNER
   ================================================================ */

function runLearner(task, demoIndices) {
  const demos = demoIndices
    .map((i) => task.demos[i])
    .filter(Boolean)
    .sort((a, b) => a.input - b.input);

  const mem = { covered: {}, order: [] };
  const steps = [];
  steps.push({ type: "init", label: "Initialize empty memory", state: snapshot(mem) });

  const seenDemoRefs = [];
  for (const demo of demos) {
    const cat = task.categories.find((c) => c.test(demo.input));
    if (!cat) continue;
    if (!mem.covered[cat.id]) {
      mem.covered[cat.id] = { label: cat.label, transform: cat.transform, examples: [] };
      mem.order.push(cat.id);
    }
    mem.covered[cat.id].examples.push({ input: demo.input, output: demo.output });
    seenDemoRefs.push({ input: demo.input, output: demo.output });
    steps.push({
      type: "update", label: `Process ${demo.input} → ${demo.output}`,
      demo, category: cat, state: snapshot(mem),
    });
  }

  const fittingRules = task.candidateRules.filter((cr) =>
    seenDemoRefs.every((d) => cr.predict(d.input) === d.output)
  ).map((r) => r.name);
  mem.fittingRules = fittingRules;
  mem.demosSeen = seenDemoRefs;

  steps.push({ type: "ready", label: "Memory updated — ready to predict", state: snapshot(mem) });
  return { mem, steps };
}

function snapshot(mem) {
  const c = {};
  for (const id of mem.order) c[id] = { ...mem.covered[id] };
  return { covered: c, order: [...mem.order], fittingRules: mem.fittingRules || [] };
}

function predict(mem, task, input) {
  if (!mem) return null;
  const cat = task.categories.find((c) => c.test(input));

  // Directly covered category → use the true rule for that category.
  if (cat && mem.covered[cat.id]) {
    return task.rule(input);
  }

  // Uncovered category → over-extrapolate a global rule consistent with demos.
  if (!mem.fittingRules || mem.fittingRules.length === 0) return null;
  const fitting = task.candidateRules.filter((r) => mem.fittingRules.includes(r.name));
  if (fitting.length === 0) return null;
  const globals = fitting.filter((r) => !r.trueRule);
  if (globals.length > 0) return globals[0].predict(input);
  return fitting[0].predict(input);
}

/* ================================================================
   COVERAGE COMPUTATION
   ================================================================ */

function computeCoverage(task, demoIndices) {
  const demos = demoIndices.map((i) => task.demos[i]).filter(Boolean);
  const coveredCats = new Set();
  for (const demo of demos) {
    const cat = task.categories.find((c) => c.test(demo.input));
    if (cat) coveredCats.add(cat.id);
  }
  const total = task.categories.length;
  const covered = coveredCats.size;
  const pct = total > 0 ? Math.round((covered / total) * 100) : 0;
  const dims = task.categories.map((cat) => ({
    ...cat,
    covered: coveredCats.has(cat.id),
    demoCount: demos.filter((d) => cat.test(d.input)).length,
  }));
  return { pct, covered, total, dims, coveredCats };
}

/* ================================================================
   COMPETING RULES
   ================================================================ */

function analyzeCompetingRules(task, demoIndices, testInput) {
  const demos = demoIndices.map((i) => task.demos[i]).filter(Boolean);
  const gt = task.rule(testInput);
  const results = [];
  for (const cr of task.candidateRules) {
    let fitsAll = true;
    const mismatches = [];
    for (const demo of demos) {
      if (cr.predict(demo.input) !== demo.output) { fitsAll = false; mismatches.push(demo); }
    }
    const prediction = cr.predict(testInput);
    const correct = prediction === gt;
    results.push({ rule: cr, fitsAll, mismatches, prediction, correct, gt });
  }
  return results;
}

/* ================================================================
   RENDERING
   ================================================================ */

function renderTaskTabs() {
  const el = $("#task-tabs");
  el.innerHTML = TASKS.map(
    (t) => `<button class="task-tab ${t.id === state.currentTaskId ? "active" : ""}" data-task="${t.id}">${t.name}</button>`
  ).join("");
  el.querySelectorAll(".task-tab").forEach((btn) => {
    btn.addEventListener("click", () => { state.currentTaskId = btn.dataset.task; resetToGuided(); });
  });
}

function renderDemos() {
  const task = currentTask();
  const grid = $("#demo-grid");
  grid.innerHTML = task.demos.map((d, i) =>
    `<div class="demo-card ${state.selectedDemos.has(i) ? "selected" : ""} ${d.critical ? "critical" : ""}" data-idx="${i}">
      <div class="demo-check">&#10003;</div>
      <div class="demo-io">${d.input} → ${d.output}</div>
      <div class="demo-category">${task.categories.find((c) => c.id === d.cat)?.label || d.cat}</div>
      ${d.critical ? '<div class="demo-critical-tag">Strategically important</div>' : ""}
    </div>`
  ).join("");
  grid.querySelectorAll(".demo-card").forEach((card) => {
    card.addEventListener("click", () => {
      const idx = parseInt(card.dataset.idx);
      if (state.selectedDemos.has(idx)) state.selectedDemos.delete(idx);
      else state.selectedDemos.add(idx);
      afterDemosChange();
    });
  });
}

function afterDemosChange() {
  renderDemos();
  renderCoverage();
  resetLearner();
  resetTest();
  detectGuidedProgress();
  updateGuidedPrompt();
}

function renderCoverage() {
  const task = currentTask();
  const indices = [...state.selectedDemos];
  const cov = computeCoverage(task, indices);
  const fill = $("#coverage-fill");
  const pct = $("#coverage-pct");
  fill.style.width = cov.pct + "%";
  pct.textContent = cov.pct + "%";
  if (cov.pct >= 100) { fill.style.background = "linear-gradient(90deg, var(--green), #22c55e)"; pct.style.color = "var(--green)"; }
  else if (cov.pct >= 50) { fill.style.background = "linear-gradient(90deg, var(--blue), var(--orange))"; pct.style.color = "var(--orange)"; }
  else { fill.style.background = "linear-gradient(90deg, var(--red), var(--orange))"; pct.style.color = "var(--red)"; }
  const grid = $("#coverage-grid");
  grid.innerHTML = cov.dims.map((d) =>
    `<div class="coverage-chip ${d.covered ? "covered" : "uncovered"}">
      <div class="chip-dot"></div>
      <div>
        <div class="chip-label">${d.label}</div>
        <div class="chip-detail">${d.transform} — ${d.covered ? d.demoCount + " demo(s)" : "No demos"}</div>
      </div>
    </div>`
  ).join("");
}

/* ---- Learner panel ---------------------------------------------- */

function renderLearnerFlow(mem, steps) {
  const flow = $("#learner-flow");
  if (!steps) { flow.innerHTML = '<p class="muted">Select demonstrations, then run the learner.</p>'; return; }
  flow.innerHTML = steps.map((s, i) =>
    `<div class="flow-step" data-step-idx="${i}">
      <div class="flow-arrow">${s.type === "init" ? "○" : s.type === "ready" ? "✓" : "→"}</div>
      <div class="flow-label">${s.label}</div>
      <div class="flow-state">${s.demo ? `${s.demo.input}→${s.demo.output}` : ""}</div>
    </div>`
  ).join("");
}

function resetLearner() {
  state.learnerState = null;
  state.learnerSteps = null;
  state.learnerRan = false;
  $("#learner-flow").innerHTML = '<p class="muted">Select demonstrations, then run the learner.</p>';
  $("#learner-state-content").innerHTML = '<p class="muted">Run the learner to see its memory state.</p>';
  $("#btn-run-learner").disabled = false;
}

function animateLearner() {
  if (state.selectedDemos.size === 0) return;
  const task = currentTask();
  const indices = [...state.selectedDemos].sort((a, b) => task.demos[a].input - task.demos[b].input);
  const { mem, steps } = runLearner(task, indices);
  state.learnerSteps = steps;
  state.learnerState = mem;
  state.learnerRan = true;
  $("#btn-run-learner").disabled = true;

  renderLearnerFlow(mem, steps);
  const flowEl = $("#learner-flow");
  const flowSteps = flowEl.querySelectorAll(".flow-step");
  let i = 0;
  function animateStep() {
    if (i > 0 && i < flowSteps.length) { flowSteps[i - 1].classList.remove("active"); flowSteps[i - 1].classList.add("done"); }
    if (i < flowSteps.length) {
      flowSteps[i].classList.add("active");
      flowSteps[i].scrollIntoView({ behavior: "smooth", block: "nearest" });
      i++;
      setTimeout(animateStep, 380);
    } else {
      renderLearnerState(mem);
      $("#btn-run-learner").disabled = false;
      runTest();
      updateGuidedPrompt();
    }
  }
  animateStep();
}

function renderLearnerState(mem) {
  const task = currentTask();
  const el = $("#learner-state-content");
  if (!mem || mem.order.length === 0) {
    el.innerHTML = '<p class="muted">Empty memory — no demonstrations processed.</p>';
    return;
  }
  let html = '<table class="state-table"><thead><tr><th>Category</th><th>Learned Rule</th><th>Examples Seen</th><th>Status</th></tr></thead><tbody>';
  for (const cat of task.categories) {
    const entry = mem.covered[cat.id];
    if (entry) {
      const exList = entry.examples.map((e) => `${e.input}→${e.output}`).join(", ");
      html += `<tr><td>${cat.label}</td><td>${cat.transform}</td><td>${exList}</td><td class="cat-known">Known</td></tr>`;
    } else {
      html += `<tr><td>${cat.label}</td><td>—</td><td>—</td><td class="cat-unknown">Unknown</td></tr>`;
    }
  }
  html += "</tbody></table>";
  const fit = mem.fittingRules && mem.fittingRules.length ? mem.fittingRules.join(", ") : "none";
  html += `<p style="margin-top:10px;font-size:13px;color:var(--ink-faint)">Rules consistent with all seen demos: <strong>${fit}</strong></p>`;
  html += '<p style="margin-top:4px;font-size:13px;color:var(--ink-faint)">Categories without demos are <strong style="color:var(--red)">unknown</strong> — the learner has no direct evidence and can only extrapolate from what it saw.</p>';
  el.innerHTML = html;
}

/* ---- Test panel ------------------------------------------------- */

function renderTestInputs() {
  const task = currentTask();
  const grp = $("#test-input-group");
  grp.innerHTML = task.testInputs.map((n) =>
    `<button class="test-input-btn ${n === state.testInput ? "active" : ""}" data-val="${n}">${n}</button>`
  ).join("");
  grp.querySelectorAll(".test-input-btn").forEach((btn) => {
    btn.addEventListener("click", () => { state.testInput = parseInt(btn.dataset.value); renderTestInputs(); runTest(); });
  });
}

function resetTest() {
  $("#test-input-val").textContent = "—";
  $("#test-pred-val").textContent = "—";
  $("#test-gt-val").textContent = "—";
  const v = $("#test-verdict"); v.textContent = "—"; v.className = "test-verdict";
  const exp = $("#test-explanation"); exp.className = "explanation-box"; exp.innerHTML = "";
  renderCompetingRules(null);
}

function runTest() {
  if (state.selectedDemos.size === 0 || !state.learnerRan) return;
  const task = currentTask();
  const testInput = state.testInput;
  const gt = task.rule(testInput);
  const pred = predict(state.learnerState, task, testInput);

  $("#test-input-val").textContent = testInput;
  $("#test-gt-val").textContent = gt;
  const v = $("#test-verdict");
  const exp = $("#test-explanation");

  if (pred === null) {
    $("#test-pred-val").textContent = "?";
    v.textContent = "No rule?"; v.className = "test-verdict unknown";
    exp.className = "explanation-box show info";
    exp.innerHTML = "No candidate rule in memory is consistent with all selected demonstrations. Add more demonstrations or reset.";
  } else if (pred === gt) {
    $("#test-pred-val").textContent = pred;
    v.textContent = "Correct"; v.className = "test-verdict correct";
    exp.className = "explanation-box show success";
    exp.innerHTML = "<strong>The prediction is correct.</strong> The demonstrations covered the rule condition that input " + testInput + " falls into, so the learner identified the intended rule and extrapolated correctly.";
  } else {
    $("#test-pred-val").textContent = pred;
    v.textContent = "Incorrect"; v.className = "test-verdict incorrect";
    exp.className = "explanation-box show failure";
    exp.innerHTML = "<strong>The prediction is wrong.</strong> The learner extrapolated <strong>" + pred + "</strong>, but the correct answer is <strong>" + gt + "</strong>. This happened because the demonstrations did not cover the rule condition for input " + testInput + " — the learner inferred a rule that fits what it saw but does not hold here.";
  }

  const analysis = analyzeCompetingRules(task, [...state.selectedDemos], testInput);
  renderCompetingRules(analysis);
}

function renderCompetingRules(analysis) {
  const tbody = $("#competing-tbody");
  const explanation = $("#competing-explanation");
  if (!analysis || analysis.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--ink-faint);padding:20px">Run the learner to see the competing-rules analysis.</td></tr>';
    explanation.innerHTML = "";
    return;
  }
  tbody.innerHTML = analysis.map((a) => {
    const statusCls = !a.fitsAll ? "rejected" : a.correct ? "consistent" : "ambiguous";
    const statusLabel = !a.fitsAll ? "Rejected" : a.correct ? "Consistent" : "Ambiguous";
    return `<tr class="rule-${statusCls}">
      <td><strong>${a.rule.name}</strong><br/><span style="font-size:12px;color:var(--ink-faint)">${a.rule.desc}</span></td>
      <td>${a.fitsAll ? '<span style="color:var(--green);font-weight:600">Yes</span>' : '<span style="color:var(--red);font-weight:600">No</span> (' + a.mismatches.length + " mismatch)"}</td>
      <td style="font-family:var(--mono);font-weight:700">${a.prediction} <span style="color:var(--ink-faint);font-weight:400">(truth: ${a.gt})</span></td>
      <td><span class="rule-status ${statusCls}">${statusLabel}</span></td>
    </tr>`;
  }).join("");
  const consistent = analysis.filter((a) => a.fitsAll && a.correct);
  const ambiguous = analysis.filter((a) => a.fitsAll && !a.correct);
  const rejected = analysis.filter((a) => !a.fitsAll);
  if (ambiguous.length > 0) {
    explanation.innerHTML = '<strong style="color:var(--orange)">Ambiguity detected.</strong> ' +
      (rejected.length > 0 ? rejected.length + " rule(s) were <strong>rejected</strong> because they don't match all demonstrations. " : "") +
      "<strong>" + consistent.length + " rule(s) fit all demonstrations, but " + ambiguous.length +
      " give(s) a wrong prediction</strong> for input " + state.testInput +
      ". The unseen test case exposes the ambiguity the demonstrations left unresolved — the learner cannot tell which rule is intended. <em>This is demonstration coverage failure: recurrent memory preserves evidence, but it cannot invent evidence that was never demonstrated.</em>";
  } else if (consistent.length > 0 && ambiguous.length === 0) {
    explanation.innerHTML = '<strong style="color:var(--green)">No ambiguity.</strong> ' +
      (rejected.length > 0 ? rejected.length + " rule(s) rejected. " : "") +
      consistent.length + " rule(s) fit all demonstrations and predict correctly. " +
      "The demonstrations provide enough coverage to pin down the intended rule.";
  } else {
    explanation.innerHTML = "All candidate rules are consistent with the current demonstrations, but coverage is too limited to distinguish between them.";
  }
}

/* ---- Step indicators --------------------------------------------- */

function updateStepBar() {
  const currentIdx = state.isFreeExplore ? 4 : Math.max(0, Math.min(4, phaseToIndex()));
  $$(".step-pill").forEach((pill) => {
    const s = parseInt(pill.dataset.step);
    pill.classList.remove("active", "done");
    if (s - 1 < currentIdx) pill.classList.add("done");
    if (s - 1 === currentIdx) pill.classList.add("active");
  });
}

function phaseToIndex() {
  switch (state.guidedPhase) {
    case "run": return 0;
    case "observe": return 1;
    case "reduce":
    case "remove": return 2;
    case "restore": return 3;
    case "done": return 4;
    default: return 0;
  }
}

/* ---- Guided prompts ---------------------------------------------- */

function updateGuidedPrompt() {
  if (state.isFreeExplore) { $("#guided-prompt").classList.add("hidden"); return; }
  const prompt = $("#guided-prompt");
  const inner = $("#guided-prompt-inner");

  let text = "";
  switch (state.guidedPhase) {
    case "run":
      text = "Here is the <strong>baseline demonstration set</strong>, with one example for each rule category (100% coverage). Click <strong>Run Learner on Demos</strong> to process them sequentially and build the memory state.";
      break;
    case "observe":
      text = "<strong>Baseline result:</strong> The learner's memory covered every category, and the unseen test input " + state.testInput + " was predicted <strong>correctly</strong>.<br/><br/>Now <strong>remove the demonstration " + demoLabel(currentTask().guidedCritical) + "</strong> (click that demo card to deselect it), then re-run the learner.";
      break;
    case "reduce":
      text = "You removed the demonstration <strong>" + demoLabel(currentTask().guidedCritical) + "</strong>. Look at the coverage bar — that category is now uncovered. Re-run the learner to see what happens.";
      break;
    case "remove":
      text = "<strong>Watch the failure:</strong> that demo was the only evidence for the " + currentTask().categories.find(c=>c.id===currentTask().demos[currentTask().guidedCritical].cat).label + " rule. Without it, the learner over-extrapolates a rule that fits what it saw but is wrong here. The competing-rules table below shows which rules still fit. <strong>Re-run the learner</strong> to confirm.";
      break;
    case "restore":
      text = "<strong>Now click the demonstration " + demoLabel(currentTask().guidedCritical) + " again to add it back</strong>, then re-run the learner. The prediction recovers and the competing rules are resolved — this is the causal chain: <em>missing coverage → ambiguity → systematic failure</em>.";
      break;
    default:
      prompt.classList.add("hidden");
      return;
  }

  prompt.classList.remove("hidden");
  inner.innerHTML = `<div class="guided-prompt-text">${text}</div>
    <button class="btn btn-primary btn-sm" id="btn-guided-next">Works&nbsp;&raquo;</button>`;
  $("#btn-guided-next").addEventListener("click", advanceGuided);
}

function demoLabel(idx) {
  const d = currentTask().demos[idx];
  return d ? `${d.input} → ${d.output}` : "";
}

function advanceGuided() {
  if (state.guidedPhase === "run") { state.guidedPhase = "observe"; }
  else if (state.guidedPhase === "observe") {
    state.guidedPhase = "remove";
    if (!state.selectedDemos.has(currentTask().guidedCritical)) {
      state.guidedPhase = "reduce";
    }
  }
  else if (state.guidedPhase === "reduce") { state.guidedPhase = "remove"; }
  else if (state.guidedPhase === "remove") { state.guidedPhase = "restore"; }
  else if (state.guidedPhase === "restore") { enterFreeExplore(); }
  updateStepBar();
  updateGuidedPrompt();
}

function detectGuidedProgress() {
  if (state.isFreeExplore) return;
  const task = currentTask();
  const critical = task.guidedCritical;
  const hasCritical = state.selectedDemos.has(critical);
  if (state.guidedPhase === "run" || state.guidedPhase === "observe") {
    if (!hasCritical && state.selectedDemos.size > 0) {
      state.guidedPhase = "reduce";
    }
  } else if ((state.guidedPhase === "remove" || state.guidedPhase === "reduce") && !hasCritical) {
    state.guidedPhase = "remove";
  } else if (state.guidedPhase === "remove" && hasCritical) {
    state.guidedPhase = "restore";
  }
  updateStepBar();
}

function enterFreeExplore() {
  state.isFreeExplore = true;
  state.guidedPhase = "done";
  ["#panel-free", "#section-bdhcq", "#section-takeaways", "#section-limitations", "#section-references", "#section-credits"].forEach(
    (sel) => $(sel)?.classList.remove("hidden")
  );
  $("#guided-prompt").classList.add("hidden");
  updateStepBar();
}

/* ---- Reset ------------------------------------------------------- */

function resetToGuided() {
  const task = currentTask();
  state.selectedDemos = new Set(task.guidedStart);
  state.testInput = task.defaultTestInput;
  state.learnerState = null;
  state.learnerSteps = null;
  state.learnerRan = false;
  state.guidedPhase = "run";
  state.isFreeExplore = false;
  state.step = 1;
  ["#panel-free", "#section-bdhcq", "#section-takeaways", "#section-limitations", "#section-references", "#section-credits"].forEach(
    (sel) => $(sel)?.classList.add("hidden")
  );
  renderTaskTabs();
  renderDemos();
  renderCoverage();
  renderLearnerFlow(null, null);
  resetTest();
  renderTestInputs();
  updateStepBar();
  updateGuidedPrompt();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetExperiment() {
  state.selectedDemos = new Set();
  state.testInput = currentTask().defaultTestInput;
  state.learnerState = null;
  state.learnerSteps = null;
  state.learnerRan = false;
  state.guidedPhase = "done";
  state.isFreeExplore = true;
  ["#panel-free", "#section-bdhcq", "#section-takeaways", "#section-limitations", "#section-references", "#section-credits"].forEach(
    (sel) => $(sel)?.classList.remove("hidden")
  );
  $("#guided-prompt").classList.add("hidden");
  renderTaskTabs();
  renderDemos();
  renderCoverage();
  resetLearner();
  resetTest();
  renderTestInputs();
  updateStepBar();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ================================================================
   INIT
   ================================================================ */

function init() {
  $("#btn-start").addEventListener("click", () => {
    $("#intro").classList.add("hidden");
    $("#experiment").classList.remove("hidden");
    resetToGuided();
  });
  $("#btn-run-learner").addEventListener("click", () => {
    if (state.selectedDemos.size === 0) return;
    animateLearner();
  });
  $("#btn-select-all").addEventListener("click", () => {
    const task = currentTask();
    task.demos.forEach((_, i) => state.selectedDemos.add(i));
    afterDemosChange();
  });
  $("#btn-deselect-all").addEventListener("click", () => {
    state.selectedDemos.clear();
    afterDemosChange();
  });
  $("#btn-reset-guided").addEventListener("click", resetToGuided);
  $("#btn-explore-reset").addEventListener("click", resetExperiment);
  $("#btn-explore-guided").addEventListener("click", resetToGuided);
}

document.addEventListener("DOMContentLoaded", init);
