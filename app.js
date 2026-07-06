const DEFAULT_STATE = {
  service: "esign",
  clientCode: "ALL",
  fromDate: "2026-06-10",
  toDate: "2026-06-10",
  searchText: ""
};

const SERVICE_LABELS = {
  esign: "ESIGN_SERVICE",
  location: "VERI5_LOCATION"
};

const TILE_DEFS = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "monthToDate", label: "Month to date" },
  { key: "lastMonth", label: "Last month" }
];

const state = { ...DEFAULT_STATE };

const elements = {
  serviceSelect: document.getElementById("serviceSelect"),
  pageTitle: document.getElementById("pageTitle"),
  scopeServiceBadge: document.getElementById("scopeServiceBadge"),
  failureReasonsSection: document.getElementById("failureReasonsSection"),
  clientSelect: document.getElementById("clientSelect"),
  searchInput: document.getElementById("searchInput"),
  fromDate: document.getElementById("fromDate"),
  toDate: document.getElementById("toDate"),
  scopeLabel: document.getElementById("scopeLabel"),
  scopeDateLabel: document.getElementById("scopeDateLabel"),
  validationMsg: document.getElementById("validationMsg"),
  statusGrid: document.getElementById("statusGrid"),
  tilesGrid: document.getElementById("tilesGrid"),
  trendChart: document.getElementById("trendChart"),
  tableWrap: document.getElementById("tableWrap"),
  failureReasonsWrap: document.getElementById("failureReasonsWrap"),
  lastUpdated: document.getElementById("lastUpdated"),
  liveStatus: document.getElementById("liveStatus"),
  runBtn: document.getElementById("runBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  resetBtn: document.getElementById("resetBtn"),
  downloadBtn: document.getElementById("downloadBtn")
};

const stateCache = {
  clients: [],
  rows: [],
  summary: { successCount: 0, failureCount: 0, totalCount: 0 },
  tiles: { today: 0, yesterday: 0, monthToDate: 0, lastMonth: 0 },
  trend: [],
  failureReasons: [],
  loading: false
};

function setup() {
  bindEvents();
  syncInputs();
  initializeApp();
}

async function initializeApp() {
  setLoading(true);
  try {
    await loadClientOptions();
    updateConnectionUi(true);
    await render(true);
  } catch (error) {
    console.error(error);
    updateConnectionUi(false);
    renderBackendUnavailable(error);
  } finally {
    setLoading(false);
  }
}

async function loadClientOptions() {
  const response = await fetch("/api/clients");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Unable to load client codes.");
  }
  stateCache.clients = payload.clients || [];
  populateClientOptions();
}

function populateClientOptions() {
  const options = ['<option value="ALL">All client codes</option>']
    .concat(stateCache.clients.map((clientCode) => `<option value="${clientCode}">${clientCode}</option>`));
  elements.clientSelect.innerHTML = options.join("");
  elements.clientSelect.value = state.clientCode;
}

function bindEvents() {
  elements.serviceSelect.addEventListener("change", async (event) => {
    state.service = event.target.value;
    updateScope();
    await runDashboardQuery(true);
  });

  elements.clientSelect.addEventListener("change", (event) => {
    state.clientCode = event.target.value;
    state.searchText = state.clientCode === "ALL" ? "" : state.clientCode;
    syncInputs();
  });

  elements.searchInput.addEventListener("input", (event) => {
    state.searchText = event.target.value.trim().toUpperCase();
    if (!state.searchText) {
      state.clientCode = "ALL";
    } else {
      const exactMatch = stateCache.clients.find((clientCode) => clientCode === state.searchText);
      state.clientCode = exactMatch || "ALL";
    }
    elements.clientSelect.value = state.clientCode;
  });

  elements.fromDate.addEventListener("change", (event) => {
    state.fromDate = event.target.value;
    updateScope();
    validateDateRange();
  });

  elements.toDate.addEventListener("change", (event) => {
    state.toDate = event.target.value;
    updateScope();
    validateDateRange();
  });

  elements.runBtn.addEventListener("click", async () => {
    await runDashboardQuery(true);
  });

  elements.refreshBtn.addEventListener("click", async () => {
    await runDashboardQuery(true);
  });

  elements.resetBtn.addEventListener("click", () => {
    Object.assign(state, DEFAULT_STATE);
    syncInputs();
    updateScope();
    validateDateRange();
    runDashboardQuery(true);
  });

  elements.downloadBtn.addEventListener("click", downloadCsv);
}

function syncInputs() {
  elements.serviceSelect.value = state.service;
  elements.clientSelect.value = state.clientCode;
  elements.searchInput.value = state.searchText;
  elements.fromDate.value = state.fromDate;
  elements.toDate.value = state.toDate;
}

