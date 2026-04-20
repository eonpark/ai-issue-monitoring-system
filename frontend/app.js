const API_BASE = "";
const REFRESH_INTERVAL = 5000;

let currentFilter = "ALL";
let latestResult = null;
let storedIssues = [];
let schedulerStatus = null;

const runButton = document.getElementById("runButton");
const schedulerStartedEl = document.getElementById("schedulerStarted");
const schedulerRunningEl = document.getElementById("schedulerRunning");
const schedulerNextRunEl = document.getElementById("schedulerNextRun");
const schedulerLastRunEl = document.getElementById("schedulerLastRun");
const serverStatus = document.getElementById("serverStatus");
const errorBanner = document.getElementById("errorBanner");
const finalStepEl = document.getElementById("finalStep");
const actionsEl = document.getElementById("actions");
const totalCountEl = document.getElementById("totalCount");
const processedCountEl = document.getElementById("processedCount");
const dedupBeforeEl = document.getElementById("dedupBefore");
const dedupAfterEl = document.getElementById("dedupAfter");
const dedupDuplicatesEl = document.getElementById("dedupDuplicates");
const metricCollectionEl = document.getElementById("metricCollection");
const metricAnalysisEl = document.getElementById("metricAnalysis");
const metricAuditEl = document.getElementById("metricAudit");
const metricDeliveryEl = document.getElementById("metricDelivery");
const lastUpdatedEl = document.getElementById("lastUpdated");
const tableBody = document.getElementById("issuesTableBody");
const filterButtons = document.querySelectorAll(".filter-button");
const issueMeta = document.getElementById("issueMeta");
const storedIssueMeta = document.getElementById("storedIssueMeta");
const countAllEl = document.getElementById("countAll");
const countOkEl = document.getElementById("countOk");
const countNoOkEl = document.getElementById("countNoOk");
const storedIssuesTableBody = document.getElementById("storedIssuesTableBody");

async function handleRunPipeline() {
  console.log("Run Pipeline clicked");
  if (!runButton) {
    return;
  }
  runButton.disabled = true;
  runButton.textContent = "Running...";
  try {
    const response = await fetch(`${API_BASE}/run`, { method: "POST" });
    if (!response.ok) {
      throw new Error("run_failed");
    }
    latestResult = await response.json();
    resetFilterToAll();
    render(latestResult);
    showServerConnected();
  } catch (error) {
    showServerError();
  } finally {
    runButton.disabled = false;
    runButton.textContent = "Run Pipeline";
  }
}

runButton?.addEventListener("click", handleRunPipeline);

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    currentFilter = button.dataset.filter;
    filterButtons.forEach((item) => item.classList.toggle("active", item === button));
    renderTable(getIssues(latestResult));
  });
});

async function fetchResult() {
  try {
    const [resultResponse, issuesResponse, schedulerResponse] = await Promise.all([
      fetch(`${API_BASE}/result`),
      fetch(`${API_BASE}/issues`),
      fetch(`${API_BASE}/scheduler-status`),
    ]);
    if (!resultResponse.ok || !issuesResponse.ok || !schedulerResponse.ok) {
      throw new Error("result_failed");
    }
    const payload = await resultResponse.json();
    const issuesPayload = await issuesResponse.json();
    const schedulerPayload = await schedulerResponse.json();
    latestResult = payload.result;
    storedIssues = Array.isArray(issuesPayload.issues) ? issuesPayload.issues : [];
    schedulerStatus = schedulerPayload.scheduler || null;
    render(latestResult);
    renderStoredIssues(storedIssues);
    renderSchedulerStatus(schedulerStatus);
    showServerConnected();
  } catch (error) {
    showServerError();
  }
}

