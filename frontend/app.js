/* ======================================================================
   VeRoof — Claims Evidence, Reviewed.
   Frontend logic: view routing, sample loading, review submission,
   progress polling, and report rendering.
   ====================================================================== */

"use strict";

const API = "/api";

/* ---------- Tiny helpers ------------------------------------------------- */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const esc = (s) =>
  String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

function showView(name) {
  const id = name.indexOf("view-") === 0 ? name : "view-" + name;
  $$(".view").forEach((v) => v.classList.remove("active"));
  const target = $("#" + id);
  if (target) target.classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------- App state ---------------------------------------------------- */

const state = {
  claimType: "accident",
  samples: [],
  reviewsCache: new Map(), // job_id -> report
  polling: null,
  recentFilters: { disposition: "", type: "" },
};

/* ---------- Disposition metadata ---------------------------------------- */

const DISPOSITIONS = {
  approve: {
    label: "Approve",
    cls: "disp-approved",
    icon: "&#10003;",
    blurb: "The claim is complete, consistent and eligible under the policy.",
  },
  reject: {
    label: "Reject",
    cls: "disp-reject",
    icon: "&#10007;",
    blurb: "The claim is not eligible — one or more findings block it.",
  },
  request_info: {
    label: "Request information",
    cls: "disp-request_info",
    icon: "&#9998;",
    blurb: "Specific items are missing or outstanding before a decision.",
  },
  escalate: {
    label: "Escalate to investigator",
    cls: "disp-escalate",
    icon: "&#11021;",
    blurb: "An automated decide is not appropriate — a human investigator should review this claim.",
  },
};

/* ---------- Required documents per claim type --------------------------- */

const REQ_DOCS = {
  accident: ["Claim form", "Repair estimate"],
  theft: [
    "Claim form",
    "FIR (within 24h)",
    "RC copy",
    "Policy schedule",
    "Key handover",
    "NOC from financier",
  ],
};

/* ---------- Navigation --------------------------------------------------- */

function bindNav() {
  $("#nav-new").addEventListener("click", () => {
    showView("view-submit");
    updateRequiredDocs();
  });
  $("#nav-samples").addEventListener("click", () => {
    showView("view-landing");
    loadRecent();
  });
  $("#brand-home").addEventListener("click", () => {
    showView("view-landing");
    loadRecent();
  });
  $("#hero-start").addEventListener("click", () => showView("view-submit"));
  $("#hero-samples").addEventListener("click", () => {
    showView("view-submit");
    jumpToSampleSelect();
  });
  $("#reset-all").addEventListener("click", resetAll);
  $("#error-back").addEventListener("click", () => showView("view-submit"));
  $("#recent-refresh").addEventListener("click", loadRecent);
}

function jumpToSampleSelect() {
  const first = $("#sample-claim-form");
  if (first) {
    first.focus();
    first.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

/* ---------- Sample loading ----------------------------------------------- */

async function loadSamples() {
  try {
    const res = await fetch(`${API}/samples`);
    if (!res.ok) throw new Error("samples fetch failed");
    state.samples = await res.json();
    const opts = state.samples
      .map(
        (s) =>
          `<option value="${esc(s.id)}">${esc(s.id.toUpperCase())} — ${esc(s.title)}</option>`
      )
      .join("");
    ["sample-claim-form", "sample-second", "sample-incident"].forEach((id) => {
      const sel = $("#" + id);
      const placeholder = id === "sample-claim-form"
        ? "<option value=''>Load a sample claim…</option>"
        : id === "sample-second"
        ? "<option value=''>Load a sample supporting document…</option>"
        : "<option value=''>Load a sample description…</option>";
      sel.innerHTML = placeholder + opts;
    });
  } catch (e) {
    showError("Could not load sample claims", String(e));
  }
}

let sampleApplySeq = 0; // generation token: never let a stale load clobber a newer one

async function applySample(sampleId) {
  const sample = state.samples.find((s) => s.id === sampleId);
  if (!sample) return;
  const seq = ++sampleApplySeq;

  // Reset every zone *before* populating, so a half-finished or failed load
  // can never leave the previous sample's text in place.
  ["claim_form", "second_document", "incident_description"].forEach((id) => {
    $("#" + id).value = "";
  });
  setClaimType(sample.claim_type);

  try {
    const read = (file) =>
      fetch(`${API}/sample-file?sample=${encodeURIComponent(sampleId)}&file=${encodeURIComponent(file)}`)
        .then((r) => {
          if (!r.ok) throw new Error("file fetch failed");
          return r.text();
        });
    const [form, second, incident] = await Promise.all([
      read(sample.claim_form),
      read(sample.second_document),
      read(sample.incident_description),
    ]);
    if (seq !== sampleApplySeq) return; // a newer selection happened meanwhile

    $("#claim_form").value = form;
    $("#second_document").value = second;
    $("#incident_description").value = incident;
    // Visually indicate which zone was used to load.
    ["sample-claim-form", "sample-second", "sample-incident"].forEach((id) => {
      const sel = $("#" + id);
      if (sel.dataset.ownsSample !== sampleId) {
        sel.value = sampleId;
        sel.dataset.ownsSample = sampleId;
      }
    });
    updateInputHints();
  } catch (e) {
    if (seq !== sampleApplySeq) return;
    showError("Could not load the sample claim", String(e));
  }
}

function bindSampleSelects() {
  ["sample-claim-form", "sample-second", "sample-incident"].forEach((id) => {
    $("#" + id).addEventListener("change", (ev) => {
      const val = ev.target.value;
      if (val) applySample(val);
      else {
        // Clearing the dropdown clears that single zone.
        const zone = id.replace("sample-", "");
        const clearMap = {
          "claim-form": "claim_form",
          second: "second_document",
          incident: "incident_description",
        };
        const field = clearMap[id.replace("sample-", "")];
        if (field) $("#" + field).value = "";
        delete ev.target.dataset.ownsSample;
        updateInputHints();
      }
    });
  });
}

/* ---------- Claim type toggle -------------------------------------------- */

function setClaimType(type) {
  state.claimType = type;
  const seg = $("#claim-type-seg");
  seg.querySelectorAll("button").forEach((b) => {
    b.classList.toggle("active", b.dataset.value === type);
  });
  const isAccident = type === "accident";
  const theftCard = $("#theft-docs-card");
  if (theftCard) theftCard.hidden = isAccident;
  $("#second-doc-title").textContent = isAccident ? "Repair estimate" : "FIR";
  $("#second-doc-tag").textContent = isAccident
    ? "For accident claims"
    : "For theft claims";
  $("#second-doc-label").textContent = isAccident
    ? "Paste or type the repair estimate text"
    : "Paste or type the FIR (First Information Report) text";
  $("#second_document").placeholder = isAccident
    ? "Damage list, itemized costs, surveyor notes…"
    : "Police station, FIR number, offence details, date of report…";
  updateRequiredDocs();
  updateInputHints();
}

function bindClaimType() {
  $$("#claim-type-seg button").forEach((b) => {
    b.addEventListener("click", () => setClaimType(b.dataset.value));
  });
}

/* ---------- Required docs checklist -------------------------------------- */

function updateRequiredDocs() {
  const zone = $("#reqdocs");
  const docs = REQ_DOCS[state.claimType] || [];
  const hasForm = ($("#claim_form").value || "").trim().length > 0;
  const hasSecond = ($("#second_document").value || "").trim().length > 0;
  const hasIncident = ($("#incident_description").value || "").trim().length > 0;

  zone.innerHTML = `<span class="reqdocs-title">Required to proceed</span>`;
  docs.forEach((d) => {
    const isCore =
      (d.indexOf("Repair estimate") >= 0 && !hasSecond) ||
      (d.indexOf("FIR") >= 0 && !hasSecond && state.claimType === "theft") ||
      (d.indexOf("Claim form") >= 0 && !hasForm);
    const tag = document.createElement("span");
    tag.className = "reqdocs-tag" + (isCore ? " required-now" : "");
    tag.innerHTML = isCore ? "&#9679;&nbsp; " + esc(d) : "&#10003;&nbsp; " + esc(d);
    zone.appendChild(tag);
  });

  // Theft-only attachments (RC, policy schedule, key handover, NOC) render as
  // their own distinct panel, visible only while a theft claim is selected.
  const theftList = $("#theft-docs-list");
  if (theftList) {
    theftList.innerHTML = `<span class="reqdocs-title">Required to proceed</span>`;
    REQ_DOCS.theft.slice(2).forEach((d) => {
      const tag = document.createElement("span");
      tag.className = "reqdocs-tag";
      tag.innerHTML = "&#10003;&nbsp; " + esc(d);
      theftList.appendChild(tag);
    });
  }
  if (state.claimType === "accident" && !hasSecond) {
    // first-level hint under the estimate field handled by placeholder
  }
}

function updateInputHints() {
  const hasForm = ($("#claim_form").value || "").trim().length > 0;
  const hasSecond = ($("#second_document").value || "").trim().length > 0;
  const hasIncident = ($("#incident_description").value || "").trim().length > 0;
  updateRequiredDocs();

  const hint = $("#submit-hint");
  const filled = [hasForm, hasSecond, hasIncident].filter(Boolean).length;
  if (filled === 3) hint.textContent = "All three documents ready.";
  else if (filled === 0) hint.textContent = "Paste documents or load a sample claim.";
  else hint.textContent = `${filled} of 3 documents entered.`;
}

function bindInputs() {
  ["claim_form", "second_document", "incident_description"].forEach((id) => {
    $("#" + id).addEventListener("input", updateInputHints);
  });
  $$("[data-clear]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const field = btn.dataset.clear;
      $("#" + field).value = "";
      updateInputHints();
    });
  });
}