async function render(updateTimestamp = false) {
  const hasValidRange = validateDateRange();
  updateScope();
  if (!hasValidRange) {
    renderValidationState();
    return;
  }

  await fetchDashboardData();
  renderStatusCards(stateCache.summary);
  renderTiles(stateCache.tiles);
  renderTrendChart(stateCache.trend);
  renderTable(stateCache.rows);
  renderFailureReasons(stateCache.failureReasons);

  if (updateTimestamp || !elements.lastUpdated.dataset.ready) {
    elements.lastUpdated.textContent = `Updated at ${formatTime(new Date())}`;
    elements.lastUpdated.dataset.ready = "true";
  }
}

function validateDateRange() {
  const hasValidRange = state.fromDate <= state.toDate;
  elements.validationMsg.hidden = hasValidRange;
  return hasValidRange;
}

function renderValidationState() {
  const emptySummary = { successCount: 0, failureCount: 0, totalCount: 0 };
  renderStatusCards(emptySummary);
  renderTiles({ today: 0, yesterday: 0, monthToDate: 0, lastMonth: 0 });
  renderTrendChart([]);
  renderTable([]);
  renderFailureReasons([]);
}

function renderBackendUnavailable(error) {
  const emptySummary = { successCount: 0, failureCount: 0, totalCount: 0 };
  renderStatusCards(emptySummary);
  renderTiles({ today: 0, yesterday: 0, monthToDate: 0, lastMonth: 0 });
  renderTrendChart([]);
  elements.tableWrap.innerHTML = `<div class="table-card"><div class="row-empty">${escapeHtml(error?.message || "Backend unavailable. Start with python server.py.")}</div></div>`;
  renderFailureReasons([]);
}

async function runDashboardQuery(updateTimestamp = false) {
  const hasValidRange = validateDateRange();
  updateScope();
  if (!hasValidRange) {
    renderValidationState();
    return;
  }
  if (!stateCache.clients.length) {
    renderBackendUnavailable(new Error("Backend unavailable. Start with python server.py."));
    return;
  }
  await render(updateTimestamp);
}

