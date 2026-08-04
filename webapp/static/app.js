/* Web shell frontend - no framework, no build step.
   Talks only to the FastAPI contract endpoints. */

const state = {
  caseId: null,
  jobId: null,
  ws: null,
  wsRetry: 0,
  wsTimer: null,
  awaitingNode: null,
  paperMarkdown: "",
};

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

function toast(msg, kind = "") {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast " + kind;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 4200);
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
  return data;
}

const jpost = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

function humanId() {
  const v = $("human-id").value.trim();
  if (!v) {
    toast("请先在右上角填写审批人（真人标识）——审批不能由 AI 署名", "err");
    $("human-id").focus();
    return null;
  }
  return v;
}

/* ---------------- health / driver ---------------- */
async function loadHealth() {
  try {
    const h = await api("/api/health");
    const badge = $("driver-badge");
    if (h.driver.real_driver_available) {
      badge.textContent = "驱动已接入 · " + h.driver.model;
      badge.className = "badge badge-ok";
    } else {
      badge.textContent = "驱动 stub（S1 未交付）";
      badge.className = "badge badge-warn";
      badge.title = "期望的导入路径: " + h.driver.expected_import;
    }
  } catch (e) {
    $("driver-badge").textContent = "后端不可达";
    $("driver-badge").className = "badge badge-err";
  }
}

/* ---------------- cases ---------------- */
async function loadCases() {
  const cases = await api("/api/cases");
  const sel = $("case-select");
  sel.innerHTML = "";
  if (!cases.length) {
    sel.innerHTML = '<option value="">（暂无 Case，先用 CLI create-case）</option>';
    return;
  }
  cases.forEach((c) => {
    const o = document.createElement("option");
    o.value = c.case_id;
    o.textContent = `${c.case_id} · ${c.title ?? ""}`;
    sel.appendChild(o);
  });
  const keep = cases.find((c) => c.case_id === state.caseId);
  state.caseId = keep ? state.caseId : cases[cases.length - 1].case_id;
  sel.value = state.caseId;
  await loadCase();
}

async function loadCase() {
  if (!state.caseId) return;
  try {
    const snap = await api(`/api/cases/${encodeURIComponent(state.caseId)}`);
    renderCaseMeta(snap);
    renderDag(snap.workflow_dag);
    renderTable("artifacts-table", snap.artifacts, ["artifact_id", "artifact_type", "path", "created_by", "status"]);
    renderTable("claims-table", snap.claims, ["claim_id", "claim_type", "text", "status"]);
    renderFigures(snap.figures);
    loadJobsForCase();
  } catch (e) {
    toast("加载 Case 失败: " + e.message, "err");
  }
}

function renderCaseMeta(snap) {
  const m = snap.manifest?.manifest ?? snap.manifest ?? {};
  $("case-meta").innerHTML =
    `type=${esc(m.competition_type ?? "-")} · status=${esc(m.status ?? "-")}<br>` +
    `artifacts=${snap.artifacts.length} · claims=${snap.claims.length} · figures=${snap.figures.length}` +
    (snap.pending_approvals.length
      ? `<br><span style="color:#d29922">待审批: ${snap.pending_approvals.map(esc).join(", ")}</span>`
      : "");
}

function renderDag(dag) {
  const nodes = dag?.nodes ?? {};
  const defs = dag?.definitions ?? {};
  const counts = {};
  Object.values(nodes).forEach((n) => (counts[n.status] = (counts[n.status] || 0) + 1));
  $("dag-counts").textContent = Object.entries(counts).map(([k, v]) => `${k}:${v}`).join("  ");

  // 更新审批徽标
  updateApprovalBadges(nodes);

  // 检查是否需要显示引导上传
  checkBlockedHint(nodes);

  const rows = Object.entries(nodes).map(([id, rt]) => {
    const d = defs[id] || {};
    const needApprove = rt.status === "NEEDS_REVIEW";
    const canRetry = ["FAILED", "BLOCKED", "STALE", "DEGRADED"].includes(rt.status);
    let act = "";
    if (needApprove) act += `<button class="inline-btn" data-approve="${esc(id)}">批准</button> `;
    if (canRetry) act += `<button class="inline-btn" data-retry="${esc(id)}">重试</button> `;
    if (!needApprove && !canRetry) act = "-";
    return `<tr>
      <td>${esc(id)}</td>
      <td><span class="status-pill s-${esc(rt.status)}">${esc(rt.status)}</span></td>
      <td>${rt.attempts ?? 0}</td>
      <td>${d.approval_required ? "是" : "否"}</td>
      <td>${esc((d.dependencies || []).join(", ") || "-")}</td>
      <td>${act}</td>
    </tr>`;
  });

  $("dag-table").innerHTML = `<table>
    <thead><tr><th>节点</th><th>状态</th><th>尝试</th><th>需审批</th><th>依赖</th><th>操作</th></tr></thead>
    <tbody>${rows.join("")}</tbody></table>`;

  $("dag-table").querySelectorAll("[data-approve]").forEach((b) =>
    b.addEventListener("click", () => approveNode(b.dataset.approve))
  );
  $("dag-table").querySelectorAll("[data-retry]").forEach((b) =>
    b.addEventListener("click", () => retryNode(b.dataset.retry))
  );
}