function render(result) {
  if (!result) {
    safeText(finalStepEl, "-");
    safeText(actionsEl, "-");
    safeText(totalCountEl, "0");
    safeText(processedCountEl, "0");
    safeText(dedupBeforeEl, "0");
    safeText(dedupAfterEl, "0");
    safeText(dedupDuplicatesEl, "0");
    renderMetrics({});
    safeText(lastUpdatedEl, "No data");
    renderSchedulerStatus(null);
    safeText(issueMeta, "분석 결과와 검증 상태를 확인합니다.");
    safeText(storedIssueMeta, "DB에 누적 저장된 이슈 이력입니다.");
    updateFilterCounts([]);
    renderTable([]);
    renderStoredIssues([]);
    return;
  }

  const issues = getIssues(result);
  console.log("Issue results loaded:", issues.length, issues);
  safeText(finalStepEl, result.final_step || "-");
  safeText(actionsEl, Array.isArray(result.actions) ? result.actions.join(" → ") : "-");
  safeText(totalCountEl, String(result.total ?? 0));
  safeText(processedCountEl, String(result.processed ?? 0));
  safeText(dedupBeforeEl, String(result.dedup?.before ?? 0));
  safeText(dedupAfterEl, String(result.dedup?.after ?? 0));
  safeText(dedupDuplicatesEl, String(result.dedup?.duplicates ?? 0));
  renderMetrics(result.metrics || {});
  safeText(lastUpdatedEl, result.last_run_time || "No timestamp");
  safeText(issueMeta, `전체 ${issues.length}건의 검사 결과를 표시합니다.`);
  updateFilterCounts(issues);
  renderTable(issues);
  renderStoredIssues(storedIssues);
}

function renderSchedulerStatus(status) {
  safeText(schedulerStartedEl, status?.started ? "작동 중" : "중지");
  safeText(schedulerRunningEl, status?.running ? "실행 중" : "대기");
  safeText(schedulerNextRunEl, status?.next_run_time || "-");
  safeText(schedulerLastRunEl, status?.last_run_time || "-");
}

function renderMetrics(metrics) {
  const collection = metrics.collection || {};
  const analysis = metrics.analysis || {};
  const audit = metrics.audit || {};
  const delivery = metrics.delivery || {};

  safeText(
    metricCollectionEl,
    `수집 ${collection.collector_count ?? 0}건 / 국내 ${collection.domestic_count ?? 0}건 / 해외 ${collection.global_count ?? 0}건`
  );
  safeText(
    metricAnalysisEl,
    `주요 이슈 ${toPercent(analysis.major_issue_rate)} / 사건 ${analysis.event_count ?? 0} / 추세 ${analysis.trend_count ?? 0} / 신호 ${analysis.signal_count ?? 0}`
  );
  safeText(
    metricAuditEl,
    `통과 ${toPercent(audit.audit_pass_rate)} / 날짜 없음 ${toPercent(audit.missing_publication_date_rate)} / 오래됨 ${toPercent(audit.outdated_source_rate)} / 본문 부족 ${toPercent(audit.insufficient_content_rate)} / 일반 페이지 ${toPercent(audit.generic_source_fail_rate)} / 내용 불일치 ${toPercent(audit.content_mismatch_rate)} / 링크 검증 실패 ${toPercent(audit.source_verification_fail_rate)}`
  );
  safeText(
    metricDeliveryEl,
    `중복 제거 ${toPercent(delivery.dedup_rate)} / 최종 OK ${delivery.validator_ok_count ?? 0}건`
  );
}

function renderTable(issues) {
  const filteredIssues = issues.filter((issue) => {
    if (currentFilter === "ALL") return true;
    return issue.status === currentFilter;
  });

  if (!filteredIssues.length) {
    const message = issues.length
      ? "현재 필터에 맞는 데이터가 없습니다."
      : "데이터가 없습니다.";
    tableBody.innerHTML = `<tr><td colspan="10" class="empty-state">${message}</td></tr>`;
    return;
  }

  tableBody.innerHTML = filteredIssues
    .map((issue) => {
      const rowClass = issue.status === "OK" ? "row-ok" : "row-no-ok";
      const link = issue.url
        ? `<a href="${escapeHtml(issue.url)}" target="_blank" rel="noreferrer">Open</a>`
        : "-";

      return `
        <tr class="${rowClass}">
          <td class="title-cell">${escapeHtml(issue.title || "-")}</td>
          <td class="summary-cell">${escapeHtml(issue.summary || "-")}</td>
          <td>${escapeHtml(String(issue.score ?? "-"))}</td>
          <td>${renderBadge(formatIssueType(issue.issue_type))}</td>
          <td>${renderBadge(formatImpactScope(issue.impact_scope))}</td>
          <td>${renderBadge(formatChangeNature(issue.change_nature))}</td>
          <td>${renderBoolean(issue.major_issue)}</td>
          <td class="status-cell">${escapeHtml(issue.status || "-")}</td>
          <td class="reason-cell">${escapeHtml(issue.validation_reason || issue.validation_status || "-")}</td>
          <td class="link-cell">${link}</td>
        </tr>
      `;
    })
    .join("");
}