function resetAll() {
  ["claim_form", "second_document", "incident_description"].forEach((id) => {
    $("#" + id).value = "";
  });
  ["sample-claim-form", "sample-second", "sample-incident"].forEach((id) => {
    $("#" + id).value = "";
    delete $("#" + id).dataset.ownsSample;
  });
  setClaimType("accident");
  updateInputHints();
}

/* ---------- Submission & progress ---------------------------------------- */

async function submitReview() {
  const form = $("#claim_form").value.trim();
  const second = $("#second_document").value.trim();
  const incident = $("#incident_description").value.trim();
  const missing = [];
  if (!form) missing.push("claim form");
  if (!second) missing.push(state.claimType === "accident" ? "repair estimate" : "FIR");
  if (!incident) missing.push("incident description");

  if (missing.length) {
    showError(
      "Missing input",
      `Please provide all required documents before running the review. Missing: ${missing.join(", ")}.`
    );
    return;
  }

  $("#run-review").disabled = true;
  startProgress();

  try {
    const res = await fetch(`${API}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        claim_type: state.claimType,
        second_document_kind: state.claimType === "accident" ? "estimate" : "fir",
        claim_form: form,
        second_document: second,
        incident_description: incident,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new ApiError(data.error || `Review rejected by server (${res.status})`);
    }
    await pollJob(data.job_id);
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : `Network error while submitting: ${String(e)}`;
    stopProgress();
    $("#run-review").disabled = false;
    showError("Review could not be submitted", msg);
  }
}

class ApiError extends Error {}

function startProgress() {
  showView("view-progress");
  const list = $("#stage-list");
  list.innerHTML = `<div class="stage-item running"><span class="stage-icon"></span>Queued for review</div>`;
  $("#progress-sub").textContent = "Running the review pipeline — this takes a few seconds.";
}

function renderStages(stages) {
  const list = $("#stage-list");
  if (!stages || stages.length === 0) return;
  list.innerHTML = stages
    .map((s, i) => {
      const last = i === stages.length - 1;
      const cls = last ? "running" : "done";
      const icon = last ? "" : "&#10003;";
      return `<div class="stage-item ${cls}"><span class="stage-icon">${icon}</span>${esc(s)}</div>`;
    })
    .join("");
}

async function pollJob(jobId) {
  const maxAttempts = 150;
  for (let i = 0; i < maxAttempts; i++) {
    await sleep(400);
    let stateSnapshot;
    try {
      const res = await fetch(`${API}/reviews/${jobId}`);
      if (!res.ok) throw new Error("job fetch failed");
      stateSnapshot = await res.json();
    } catch (e) {
      continue; // transient — keep polling
    }
    renderStages(stateSnapshot.stages || []);
    if (stateSnapshot.status === "done") {
      if (stateSnapshot.report) {
        renderReport(stateSnapshot.report);
        state.reviewsCache.set(jobId, stateSnapshot.report);
        showView("view-report");
        $("#run-review").disabled = false;
      } else {
        $("#run-review").disabled = false;
        showError("Review incomplete", "The pipeline returned no report.");
      }
      return;
    }
    if (stateSnapshot.status === "error") {
      stopProgress();
      $("#run-review").disabled = false;
      showError("Review failed", stateSnapshot.error || "Unknown pipeline error.");
      return;
    }
  }
  stopProgress();
  $("#run-review").disabled = false;
  showError("Review timed out", "The review took longer than expected. Please try again.");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function stopProgress() {
  const list = $("#stage-list");
  list.innerHTML = `<div class="stage-item"><span class="stage-icon"></span>Stopped</div>`;
}

/* ---------- Report rendering ---------------------------------------------- */

function renderReport(report) {
  const root = $("#report-root");
  root.innerHTML = "";

  const disp = DISPOSITIONS[report.disposition] || DISPOSITIONS.escalate;

  // Toolbar
  const toolbar = document.createElement("div");
  toolbar.className = "report-toolbar";
  toolbar.innerHTML = `
    <h2>Claim review report</h2>
    <div style="display:flex;gap:var(--sp-2);flex-wrap:wrap">
      <button class="btn btn-ghost" id="report-download">&#8681;&nbsp; Download report</button>
      <button class="btn btn-ghost" id="report-print">&#128424;&nbsp; Print / PDF</button>
      <button class="btn btn-ghost" id="report-back">&#8592;&nbsp; Back</button>
      <button class="btn btn-primary" id="report-new">&#65291;&nbsp; New review</button>
    </div>`;
  root.appendChild(toolbar);

  // Disposition banner
  const banner = document.createElement("div");
  banner.className = `disposition-banner ${disp.cls}`;
  banner.innerHTML = `
    <div class="disp-icon">${disp.icon}</div>
    <div>
      <h3>${esc(disp.label)}</h3>
      <p>${esc(disp.blurb)}</p>
      <p style="margin-top:var(--sp-2);color:var(--ink-soft)">${esc(report.summary)}</p>
    </div>`;
  root.appendChild(banner);

  const grid = document.createElement("div");
  grid.className = "report-grid";
  root.appendChild(grid);

  // Completeness
  grid.appendChild(completenessSection(report));
  // Consistency
  grid.appendChild(consistencySection(report));
  // Clauses
  grid.appendChild(clausesSection(report));
  // Recommendation
  grid.appendChild(recommendationSection(report));
  // Findings
  grid.appendChild(findingsSection(report));

  $("#report-download").addEventListener("click", () => downloadReportMarkdown(report));
  $("#report-print").addEventListener("click", () => window.print());
  $("#report-back").addEventListener("click", () => {
    showView("view-landing");
    loadRecent();
  });
  $("#report-new").addEventListener("click", () => {
    showView("view-submit");
    updateRequiredDocs();
  });
}

function buildReportMarkdown(report) {
  const disp = DISPOSITIONS[report.disposition] || DISPOSITIONS.escalate;
  const L = [];
  L.push("# Claim review report");
  L.push("");
  L.push(`- **Disposition:** ${disp.label}`);
  L.push(`- **Generated:** ${new Date().toLocaleString()}`);
  L.push("");
  L.push("## Summary");
  L.push(report.summary || "");
  L.push("");

  const rd = report.required_docs || { required: [], present: [], missing: [] };
  L.push("## Document completeness");
  if ((rd.missing || []).length === 0) {
    L.push("All required documents are present.");
  } else {
    L.push(`Missing: ${rd.missing.join(", ")}`);
    if ((rd.present || []).length) L.push(`Present: ${rd.present.join(", ")}`);
  }
  L.push("");

  const cons = report.contradictions || [];
  const contradictions = cons.filter((c) => c.severity === "contradiction");
  const agreements = cons.filter((c) => c.severity === "agreement");
  L.push("## Cross-document consistency");
  if (contradictions.length === 0) {
    L.push("No contradictions detected across the three documents.");
  } else {
    contradictions.forEach((c) => {
      const src = c.between && c.between.length ? ` (Between: ${c.between.join(" & ")})` : "";
      L.push(`- **${c.summary}**${src}. ${c.details || ""}`);
    });
  }
  if (agreements.length) {
    L.push("");
    L.push(`Agreements noted: ${agreements.map((a) => a.summary).join(" ")}`);
  }
  L.push("");

  const clauses = report.clauses || [];
  L.push("## Applicable policy clauses");
  if (clauses.length === 0) {
    L.push("No clauses were retrieved for this claim.");
  } else {
    clauses.forEach((cl) => {
      const num = cl.number ? ` ${cl.number} —` : "";
      L.push(`### Clause${num} ${cl.title || ""}`);
      if (cl.relevance) L.push(`*Relevance:* ${cl.relevance}`);
      L.push("");
      const quote = cl.quote || cl.full_text || "";
      L.push(`> ${quote.replace(/\n+/g, "\n> ")}`);
      if (cl.full_text && cl.full_text !== quote) {
        L.push("");
        L.push(`<details>`);
        L.push(`<summary>Full clause text</summary>`);
        L.push("");
        L.push(cl.full_text);
        L.push("");
        L.push(`</details>`);
      }
      L.push("");
    });
  }

  const findings = report.findings || [];
  L.push("## All findings");
  if (findings.length === 0) {
    L.push("No findings.");
  } else {
    findings.forEach((f) => {
      L.push(`- **${String(f.status || "").toUpperCase()}** — ${f.title}. ${f.detail || ""}`);
    });
  }
  L.push("");

  L.push("## Recommendation");
  L.push(`${disp.label}. ${report.recommendation || ""}`);
  L.push("");
  return L.join("\n");
}