const APPROVAL_NODES = ["data_registration", "model_selection", "paper_ready", "final_review"];

function updateApprovalBadges(nodes) {
  APPROVAL_NODES.forEach((nodeId) => {
    const badge = $(`badge-${nodeId}`);
    const badgeContainer = badge?.closest(".approval-badge");
    if (!badge || !badgeContainer) return;

    const node = nodes[nodeId];
    const status = node?.status || "PENDING";

    // 清除旧状态类
    badgeContainer.classList.remove("blocked", "approved", "pending", "running");

    if (status === "SUCCEEDED") {
      badge.textContent = "已批准";
      badgeContainer.classList.add("approved");
    } else if (status === "NEEDS_REVIEW") {
      badge.textContent = "待审批";
      badgeContainer.classList.add("pending");
    } else if (status === "RUNNING") {
      badge.textContent = "进行中";
      badgeContainer.classList.add("running");
    } else if (status === "BLOCKED" || status === "FAILED") {
      badge.textContent = "已阻塞";
      badgeContainer.classList.add("blocked");
    } else {
      badge.textContent = status;
      badgeContainer.classList.add("pending");
    }
  });
}

function checkBlockedHint(nodes) {
  const hintEl = $("blocked-upload-hint");
  const hasBlocked = Object.values(nodes).some((n) => n.status === "BLOCKED");
  const hasDataReg = nodes["data_registration"];
  const noData = !hasDataReg || hasDataReg.status === "PENDING";

  if (hasBlocked && noData) {
    hintEl.classList.remove("hidden");
  } else {
    hintEl.classList.add("hidden");
  }
}

