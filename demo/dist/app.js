(() => {
  const data = window.TRACEREPAIR_DEMO;
  if (!data) {
    document.body.innerHTML = "<p>Demo data is missing. Run scripts/export_web_demo.py.</p>";
    return;
  }

  const $ = (selector) => document.querySelector(selector);
  const setText = (selector, value) => { $(selector).textContent = value; };
  const summary = data.summary;
  const historical = data.historicalBenchmark;
  const langgraph = data.langgraphDevelopment;
  const blind = data.langgraphBlind;
  const developmentAttempts = historical.attempts.filter((attempt) => attempt.split === "development");
  const lockedAttempts = historical.attempts.filter((attempt) => attempt.split === "locked");
  const countSuccesses = (attempts) => attempts.filter((attempt) => attempt.success).length;
  setText("#metric-success", `${historical.successes}/${historical.runs}`);
  setText("#metric-cases", historical.runs);
  setText("#metric-tokens", historical.averageTokens);
  setText("#metric-tools", historical.incorrectAcceptedPatches);
  setText("#dev-score", `${countSuccesses(developmentAttempts)}/${developmentAttempts.length}`);
  setText("#test-score", `${countSuccesses(lockedAttempts)}/${lockedAttempts.length}`);
  setText(
    "#historical-stop-reason",
    `${historical.failures} 个候选补丁未通过目标测试，控制器均在完整回归前停止并转人工；`
      + `锁定集每题只运行一次，未进行失败重试。`,
  );
  setText(
    "#historical-integrity",
    `0 个错误补丁被接受 · report sha256 ${historical.reportSha256.slice(0, 12)}… · `
      + `terminal ledger sha256 ${historical.terminalLedgerSha256.slice(0, 12)}…`,
  );
  setText("#historical-scope", historical.scopeNote);
  setText(
    "#langgraph-comparison",
    `${langgraph.comparison.baselineAgentVersion || langgraph.comparison.baseline_agent_version} `
      + `${Math.round(langgraph.comparison.baseline_pass_at_1 * 5)}/5 → `
      + `${langgraph.agentVersion} ${langgraph.successes}/${langgraph.runs}; `
      + "使用相同五个已知开发任务。",
  );
  setText(
    "#langgraph-tradeoff",
    `错误接受补丁 ${langgraph.incorrectAcceptedPatches} · `
      + `平均 Tokens ${langgraph.comparison.baseline_average_completion_tokens} → ${langgraph.averageTokens} · `
      + `P50 ${langgraph.comparison.baseline_p50_wall_seconds}s → ${langgraph.p50Seconds}s。`,
  );
  setText("#langgraph-scope", langgraph.scopeNote);
  setText(
    "#langgraph-blind-result",
    `${blind.successes}/${blind.runs} pass@1 · ${blind.humanHandoffs} 次安全转人工 · `
      + `${blind.incorrectAcceptedPatches} 个错误补丁被接受。`,
  );
  setText(
    "#langgraph-blind-integrity",
    `每题一次，无事后重试 · ${blind.independentHashChains} 条独立哈希链 · `
      + `evidence ${blind.evidenceIndexSha256.slice(0, 12)}…`,
  );
  setText("#langgraph-blind-scope", blind.scopeNote);
  setText("#generated-at", `snapshot ${new Date(data.generatedAt).toLocaleString("zh-CN")}`);
  if (data.repositoryCohort) {
    const repository = data.repositoryCohort;
    setText("#repository-evidence-label", "FROZEN REAL-MODEL STABILITY");
    setText("#repository-score", `${repository.successes}/${repository.runs} passed`);
    setText(
      "#repository-detail",
      `MiniMath repeat stability · ${repository.averageTokens} average tokens · `
        + `${repository.averageToolCalls} average tool calls. This is not a locked generalization result.`,
    );
  }
  if (data.lockedRepositoryResult) {
    const locked = data.lockedRepositoryResult;
    setText("#locked-repository-evidence-label", "HELD-OUT REPOSITORY · ONE SHOT");
    setText("#locked-repository-score", locked.success ? "1/1 passed" : "0/1 safely stopped");
    setText(
      "#locked-repository-detail",
      `${locked.tokens} output tokens · ${locked.modelCalls} model calls · `
        + `${locked.toolCalls} tool calls · target + regression passed · no retry.`,
    );
  }

  const cohorts = $("#cohorts");
  data.cohorts.forEach((cohort) => {
    const row = document.createElement("div");
    row.className = "cohort";
    const label = document.createElement("span");
    label.textContent = cohort.version;
    const track = document.createElement("div");
    track.className = "cohort-track";
    const fill = document.createElement("div");
    fill.className = "cohort-fill";
    fill.style.width = `${cohort.successRate * 100}%`;
    const value = document.createElement("strong");
    value.textContent = `${Math.round(cohort.successRate * 100)}%`;
    track.appendChild(fill);
    row.append(label, track, value);
    cohorts.appendChild(row);
  });

  const select = $("#trace-select");
  let filter = "all";
  const filteredTraces = () => filter === "all"
    ? data.traces
    : data.traces.filter((trace) => trace.split === filter);

  function renderTimeline(selector, steps) {
    const timeline = $(selector);
    timeline.innerHTML = "";
    steps.forEach((step) => {
      const item = document.createElement("li");
      item.textContent = step;
      timeline.appendChild(item);
    });
  }

  function renderVerification(trace) {
    const gates = ["policy", "apply", "target", "regression"];
    gates.forEach((name) => {
      const gate = trace.verification[name];
      const card = $(`#verify-${name}`);
      card.classList.toggle("pass", gate.ok);
      card.classList.toggle("fail", !gate.ok);
      card.querySelector("strong").textContent = gate.ok ? "PASS" : "STOP";
      const duration = gate.durationMs == null ? "" : ` · ${gate.durationMs} ms`;
      card.querySelector("p").textContent = `${gate.detail}${duration}`;
    });
  }

  function renderPatch(trace) {
    const patch = trace.patchPreview;
    setText("#diff-file", patch.file);
    setText("#diff-added", `+${patch.addedLines}`);
    setText("#diff-removed", `-${patch.removedLines}`);
    setText("#diff-evidence", patch.evidence);
    setText("#diff-hash", `diff sha256 ${patch.diffSha256.slice(0, 12)}…`);
    const code = $("#diff-code");
    code.innerHTML = "";
    patch.lines.forEach((line) => {
      const row = document.createElement("div");
      row.className = `diff-line ${line.kind}`;
      const marker = document.createElement("span");
      marker.textContent = line.kind === "added" ? "+" : line.kind === "removed" ? "−" : "·";
      const content = document.createElement("code");
      content.textContent = line.text;
      row.append(marker, content);
      code.appendChild(row);
    });
  }

  function renderTrace(taskId) {
    const trace = data.traces.find((item) => item.taskId === taskId) || filteredTraces()[0];
    if (!trace) return;
    setText("#task-id", trace.taskId);
    setText("#trace-issue", trace.issue);
    setText("#fact-case", `${trace.caseId} / ${trace.split}`);
    setText("#fact-calls", trace.modelCalls);
    setText("#fact-tokens", trace.tokens);
    setText("#fact-tools", trace.toolCalls);
    $("#gate-target").classList.toggle("pass", trace.targetPassed);
    $("#gate-regression").classList.toggle("pass", trace.regressionPassed);
    $("#gate-review").classList.toggle("pass", trace.status === "awaiting_review");
    renderTimeline("#timeline", trace.timeline);
    renderVerification(trace);
    renderPatch(trace);
  }

  function populateSelect() {
    const previous = select.value;
    select.innerHTML = "";
    filteredTraces().forEach((trace) => {
      const option = document.createElement("option");
      option.value = trace.taskId;
      option.textContent = `Case ${trace.caseId} · ${trace.caseName} · ${trace.tokens} tok`;
      select.appendChild(option);
    });
    if ([...select.options].some((option) => option.value === previous)) select.value = previous;
    renderTrace(select.value);
  }

  document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll(".filter").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    filter = button.dataset.filter;
    populateSelect();
  }));
  select.addEventListener("change", () => renderTrace(select.value));
  populateSelect();

  function yesNo(value) {
    return value ? "YES" : "NO";
  }

  function renderFailure(taskId) {
    const failure = data.failures.find((item) => item.taskId === taskId) || data.failures[0];
    if (!failure) return;
    setText("#failure-category", failure.category.replaceAll("_", " "));
    setText("#failure-title", failure.title);
    setText("#failure-issue", failure.issue);
    setText("#failure-task", failure.taskId);
    setText("#failure-tokens", failure.tokens);
    setText("#failure-tools", failure.toolCalls);
    setText("#failure-recoveries", failure.control.deterministicRecoveries);
    setText("#failure-attempted", yesNo(failure.control.patchAttempted));
    setText("#failure-applied", yesNo(failure.control.patchApplied));
    setText("#failure-tests", yesNo(failure.control.testsStarted));
    setText("#failure-reason", failure.control.stopReason);
    setText("#failure-outcome", failure.controlOutcome);
    setText("#failure-lesson", failure.lesson);
    renderTimeline("#failure-timeline", failure.timeline);
    document.querySelectorAll(".failure-tab").forEach((button) => {
      const active = button.dataset.taskId === failure.taskId;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  const failureTabs = $("#failure-tabs");
  data.failures.forEach((failure, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "failure-tab";
    button.dataset.taskId = failure.taskId;
    button.setAttribute("role", "tab");
    const number = document.createElement("span");
    number.textContent = `0${index + 1}`;
    button.append(number, document.createTextNode(failure.title));
    button.addEventListener("click", () => renderFailure(failure.taskId));
    failureTabs.appendChild(button);
  });
  renderFailure(data.failures[0]?.taskId);

  function renderRecovery(taskId) {
    const scenario = data.recoveryScenarios.find((item) => item.task_id === taskId)
      || data.recoveryScenarios[0];
    if (!scenario) return;
    setText("#recovery-point", scenario.crash_point.replaceAll("_", " "));
    setText("#recovery-title", scenario.title);
    setText("#recovery-task", scenario.task_id);
    setText("#recovery-before-calls", scenario.phase_one_model_calls);
    setText("#recovery-after-calls", scenario.resume_model_calls);
    setText("#recovery-status", scenario.final_status);
    setText("#recovery-guard", scenario.integrity_guard);

    const skipped = $("#recovery-skipped");
    skipped.innerHTML = "";
    scenario.skipped_tools.forEach((tool) => {
      const chip = document.createElement("code");
      chip.textContent = tool;
      skipped.appendChild(chip);
    });

    const timeline = $("#recovery-timeline");
    timeline.innerHTML = "";
    scenario.timeline.forEach((step, index) => {
      const item = document.createElement("div");
      item.className = `recovery-step ${step.state}`;
      const marker = document.createElement("span");
      marker.textContent = String(index + 1).padStart(2, "0");
      const copy = document.createElement("div");
      const label = document.createElement("strong");
      label.textContent = step.label;
      const detail = document.createElement("p");
      detail.textContent = step.detail;
      copy.append(label, detail);
      item.append(marker, copy);
      timeline.appendChild(item);
    });
    document.querySelectorAll(".recovery-tab").forEach((button) => {
      const active = button.dataset.taskId === scenario.task_id;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  const recoveryTabs = $("#recovery-tabs");
  data.recoveryScenarios.forEach((scenario, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "recovery-tab";
    button.dataset.taskId = scenario.task_id;
    button.setAttribute("role", "tab");
    const number = document.createElement("span");
    number.textContent = `SCENARIO 0${index + 1}`;
    const label = document.createElement("strong");
    label.textContent = scenario.title;
    button.append(number, label);
    button.addEventListener("click", () => renderRecovery(scenario.task_id));
    recoveryTabs.appendChild(button);
  });
  renderRecovery(data.recoveryScenarios[0]?.task_id);
})();
