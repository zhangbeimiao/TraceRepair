(() => {
  const data = window.TRACEREPAIR_DEMO;
  if (!data) { document.body.innerHTML = "<p>Demo data is missing. Run scripts/export_web_demo.py.</p>"; return; }
  const $ = (selector) => document.querySelector(selector);
  const summary = data.summary;
  $("#metric-success").textContent = `${summary.successes}/${summary.runs}`;
  $("#metric-cases").textContent = summary.evaluatedBugTypes;
  $("#metric-tokens").textContent = summary.averageTokens;
  $("#metric-tools").textContent = summary.averageToolCalls;
  $("#dev-score").textContent = `${summary.development.successful_runs}/${summary.development.runs}`;
  $("#test-score").textContent = `${summary.locked.successful_runs}/${summary.locked.runs}`;
  $("#generated-at").textContent = `snapshot ${new Date(data.generatedAt).toLocaleString("zh-CN")}`;
  const cohorts = $("#cohorts");
  data.cohorts.forEach((cohort) => {
    const row = document.createElement("div"); row.className = "cohort";
    row.innerHTML = `<span>${cohort.version}</span><div class="cohort-track"><div class="cohort-fill" style="width:${cohort.successRate * 100}%"></div></div><strong>${Math.round(cohort.successRate * 100)}%</strong>`;
    cohorts.appendChild(row);
  });
  const select = $("#trace-select"); let filter = "all";
  const filteredTraces = () => filter === "all" ? data.traces : data.traces.filter((trace) => trace.split === filter);
  function renderTrace(taskId) {
    const trace = data.traces.find((item) => item.taskId === taskId) || filteredTraces()[0]; if (!trace) return;
    $("#task-id").textContent=trace.taskId; $("#trace-issue").textContent=trace.issue; $("#fact-case").textContent=`${trace.caseId} / ${trace.split}`;
    $("#fact-calls").textContent=trace.modelCalls; $("#fact-tokens").textContent=trace.tokens; $("#fact-tools").textContent=trace.toolCalls;
    $("#gate-target").classList.toggle("pass",trace.targetPassed); $("#gate-regression").classList.toggle("pass",trace.regressionPassed); $("#gate-review").classList.toggle("pass",trace.status === "awaiting_review");
    const timeline=$("#timeline"); timeline.innerHTML=""; trace.timeline.forEach((step) => { const item=document.createElement("li"); item.textContent=step; timeline.appendChild(item); });
  }
  function populateSelect() {
    const previous=select.value; select.innerHTML="";
    filteredTraces().forEach((trace) => { const option=document.createElement("option"); option.value=trace.taskId; option.textContent=`Case ${trace.caseId} · ${trace.caseName} · ${trace.tokens} tok`; select.appendChild(option); });
    if ([...select.options].some((option) => option.value === previous)) select.value=previous; renderTrace(select.value);
  }
  document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll(".filter").forEach((item) => item.classList.remove("active")); button.classList.add("active"); filter=button.dataset.filter; populateSelect(); }));
  select.addEventListener("change", () => renderTrace(select.value)); populateSelect();
})();