function renderTable(elId, rows, cols) {
  const el = $(elId);
  if (!rows || !rows.length) { el.innerHTML = '<p class="meta">（空）</p>'; return; }
  const keys = cols.filter((c) => rows.some((r) => r[c] !== undefined));
  el.innerHTML = `<table>
    <thead><tr>${keys.map((k) => `<th>${esc(k)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${keys.map((k) => `<td title="${esc(r[k])}">${esc(r[k] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
}

function renderFigures(figures) {
  const el = $("figures-grid");
  if (!figures || !figures.length) { el.innerHTML = '<p class="meta">（暂无图形）</p>'; return; }
  el.innerHTML = figures.map((f, i) => `
    <figure>
      <img src="/api/cases/${encodeURIComponent(state.caseId)}/figures/${i}" alt="${esc(f.title)}"
           onerror="this.style.display='none'" />
      <figcaption>${esc(f.title ?? "figure")} · ${esc(f.status ?? "")}</figcaption>
    </figure>`).join("");
}

/* ---------------- approvals ---------------- */
async function approveNode(nodeId, note) {
  const who = humanId(); if (!who) return;
  try {
    await jpost(`/api/cases/${encodeURIComponent(state.caseId)}/approve`, {
      node_id: nodeId, note: note || "Evidence reviewed via web shell", approved_by: who,
    });
    toast(`节点 ${nodeId} 已批准`, "ok");
    loadCase(); loadLedger();
  } catch (e) { toast("审批失败: " + e.message, "err"); }
}

async function retryNode(nodeId) {
  const who = humanId(); if (!who) return;
  const reason = prompt(`重试节点 ${nodeId} 的原因：`, "Manual retry from web shell");
  if (reason === null) return;
  try {
    await jpost(`/api/cases/${encodeURIComponent(state.caseId)}/retry`, {
      node_id: nodeId, reason, requested_by: who,
    });
    toast(`节点 ${nodeId} 已请求重试`, "ok");
    loadCase();
  } catch (e) { toast("重试失败: " + e.message, "err"); }
}

/* ---------------- chat ---------------- */
function pushMsg(cls, html) {
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.innerHTML = html;
  $("chat-log").appendChild(d);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
}

async function sendChat() {
  const msg = $("chat-message").value.trim();
  if (!msg) return;
  if (!state.caseId) { toast("请先选择 Case", "err"); return; }
  pushMsg("msg-user", esc(msg));
  $("chat-message").value = "";
  $("chat-send").disabled = true;
  try {
    const r = await jpost("/api/chat", {
      case_id: state.caseId, session_id: null, message: msg, context: {},
    });
    const chips = (r.tool_calls || []).map((t) =>
      `<span class="chip ${t.requires_approval ? "need-approval" : ""}">${esc(t.tool)}${t.requires_approval ? " ⚠需审批" : ""}</span>`
    ).join("");
    pushMsg("msg-bot", esc(r.reply) + (chips ? `<div class="tool-chips">${chips}</div>` : ""));
    pushMsg("msg-sys", `ledger=${esc(r.ledger.entry_id)} · used_ai=${r.ledger.used_ai}` +
      (r.job_id ? ` · job=${esc(r.job_id)}` : ""));
    if (r.job_id) attachJob(r.job_id);
    loadLedger();
  } catch (e) {
    pushMsg("msg-sys", "请求失败: " + esc(e.message));
  } finally {
    $("chat-send").disabled = false;
  }
}

/* ---------------- jobs + websocket ---------------- */
async function startJob() {
  const who = humanId(); if (!who) return;
  if (!state.caseId) { toast("请先选择 Case", "err"); return; }
  try {
    const r = await jpost("/api/jobs", {
      case_id: state.caseId, kind: $("job-kind").value, payload: {}, approved_by: who,
    });
    toast("任务已创建: " + r.job_id, "ok");
    attachJob(r.job_id);
  } catch (e) { toast("创建任务失败: " + e.message, "err"); }
}

function attachJob(jobId) {
  state.jobId = jobId;
  $("job-events").innerHTML = "";
  connectWS(jobId);
  pollJob(jobId);
}

function logEvent(ev) {
  const cls =
    ev.type === "progress" ? "ev-progress" :
    ev.type === "approval_required" ? "ev-approval" :
    ev.type === "done" ? "ev-done" :
    ev.type === "ledger" ? "ev-ledger" :
    ev.type === "error" ? "ev-error" : "";
  const time = (ev.ts || "").slice(11, 19);
  let text = ev.type;
  if (ev.type === "progress") text = `${ev.node} → ${ev.status} (${Math.round((ev.progress || 0) * 100)}%)`;
  else if (ev.type === "approval_required") text = `需审批: ${(ev.nodes || []).join(", ")}`;
  else if (ev.type === "ledger") text = `台账写入 ${ev.entry_id}`;
  else if (ev.type === "done") text = "任务完成";
  else if (ev.type === "error") text = "错误: " + ev.message;
  else if (ev.type === "hello") text = `已连接 (status=${ev.status})`;
  const d = document.createElement("div");
  d.className = cls;
  d.textContent = `[${time}] ${text}`;
  $("job-events").appendChild(d);
  $("job-events").scrollTop = $("job-events").scrollHeight;
}

function applyEvent(ev) {
  logEvent(ev);
  if (ev.type === "progress") {
    $("job-progress").style.width = Math.round((ev.progress || 0) * 100) + "%";
    $("job-status").textContent = `job=${state.jobId} · ${ev.node} · ${ev.status}`;
  }
  if (ev.type === "approval_required") {
    state.awaitingNode = (ev.nodes || [])[0];
    $("approval-node").textContent = state.awaitingNode;
    $("job-approval").classList.remove("hidden");
    loadCase();
  }
  if (ev.type === "done") {
    $("job-progress").style.width = "100%";
    $("job-status").textContent = `job=${state.jobId} · 已完成`;
    $("job-approval").classList.add("hidden");
    loadCase(); loadLedger();
  }
  if (ev.type === "cancelled") $("job-status").textContent = `job=${state.jobId} · 已取消`;
}

function connectWS(jobId) {
  if (state.ws) { try { state.ws.close(); } catch {} state.ws = null; }
  clearTimeout(state.wsTimer);
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}`);
  state.ws = ws;

  ws.onopen = () => {
    state.wsRetry = 0;
    $("ws-badge").textContent = "WS 已连接";
    $("ws-badge").className = "badge badge-ok";
  };
  ws.onmessage = (e) => { try { applyEvent(JSON.parse(e.data)); } catch {} };
  ws.onerror = () => {
    $("ws-badge").textContent = "WS 异常";
    $("ws-badge").className = "badge badge-err";
  };
  ws.onclose = () => {
    if (state.jobId !== jobId) return;
    // exponential backoff, and fall back to REST so no state is lost
    const delay = Math.min(1000 * 2 ** state.wsRetry, 15000);
    state.wsRetry += 1;
    $("ws-badge").textContent = `WS 重连中(${Math.round(delay / 1000)}s)`;
    $("ws-badge").className = "badge badge-warn";
    pollJob(jobId);
    state.wsTimer = setTimeout(() => connectWS(jobId), delay);
  };
}

async function pollJob(jobId) {
  try {
    const j = await api(`/api/jobs/${encodeURIComponent(jobId)}?case_id=${encodeURIComponent(state.caseId)}`);
    $("job-status").textContent =
      `job=${j.job_id} · status=${j.status} · node=${j.current_node ?? "-"} · mode=${j.mode ?? "-"}`;
    $("job-progress").style.width = Math.round((j.progress || 0) * 100) + "%";
    if (j.awaiting_approval && j.awaiting_approval.length) {
      state.awaitingNode = j.awaiting_approval[0];
      $("approval-node").textContent = state.awaitingNode;
      $("job-approval").classList.remove("hidden");
    } else {
      $("job-approval").classList.add("hidden");
    }
  } catch (e) { /* job may not exist yet */ }
}

async function loadJobsForCase() {
  try {
    const list = await api(`/api/cases/${encodeURIComponent(state.caseId)}/jobs`);
    if (!list.length) { $("job-status").textContent = "尚未启动任务"; return; }
    const last = list[list.length - 1];
    $("job-status").textContent =
      `最近任务 ${last.job_id} · ${last.status} · ${Math.round((last.progress || 0) * 100)}%`;
  } catch {}
}

/* ---------------- paper / ledger / upload ---------------- */
async function loadPaper() {
  if (!state.caseId) return;
  try {
    const p = await api(`/api/cases/${encodeURIComponent(state.caseId)}/paper`);
    state.paperMarkdown = p.markdown || "";
    const gate = $("gate-badge");
    gate.textContent = "gate: " + (p.consistency_gate ?? "-");
    gate.className = "badge " + (p.consistency_gate === "PASS" ? "badge-ok" :
      p.consistency_gate === "UNKNOWN" ? "badge-idle" : "badge-warn");
    $("paper-meta").textContent = p.source ? `来源: ${p.source}` : "论文尚未生成";
    $("paper-body").textContent = p.markdown || "（论文合并稿尚未生成）";

    // 论文统计信息
    renderPaperStats(p.markdown);

    // 质量门详情
    renderConsistencyDetail(p.consistency);
  } catch (e) { toast("加载论文失败: " + e.message, "err"); }
}

function renderPaperStats(markdown) {
  const statsEl = $("paper-stats");
  if (!markdown) {
    statsEl.classList.add("hidden");
    return;
  }
  statsEl.classList.remove("hidden");

  // 字数统计（中文字符 + 英文单词）
  const chineseChars = (markdown.match(/[\u4e00-\u9fa5]/g) || []).length;
  const englishWords = (markdown.match(/[a-zA-Z]+/g) || []).length;
  const totalWords = chineseChars + englishWords;
  $("paper-word-count").textContent = `字数: ${totalWords}`;

  // 章节数统计（以 # 开头的行）
  const chapters = (markdown.match(/^#{1,3}\s+.+$/gm) || []).length;
  $("paper-chapter-count").textContent = `章节数: ${chapters}`;

  // 生成时间
  const now = new Date();
  $("paper-gen-time").textContent = `加载时间: ${now.toLocaleString("zh-CN")}`;
}

function renderConsistencyDetail(consistency) {
  const detailEl = $("consistency-detail");
  const violationsEl = $("consistency-violations");
  const statusEl = $("consistency-gate-status");

  if (!consistency || consistency.gate === "UNKNOWN") {
    detailEl.classList.add("hidden");
    return;
  }

  detailEl.classList.remove("hidden");
  statusEl.textContent = "gate: " + (consistency.gate || "-");
  statusEl.className = "badge " + (consistency.gate === "PASS" ? "badge-ok" : "badge-warn");

  const violations = consistency.violations || [];
  if (!violations.length) {
    violationsEl.innerHTML = '<p class="meta">未发现违规项</p>';
    return;
  }

  violationsEl.innerHTML = violations.map((v, i) => {
    const type = v.type || v.rule || "unknown";
    const chapter = v.chapter || v.section || v.location || "";
    const desc = v.message || v.description || v.detail || JSON.stringify(v);
    return `<div class="violation-item" data-idx="${i}">
      <div class="violation-type">${esc(type)}</div>
      ${chapter ? `<div class="violation-chapter">命中章节: ${esc(chapter)}</div>` : ""}
      <div class="violation-desc">${esc(desc)}</div>
    </div>`;
  }).join("");

  // 点击跳转到论文对应位置
  violationsEl.querySelectorAll(".violation-item").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.idx, 10);
      const v = violations[idx];
      const chapter = v?.chapter || v?.section;
      if (chapter) scrollToChapter(chapter);
    });
  });
}