async function fetchDashboardData() {
  stateCache.loading = true;
  setLoading(true);
  const params = new URLSearchParams({
    service: state.service,
    from: state.fromDate,
    to: state.toDate,
    clientCode: state.clientCode
  });
  try {
    const response = await fetch(`/api/dashboard?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to fetch dashboard data");
    }
    stateCache.rows = payload.clients || [];
    stateCache.summary = payload.summary || stateCache.summary;
    stateCache.tiles = payload.tiles || stateCache.tiles;
    stateCache.trend = payload.trend || [];
    stateCache.failureReasons = payload.failureReasons || [];
  } catch (error) {
    console.error(error);
    stateCache.rows = [];
    stateCache.summary = { successCount: 0, failureCount: 0, totalCount: 0 };
    stateCache.tiles = { today: 0, yesterday: 0, monthToDate: 0, lastMonth: 0 };
    stateCache.trend = [];
    stateCache.failureReasons = [];
    updateConnectionUi(false);
    elements.tableWrap.innerHTML = `<div class="table-card"><div class="row-empty">${escapeHtml(error.message || "Backend unavailable. Start with python server.py.")}</div></div>`;
  } finally {
    stateCache.loading = false;
    setLoading(false);
  }
}

function updateConnectionUi(isAvailable) {
  elements.liveStatus.innerHTML = isAvailable
    ? '<span class="live-dot"></span>Live backend'
    : '<span class="live-dot"></span>Backend required';
  elements.runBtn.disabled = !isAvailable || stateCache.loading;
  elements.refreshBtn.disabled = !isAvailable || stateCache.loading;
  elements.downloadBtn.disabled = !isAvailable || stateCache.loading;
}

function setLoading(isLoading) {
  stateCache.loading = isLoading;
  elements.runBtn.disabled = isLoading || !stateCache.clients.length;
  elements.refreshBtn.disabled = isLoading || !stateCache.clients.length;
  elements.downloadBtn.disabled = isLoading || !stateCache.clients.length;
  elements.resetBtn.disabled = isLoading;
}

function updateScope() {
  const label = state.clientCode === "ALL" ? "All client codes" : state.clientCode;
  elements.scopeLabel.textContent = label;
  elements.scopeDateLabel.textContent = `${state.fromDate} to ${state.toDate}`;

  const serviceLabel = SERVICE_LABELS[state.service] || state.service;
  elements.scopeServiceBadge.textContent = serviceLabel;
  elements.pageTitle.textContent = `${serviceLabel} transaction monitoring`;
  elements.failureReasonsSection.style.display = state.service === "esign" ? "" : "none";
}

function renderStatusCards(summary) {
  const cards = [
    { cls: "success", label: "Success", value: summary.successCount, pct: percentage(summary.successCount, summary.totalCount) },
    { cls: "failure", label: "Failure", value: summary.failureCount, pct: percentage(summary.failureCount, summary.totalCount) },
    { cls: "total", label: "Total", value: summary.totalCount, pct: "Query result" }
  ];

  elements.statusGrid.innerHTML = cards.map((card) => `
    <article class="metric-card status ${card.cls}">
      <div class="metric-label">${card.label}</div>
      <div class="metric-value">${formatNumber(card.value)}</div>
      <div class="metric-subtext">${typeof card.pct === "string" ? card.pct : `${card.pct}% of total`}</div>
    </article>
  `).join("");
}

function renderTiles(tiles) {
  elements.tilesGrid.innerHTML = TILE_DEFS.map((tile) => `
    <article class="metric-card tile">
      <div class="metric-label">${tile.label}</div>
      <div class="metric-value">${formatNumber(tiles[tile.key] || 0)}</div>
      <div class="metric-subtext">Live aggregate from database</div>
    </article>
  `).join("");
}

function renderTrendChart(data) {
  if (!data.length) {
    elements.trendChart.innerHTML = `
      <rect x="0" y="0" width="760" height="280" rx="18" fill="#ffffff"></rect>
      <text x="380" y="145" text-anchor="middle" fill="#8b98ab" font-size="14">No trend data available for the current filter</text>
    `;
    return;
  }

  const width = 760;
  const height = 280;
  const padding = { top: 24, right: 20, bottom: 42, left: 42 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(...data.map((item) => item.totalCount), 1);
  const xStep = data.length === 1 ? 0 : innerWidth / (data.length - 1);

  const points = { success: [], failure: [], total: [] };
  data.forEach((item, index) => {
    const x = padding.left + (xStep * index);
    points.success.push([x, toY(item.successCount, maxValue, padding, innerHeight)]);
    points.failure.push([x, toY(item.failureCount, maxValue, padding, innerHeight)]);
    points.total.push([x, toY(item.totalCount, maxValue, padding, innerHeight)]);
  });

  const yGrid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const y = padding.top + innerHeight - (innerHeight * ratio);
    const value = Math.round(maxValue * ratio);
    return `
      <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#e5ebf2" stroke-dasharray="4 6"></line>
      <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" fill="#8b98ab" font-size="11">${value}</text>
    `;
  }).join("");

  const xLabels = data.map((item, index) => {
    const x = padding.left + (xStep * index);
    return `<text x="${x}" y="${height - 14}" text-anchor="middle" fill="#8b98ab" font-size="11">${escapeHtml(item.label)}</text>`;
  }).join("");

  elements.trendChart.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" rx="18" fill="#ffffff"></rect>
    ${yGrid}
    ${polyline(points.success, "#0f996c")}
    ${polyline(points.failure, "#df3655")}
    ${polyline(points.total, "#2f5cb8")}
    ${pointMarkers(points.total, "#2f5cb8")}
    ${xLabels}
  `;
}

function toY(value, maxValue, padding, innerHeight) {
  return padding.top + innerHeight - ((value / maxValue) * innerHeight);
}

function polyline(points, color) {
  return `<polyline fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${points.map(([x, y]) => `${x},${y}`).join(" ")}"></polyline>`;
}

function pointMarkers(points, color) {
  return points.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="3.5" fill="${color}"></circle>`).join("");
}

function renderTable(rows) {
  if (!rows.length) {
    if (!elements.tableWrap.innerHTML.includes("row-empty")) {
      elements.tableWrap.innerHTML = '<div class="table-card"><div class="row-empty">No client rows match the current filter.</div></div>';
    }
    return;
  }

  const tableRows = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.clientCode)}</td>
      <td class="num">${formatNumber(row.successCount)}</td>
      <td class="num">${formatNumber(row.failureCount)}</td>
      <td class="num">${formatNumber(row.totalCount)}</td>
    </tr>
  `).join("");

  elements.tableWrap.innerHTML = `
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>Client Code</th>
            <th class="num">Success Count</th>
            <th class="num">Failure Count</th>
            <th class="num">Total Count</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>
  `;
}

function renderFailureReasons(rows) {
  if (!elements.failureReasonsWrap) {
    return;
  }
  if (!rows.length) {
    elements.failureReasonsWrap.innerHTML = '<div class="table-card"><div class="row-empty">No failed transactions in the current filter.</div></div>';
    return;
  }

  const tableRows = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.reason)}</td>
      <td class="num">${formatNumber(row.count)}</td>
    </tr>
  `).join("");

  elements.failureReasonsWrap.innerHTML = `
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>Failure Reason</th>
            <th class="num">Count</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>
  `;
}

function downloadCsv() {
  if (state.fromDate > state.toDate || !stateCache.clients.length || stateCache.loading) {
    return;
  }
  const params = new URLSearchParams({
    service: state.service,
    from: state.fromDate,
    to: state.toDate,
    clientCode: state.clientCode
  });
  window.location.href = `/api/export.csv?${params.toString()}`;
}

function percentage(value, total) {
  if (!total) {
    return 0;
  }
  return Math.round((value / total) * 100);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function formatTime(date) {
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

setup();