function downloadReportMarkdown(report) {
  const md = buildReportMarkdown(report);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "veroof-report.md";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function completenessSection(report) {
  const sec = sectionEl("&#9745;", "Document completeness", "Declared attachments for this claim type");
  const rd = report.required_docs || { required: [], present: [], missing: [] };
  const ext = report.checks && report.checks.find((c) => c.name === "completeness");

  // Render the DRY checklist of required docs for this claim type, marking
  // the ones we know are present/missing from the report.
  const knownMissing = new Set((rd.missing || []).map(lowerKey) );
  const knownPresent = new Set((rd.present || []).map(lowerKey));
  const allRequired = requiredHumanList();

  allRequired.forEach((item) => {
    const key = lowerKey(item);
    const present = knownPresent.has(key);
    const missing = knownMissing.has(key);
    const row = document.createElement("div");
    row.className = "checklist-item";
    let icon = "&#10003;";
    let markCls = "mark-pass";
    let meta = "Present";
    if (missing) {
      icon = "&#10007;";
      markCls = "mark-fail";
      meta = "Missing";
    } else if (!present) {
      icon = "&#183;";
      markCls = "";
      meta = "Pending confirmation";
    }
    row.innerHTML = `
      <span class="checklist-mark ${markCls}">${icon}</span>
      <div>
        <div class="checklist-label">${esc(item)}</div>
        <div class="checklist-meta">${meta}</div>
      </div>`;
    sec.appendChild(row);
  });

  if (ext && ext.details && ext.details.length) {
    const note = document.createElement("div");
    note.className = "contra-detail";
    note.style.marginTop = "var(--sp-3)";
    note.textContent = ext.details[0];
    sec.appendChild(note);
  }
  return sec;
}

function requiredHumanList() {
  return state.claimType === "theft"
    ? ["claim form", "fir", "rc", "policy schedule", "key handover", "noc financier"]
    : ["claim form", "repair estimate"];
}

function lowerKey(s) {
  return String(s).toLowerCase().replace(/[_\s]+/g, " ").trim();
}

function consistencySection(report) {
  const sec = sectionEl("&#9888;", "Cross-document consistency", "Contradictions surfaced, never smoothed over");
  const cons = report.contradictions || [];
  const contradictions = cons.filter((c) => c.severity === "contradiction");

  if (contradictions.length === 0) {
    const good = document.createElement("div");
    good.className = "contra-none";
    good.innerHTML = "No contradictions detected across the three documents.";
    sec.appendChild(good);
  } else {
    contradictions.forEach((c) => {
      const card = document.createElement("div");
      card.className = "contra-card";
      card.innerHTML = `
        <div class="contra-icon">&#9888;</div>
        <div>
          <div class="contra-title">${esc(c.summary)}</div>
          <div class="contra-detail">${esc(c.details)}</div>
          ${c.between && c.between.length ? `<div class="contra-source">Between: ${c.between.map(esc).join(" &amp; ")}</div>` : ""}
        </div>`;
      sec.appendChild(card);
    });
  }

  if (cons.length) {
    const agree = cons.filter((c) => c.severity === "agreement");
    if (agree.length) {
      const info = document.createElement("div");
      info.className = "contra-detail";
      info.style.marginTop = "var(--sp-3)";
      info.textContent = "Agreements noted: " + agree.map((a) => a.summary).join(" ");
      sec.appendChild(info);
    }
  }
  return sec;
}

function clausesSection(report) {
  const sec = sectionEl("&#9878;", "Applicable policy clauses", "Retrieved from the policy document for this claim");
  const clauses = report.clauses || [];
  if (clauses.length === 0) {
    const none = document.createElement("div");
    none.className = "contra-detail";
    none.textContent = "No clauses were retrieved for this claim.";
    sec.appendChild(none);
    return sec;
  }
  clauses.forEach((cl) => {
    const card = document.createElement("div");
    card.className = "clause-card";
    const shortQuote = cl.quote || cl.full_text || "";
    card.innerHTML = `
      <div class="clause-head">
        <span class="clause-num">Clause ${esc(cl.number)}</span>
        <h4>${esc(cl.title)}</h4>
        <span class="clause-chevron">&#9660;</span>
      </div>
      <div class="clause-body">
        <div class="clause-relevance">${esc(cl.relevance || "Cited for this claim")}</div>
        <div class="clause-quote">${esc(shortQuote)}</div>
        ${cl.full_text && cl.full_text !== shortQuote
          ? `<button class="btn btn-ghost" style="margin-top:var(--sp-2)">&#8597;&nbsp; Show full clause text</button>`
          : ""}
      </div>`;
    const head = card.querySelector(".clause-head");
    const body = card.querySelector(".clause-body");
    const toggleBtn = card.querySelector("button");
    const fullTextHidden = !!toggleBtn;
    head.addEventListener("click", () => {
      card.classList.toggle("expanded");
    });
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const quote = card.querySelector(".clause-quote");
        if (quote.dataset.expanded) {
          quote.textContent = cl.quote || cl.full_text || "";
          quote.dataset.expanded = "";
          toggleBtn.textContent = "\u2197 Show full clause text";
        } else {
          quote.textContent = cl.full_text;
          quote.dataset.expanded = "1";
          toggleBtn.textContent = "\u2191 Show less";
        }
      });
    }
    sec.appendChild(card);
  });
  return sec;
}

function recommendationSection(report) {
  const sec = sectionEl("&#9873;", "Recommendation", "What should happen next");
  sec.className += " rec-card";
  const body = document.createElement("div");
  body.className = "rec-body";
  body.innerHTML = `<strong>${esc(DISPOSITIONS[report.disposition]?.label || report.disposition)}.</strong> ${esc(report.recommendation)}`;
  sec.appendChild(body);
  return sec;
}

function findingsSection(report) {
  const sec = sectionEl("&#9776;", "All findings", "Every check and claim, cited and assessed");
  sec.className += " full";
  const list = document.createElement("div");
  list.className = "findings-list";
  const findings = report.findings || [];
  if (findings.length === 0) {
    list.innerHTML = `<div class="contra-detail">No findings.</div>`;
  }
  findings.forEach((f) => {
    const item = document.createElement("div");
    item.className = `finding-item status-${esc(f.status)}`;
    const tag = document.createElement("span");
    tag.className = "finding-status";
    tag.textContent = f.status;
    const body = document.createElement("div");
    body.innerHTML = `<div class="finding-title">${esc(f.title)}</div>
      <div class="finding-detail">${esc(f.detail)}</div>`;
    item.appendChild(tag);
    item.appendChild(body);
    list.appendChild(item);
  });
  sec.appendChild(list);
  return sec;
}

function sectionEl(icon, title, subtitle) {
  const sec = document.createElement("div");
  sec.className = "report-section";
  sec.innerHTML = `
    <h3 class="section-title"><span class="icon">${icon}</span>${esc(title)}
      <span class="tag" style="margin-left:auto">${esc(subtitle)}</span>
    </h3>`;
  return sec;
}

/* ---------- Recent reviews ------------------------------------------------ */

async function loadRecent() {
  const grid = $("#recent-grid");
  grid.innerHTML = `<div class="contra-detail">Loading…</div>`;
  try {
    const res = await fetch(`${API}/reviews`);
    if (!res.ok) throw new Error("reviews fetch failed");
    const data = await res.json();
    const { disposition = "", type = "" } = state.recentFilters || {};
    const reviews = (data.reviews || []).filter(
      (r) =>
        (!disposition || r.disposition === disposition) &&
        (!type || r.claim_type === type)
    );
    animateCount($("#recent-count"), (data.reviews || []).length);
    if (reviews.length === 0) {
      grid.innerHTML = `<div class="contra-detail" style="grid-column:1/-1">${
        (data.reviews || []).length === 0
          ? "No reviews yet this session. Run a claim review and it will appear here."
          : "No reviews match the current filters."
      }</div>`;
      return;
    }
    grid.innerHTML = "";
    reviews.forEach((r, i) => {
      const card = document.createElement("div");
      card.className = "recent-card";
      card.style.animationDelay = `${Math.min(i * 0.05, 0.45)}s`;
      const chip = `<span class="status-chip status-disposition ${esc(r.disposition)}"><span class="dot"></span>${esc(r.disposition.replace("_", " "))}</span>`;
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--sp-2)">
          ${chip}
          <span style="font-size:11px;color:var(--ink-faint)">#${esc(r.job_id.slice(0, 6))}</span>
        </div>
        <div style="font-weight:700;font-size:14px">${esc(r.title || "Claim review")}</div>
        <div style="font-size:12.5px;color:var(--ink-faint)">${esc(r.claim_type || "")} claim</div>`;
      card.addEventListener("click", () => reopenReview(r.job_id));
      grid.appendChild(card);
    });
  } catch (e) {
    grid.innerHTML = `<div class="contra-detail">Could not load recent reviews.</div>`;
  }
}