function scrollToChapter(chapterName) {
  const paperBody = $("paper-body");
  const text = paperBody.textContent;
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(chapterName)) {
      // 计算滚动位置（粗略）
      const lineHeight = 20; // approx
      paperBody.scrollTop = i * lineHeight;
      toast(`跳转到: ${chapterName}`, "ok");
      return;
    }
  }
  toast(`未找到章节: ${chapterName}`, "err");
}

async function loadLedger() {
  if (!state.caseId) return;
  try {
    const l = await api(`/api/cases/${encodeURIComponent(state.caseId)}/ledger`);
    const s = l.summary;
    $("ledger-summary").textContent =
      `总计 ${s.total} · AI 调用 ${s.ai_calls} · 采纳 ${s.adopted} · 人工复核 ${s.human_reviewed}`;
    renderTable("ledger-table", l.entries.slice().reverse(),
      ["timestamp", "tool", "model", "stage", "purpose", "used_ai", "human_reviewed", "entry_id"]);
  } catch (e) { /* case without ledger yet */ }
}

async function doUpload() {
  const f = $("upload-file").files[0];
  if (!f) { toast("请先选择文件", "err"); return; }
  if (!state.caseId) { toast("请先选择 Case", "err"); return; }
  const fd = new FormData();
  fd.append("case_id", state.caseId);
  fd.append("kind", "input");
  fd.append("file", f);
  try {
    const r = await api("/api/upload", { method: "POST", body: fd });
    $("upload-result").textContent = "已注册 artifact_id=" + (r.artifact?.artifact_id ?? "?");
    toast("上传并注册成功", "ok");
    loadCase(); loadLedger();
  } catch (e) { toast("上传失败: " + e.message, "err"); }
}