function renderStoredIssues(issues) {
  safeText(storedIssueMeta, `DB 누적 이슈 ${issues.length}건`);

  if (!issues.length) {
    storedIssuesTableBody.innerHTML = `<tr><td colspan="7" class="empty-state">저장된 이슈가 없습니다.</td></tr>`;
    return;
  }

  storedIssuesTableBody.innerHTML = issues
    .map((issue) => {
      const rowClass = issue.status === "OK" ? "row-ok" : "row-no-ok";
      const link = issue.url
        ? `<a href="${escapeHtml(issue.url)}" target="_blank" rel="noreferrer">Open</a>`
        : "-";

      return `
        <tr class="${rowClass}">
          <td>${escapeHtml(issue.created_at || "-")}</td>
          <td class="title-cell">${escapeHtml(issue.title || "-")}</td>
          <td>${escapeHtml(String(issue.score ?? "-"))}</td>
          <td>${renderBadge(formatIssueType(issue.issue_type))}</td>
          <td class="status-cell">${escapeHtml(issue.status || "-")}</td>
          <td class="reason-cell">${escapeHtml(issue.validation_reason || "-")}</td>
          <td class="link-cell">${link}</td>
        </tr>
      `;
    })
    .join("");
}

function getIssues(result) {
  if (!result) return [];
  if (Array.isArray(result.data)) return result.data;
  if (Array.isArray(result.issues)) return result.issues;
  if (result.result) return getIssues(result.result);
  return [];
}

function updateFilterCounts(issues) {
  const okCount = issues.filter((issue) => issue.status === "OK").length;
  const noOkCount = issues.filter((issue) => issue.status === "NO_OK").length;
  safeText(countAllEl, String(issues.length));
  safeText(countOkEl, String(okCount));
  safeText(countNoOkEl, String(noOkCount));
}

function resetFilterToAll() {
  currentFilter = "ALL";
  filterButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === "ALL");
  });
}

function showServerConnected() {
  safeText(serverStatus, "서버 연결 정상");
  errorBanner?.classList.add("hidden");
}

function showServerError() {
  safeText(serverStatus, "서버 연결 실패");
  errorBanner?.classList.remove("hidden");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeText(element, value) {
  if (element) {
    element.textContent = value;
  }
}

function renderBoolean(value) {
  if (value === true) return '<span class="meta-badge meta-true">예</span>';
  if (value === false) return '<span class="meta-badge meta-false">아니오</span>';
  return '<span class="meta-badge">-</span>';
}

function renderBadge(value) {
  return `<span class="meta-badge">${escapeHtml(String(value || "-"))}</span>`;
}

function toPercent(value) {
  const numeric = Number(value || 0);
  return `${Math.round(numeric * 100)}%`;
}

function formatIssueType(value) {
  const mapping = {
    event: "사건",
    trend: "추세",
    signal: "신호",
  };
  return mapping[String(value || "").toLowerCase()] || value || "-";
}

function formatImpactScope(value) {
  const mapping = {
    global: "글로벌",
    regional: "지역/국가",
    limited: "제한적",
  };
  return mapping[String(value || "").toLowerCase()] || value || "-";
}

function formatChangeNature(value) {
  const mapping = {
    concrete_change: "실제 변화",
    ongoing_shift: "진행 중인 변화",
    commentary: "해설/논평",
  };
  return mapping[String(value || "").toLowerCase()] || value || "-";
}

fetchResult();
setInterval(fetchResult, REFRESH_INTERVAL);