function animateCount(el, target) {
  if (!el) return;
  if (!target || target <= 0) {
    el.textContent = String(target || 0);
    return;
  }
  const start = performance.now();
  const dur = 380;
  const step = (t) => {
    const k = Math.min((t - start) / dur, 1);
    el.textContent = String(Math.round(target * (1 - Math.pow(1 - k, 3))));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function bindProofSteps() {
  $$(".proof-step").forEach((step) => {
    step.addEventListener("click", () => {
      const wasActive = step.classList.contains("proof-active");
      $$(".proof-step").forEach((o) => o.classList.remove("proof-active"));
      if (!wasActive) step.classList.add("proof-active");
    });
  });
}

async function reopenReview(jobId) {
  const cached = state.reviewsCache.get(jobId);
  if (cached) {
    renderReport(cached);
    showView("view-report");
    return;
  }
  try {
    const res = await fetch(`${API}/reviews/${jobId}`);
    const data = await res.json();
    if (data.report) {
      state.reviewsCache.set(jobId, data.report);
      renderReport(data.report);
      showView("view-report");
    } else {
      showError("Review unavailable", data.error || "The stored review has no report.");
    }
  } catch (e) {
    showError("Review unavailable", String(e));
  }
}

/* ---------- Error state --------------------------------------------------- */

function showError(title, message, detail) {
  $("#error-title").textContent = title;
  $("#error-message").textContent = message;
  const det = $("#error-detail");
  if (detail) {
    det.style.display = "block";
    det.textContent = detail;
  } else {
    det.style.display = "none";
  }
  showView("view-error");
}

/* ---------- Launch -------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", async () => {
  bindNav();
  bindClaimType();
  bindSampleSelects();
  bindInputs();
  bindProofSteps();
  setClaimType("accident");
  updateRequiredDocs();
  updateInputHints();
  await loadSamples();
  loadRecent();
  $("#run-review").addEventListener("click", submitReview);
});