/* ---------------- wiring ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  loadHealth();
  loadCases().catch((e) => toast("加载 Case 列表失败: " + e.message, "err"));

  $("case-select").addEventListener("change", (e) => {
    state.caseId = e.target.value;
    loadCase(); loadPaper(); loadLedger();
  });
  $("refresh-cases").addEventListener("click", () => loadCases());
  $("chat-send").addEventListener("click", sendChat);
  $("chat-message").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendChat();
  });
  $("job-start").addEventListener("click", startJob);
  $("approval-go").addEventListener("click", () => {
    if (state.awaitingNode) approveNode(state.awaitingNode, $("approval-note").value);
  });
  $("upload-go").addEventListener("click", doUpload);

  $("paper-download").addEventListener("click", () => {
    if (!state.paperMarkdown) { toast("尚无论文内容", "err"); return; }
    const blob = new Blob([state.paperMarkdown], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${state.caseId}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  });

  $("paper-export").addEventListener("click", async () => {
    if (!state.caseId) return;
    try {
      await jpost(`/api/cases/${encodeURIComponent(state.caseId)}/export`, { profile: "SM" });
      toast("投稿包已生成", "ok");
      loadLedger();
    } catch (e) { toast("导出失败: " + e.message, "err"); }
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      $("panel-" + tab.dataset.tab).classList.add("active");
      if (tab.dataset.tab === "paper") loadPaper();
      if (tab.dataset.tab === "ledger") loadLedger();
    });
  });
});
