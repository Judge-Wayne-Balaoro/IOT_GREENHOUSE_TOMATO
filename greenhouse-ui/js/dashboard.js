if (!Auth.require()) throw new Error("redirecting to login");

const $ = s => document.querySelector(s);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const me = Auth.user();
$("#who").textContent = me ? (me.name || me.username) : "";
$("#logout").onclick = () => Auth.logout();
$("#themeBtn").onclick = toggleTheme;

const ICON = {
  pump: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  fan: '<circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7 2 0 2 3 0 5l-3 3M14 12c4 0 7 1 7 4 0 2-3 2-5 0l-3-3M12 14c0 4-1 7-4 7-2 0-2-3 0-5l3-3M10 12c-4 0-7-1-7-4 0-2 3-2 5 0l3 3"/>',
  grow: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>'
};
const DEVS = [["pump_status", "pump", "Water pump"], ["fan_status", "fan", "Exhaust fan"], ["grow_light_status", "grow", "Grow light"]];
$("#devices").innerHTML = DEVS.map(([f, k, n]) =>
  `<div class="panel dev" id="d-${f}"><div class="ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg></div><div><b>${n}</b><span class="pill">--</span></div></div>`).join("");

const MAXH = 40;
$("#ruler").insertAdjacentHTML("beforeend", [0, 10, 20, 30, 40].map(v =>
  `<span style="bottom:${v / MAXH * 100}%"></span><em style="bottom:${v / MAXH * 100}%">${v}</em>`).join(""));
const safe = v => v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? "--" : v;
function setNum(selector, value) { const node = $(selector); if (node && node.firstChild) node.firstChild.nodeValue = String(safe(value)); }
const bar = (id, pct) => { const v = Number(pct); $("#" + id).style.width = (Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : 0) + "%"; };
function render(d) {
  d = d || {};
  setNum("#v-temp", d.temperature); setNum("#v-hum", d.humidity); setNum("#v-soil", d.soil_moisture); setNum("#v-height", d.plant_height);
  const lightNode = $("#v-light");
  const lightKnown = d.light_level !== null && d.light_level !== undefined && d.light_level !== "";
  const isDark = lightKnown && Number(d.light_level) === 1;
  lightNode.textContent = !lightKnown ? "—" : (isDark ? "Dark" : "Bright");
  lightNode.classList.toggle("is-dark", isDark);
  lightNode.classList.toggle("is-bright", lightKnown && !isDark);
  bar("b-temp", d.temperature == null ? 0 : (d.temperature - 10) / 30 * 100);
  bar("b-hum", d.humidity); bar("b-soil", d.soil_moisture);
  $("#plant").style.height = (d.plant_height == null ? 0 : Math.max(0, Math.min(100, Number(d.plant_height) / MAXH * 100))) + "%";
  DEVS.forEach(([f]) => {
    const el = $("#d-" + f), known = d[f] !== null && d[f] !== undefined, on = known && !!d[f];
    el.classList.toggle("on", on); el.querySelector(".pill").textContent = !known ? "N/A" : (on ? "ON" : "OFF");
  });
  const stamp = d.timestamp ? new Date(d.timestamp) : null;
  $("#updated").textContent = stamp && Number.isFinite(stamp.getTime()) ? stamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "No readings yet";
}
function renderWifi(connected) {
  $("#wifiDot").className = "dot " + (connected ? "on" : "off");
  $("#wifiTxt").textContent = "Wi-Fi: " + (connected ? "Connected" : "Disconnected");
}
function showError(msg) { const b = $("#banner"); b.hidden = !msg; b.textContent = msg || ""; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

const METRICS = [
  ["temperature", "Temperature (°C)", "--c-temp"],
  ["humidity", "Humidity (%)", "--c-hum"],
  ["soil_moisture", "Soil moisture (%)", "--c-soil"],
  ["light_level", "Light condition", "--c-light"],
  ["plant_height", "Official plant height (cm)", "--c-height"]
];
$("#charts").innerHTML = METRICS.map(([k, t]) =>
  `<div class="panel chart${k === "plant_height" ? " wide" : ""}"><h3>${t}</h3><canvas id="c-${k}" role="img" aria-label="${t} over time"></canvas></div>`).join("");
const charts = {};
let hours = 24, hist = [], officialGrowth = [], ultrasonicRows = [];
function label(ts) {
  const d = new Date(ts);
  return hours > 24 ? d.toLocaleDateString([], { month: "short", day: "numeric" }) : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function chartRange() { const end = new Date(); return { start: new Date(end.getTime() - hours * 3600000), end }; }
function drawCharts() {
  const step = Math.max(1, Math.floor(hist.length / 150));
  const sampled = hist.filter((_, i) => i % step === 0);
  METRICS.forEach(([key, title, colorName]) => {
    let data, values;
    if (key === "plant_height") {
      // Manual ruler measurements are sparse, so show the whole monitoring history
      // regardless of the environmental chart's 6 h / 24 h / 7 day filter.
      data = officialGrowth;
      values = data.map(p => p.height_cm);
    } else {
      data = sampled;
      values = data.map(p => p[key]);
    }
    const color = css(colorName), isLightCondition = key === "light_level";
    if (charts[key]) charts[key].destroy();
    charts[key] = new Chart($("#c-" + key), {
      type: "line",
      data: { labels: data.map(p => key === "plant_height" ? new Date(p.timestamp).toLocaleDateString([], { month: "short", day: "numeric" }) : label(p.timestamp)), datasets: [{ data: values, borderColor: color, backgroundColor: color + "22", fill: !isLightCondition, pointRadius: (key === "plant_height" || isLightCondition) ? 3 : 0, borderWidth: 2, tension: .25, stepped: (key === "plant_height" || isLightCondition) ? "before" : false }] },
      options: { maintainAspectRatio: false, animation: false, plugins: { legend: { display: false }, tooltip: { callbacks: isLightCondition ? { label: context => "Light condition: " + (Number(context.raw) === 1 ? "Dark" : "Bright") } : {} } }, interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { color: css("--muted"), maxTicksLimit: 6, maxRotation: 0 }, grid: { display: false } }, y: isLightCondition ? { min: 0, max: 1, ticks: { stepSize: 1, color: css("--muted"), callback: value => Number(value) === 1 ? "Dark" : "Bright" }, grid: { color: css("--line") } } : { ticks: { color: css("--muted") }, grid: { color: css("--line") }, beginAtZero: key === "plant_height" } } }
    });
  });
}
function onCell(v) { return v == null ? "<td>—</td>" : (v ? '<td class="s-on">ON</td>' : "<td>OFF</td>"); }
function lightCell(v) {
  if (v === null || v === undefined || v === "") return "<td>—</td>";
  const dark = Number(v) === 1;
  return `<td><span class="light-pill ${dark ? "is-dark" : "is-bright"}"><span class="condition-dot"></span>${dark ? "Dark" : "Bright"}</span></td>`;
}
function drawTable() {
  // Always show the newest 10 actual readings. Don't downsample the history table;
  // downsampling is only useful for chart rendering and can hide the latest rows.
  const rows = [...hist]
    .filter(p => p.timestamp && Number.isFinite(new Date(p.timestamp).getTime()))
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, 10);
  const fmt = t => new Date(t).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  $("#rows").innerHTML = rows.length ? rows.map(p =>
    `<tr><td>${fmt(p.timestamp)}</td><td>${safe(p.temperature)}</td><td>${safe(p.humidity)}</td><td>${safe(p.soil_moisture)}</td>${lightCell(p.light_level)}<td>${safe(p.plant_height)}</td>${onCell(p.pump_status)}${onCell(p.fan_status)}${onCell(p.grow_light_status)}</tr>`).join("") : '<tr><td colspan="9" class="sub">No environmental readings in this period.</td></tr>';
}
function renderGrowthTable() {
  const rows = [...officialGrowth].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 10);
  const fmt = t => new Date(t).toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  $("#manualGrowthRows").innerHTML = rows.length ? rows.map(r => `<tr><td>${fmt(r.timestamp)}</td><td>${Number(r.height_cm).toFixed(1)}</td><td>Ruler</td><td>${escapeHtml(r.notes || "") || "—"}</td></tr>`).join("") : '<tr><td colspan="4" class="sub">No ruler measurements recorded yet.</td></tr>';
}
function renderUltrasonicTable() {
  const rows = ultrasonicRows.slice(0, 12);
  const fmt = t => new Date(t).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  $("#ultrasonicRows").innerHTML = rows.length ? rows.map(r => `<tr><td>${fmt(r.recorded_at)}</td><td>${safe(r.distance_cm)}</td><td>${safe(r.estimated_height_cm)}</td><td>Experimental — not official</td></tr>`).join("") : '<tr><td colspan="4" class="sub">No ultrasonic test records received yet. The ESP32 firmware must use /api/ultrasonic-tests.</td></tr>';
}
async function loadHistory() {
  try {
    const range = chartRange();
    const [env, growth, ultrasonics] = await Promise.all([
      Api.history(hours), Api.growthHistory(null, null), Api.ultrasonicTests(null, null)
    ]);
    hist = env; officialGrowth = growth; ultrasonicRows = ultrasonics;
    drawCharts(); drawTable(); renderGrowthTable(); renderUltrasonicTable(); showError("");
  } catch (e) { showError(e.message); }
}
$("#range").addEventListener("click", e => {
  const button = e.target.closest("button"); if (!button) return;
  hours = +button.dataset.r;
  document.querySelectorAll("#range button").forEach(x => x.setAttribute("aria-pressed", x === button));
  loadHistory();
});

/* ---------- Official ruler measurement form ---------- */
function localDateValue(date = new Date()) {
  return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
}
const heightDate = $("#heightDate");
heightDate.max = localDateValue();
heightDate.value = localDateValue();
$("#growthForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("#saveHeight"), status = $("#growthFormStatus");
  status.textContent = ""; status.classList.remove("error-text");
  const height = Number($("#heightCm").value);
  const dateValue = heightDate.value;
  if (!Number.isFinite(height) || height <= 0 || height > 300) { status.textContent = "Enter a height greater than 0 and no more than 300 cm."; status.classList.add("error-text"); return; }
  if (!dateValue || dateValue > localDateValue()) { status.textContent = "Choose a valid measurement date (today or earlier)."; status.classList.add("error-text"); return; }
  const stamp = new Date(dateValue + "T12:00:00").toISOString();
  button.disabled = true; button.textContent = "Saving…";
  try {
    await Api.saveManualHeight({ recorded_at: stamp, height_cm: height, notes: $("#heightNotes").value.trim() });
    status.textContent = "Ruler measurement saved to PostgreSQL.";
    $("#heightCm").value = ""; $("#heightNotes").value = "";
    await tick(); await loadHistory();
  } catch (error) { status.textContent = error.message; status.classList.add("error-text"); }
  finally { button.disabled = false; button.textContent = "Save ruler measurement"; }
});

/* ---------- Excel export ---------- */
const exportPeriod = $("#exportPeriod"), exportFormat = $("#exportFormat"), exportStatus = $("#exportStatus");
function setExportStatus(message, isError = false) { exportStatus.textContent = message; exportStatus.classList.toggle("error-text", isError); }
function toggleExportDateFields() {
  const period = exportPeriod.value;
  $("#exportDayField").hidden = period !== "day";
  $("#exportCustomFields").hidden = period !== "custom";
}
exportPeriod.addEventListener("change", toggleExportDateFields); toggleExportDateFields();
const todayValue = localDateValue();
$("#exportDay").value = todayValue; $("#exportDay").max = todayValue;
$("#exportTo").value = todayValue; $("#exportTo").max = todayValue;
const sevenDaysPrior = new Date(); sevenDaysPrior.setDate(sevenDaysPrior.getDate() - 7);
$("#exportFrom").value = localDateValue(sevenDaysPrior); $("#exportFrom").max = todayValue; $("#exportTo").min = $("#exportFrom").value;
$("#exportFrom").addEventListener("change", () => {
  const from = $("#exportFrom").value; $("#exportTo").min = from || "";
  if (from && $("#exportTo").value && $("#exportTo").value < from) $("#exportTo").value = from;
});
$("#exportTo").addEventListener("change", () => { $("#exportFrom").max = $("#exportTo").value || todayValue; });
function dateStart(value) { if (!value) return null; const [y, m, d] = value.split("-").map(Number); return new Date(y, m - 1, d, 0, 0, 0, 0); }
function dateEnd(value) { const d = dateStart(value); if (d) d.setHours(23, 59, 59, 999); return d; }
function getExportRange() {
  const now = new Date(), period = exportPeriod.value;
  if (period === "today") { const start = new Date(now); start.setHours(0, 0, 0, 0); return { start, end: now, label: "today" }; }
  if (period === "day") { const value = $("#exportDay").value, start = dateStart(value), end = dateEnd(value); if (!start || !end) throw new Error("Choose a valid date."); return { start, end, label: value }; }
  if (period === "week" || period === "month") { const start = new Date(now); start.setDate(start.getDate() - (period === "week" ? 7 : 30)); return { start, end: now, label: period === "week" ? "last_7_days" : "last_30_days" }; }
  if (period === "custom") { const from = $("#exportFrom").value, to = $("#exportTo").value, start = dateStart(from), end = dateEnd(to); if (!start || !end) throw new Error("Choose both a start date and an end date."); if (start > end) throw new Error("The start date must be on or before the end date."); return { start, end, label: from + "_to_" + to }; }
  return { start: null, end: now, label: "all_available_data" };
}
const EXPORT_METRICS = [["temperature", "Temperature (°C)"], ["humidity", "Humidity (%)"], ["soil_moisture", "Soil Moisture (%)"]];
const EXPORT_STATES = [["pump_status", "Pump"], ["fan_status", "Exhaust Fan"], ["grow_light_status", "Grow Light"]];
function toRawSheetRows(rows) { return rows.map(p => ({
  "Timestamp": p.timestamp ? new Date(p.timestamp).toLocaleString() : "", "Temperature (°C)": p.temperature ?? "",
  "Humidity (%)": p.humidity ?? "", "Soil Moisture (%)": p.soil_moisture ?? "", "Light Condition": p.light_level == null ? "" : (Number(p.light_level) === 1 ? "Dark" : "Bright"),
  "Official Plant Height (cm)": p.plant_height ?? "", "Pump": p.pump_status == null ? "" : (p.pump_status ? "ON" : "OFF"),
  "Exhaust Fan": p.fan_status == null ? "" : (p.fan_status ? "ON" : "OFF"), "Grow Light": p.grow_light_status == null ? "" : (p.grow_light_status ? "ON" : "OFF")
})); }
function dayKey(date) { return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0"); }
function weekStart(date) { const d = new Date(date); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d; }
function buildSummaryRows(rows, interval) {
  const groups = new Map();
  for (const r of rows) {
    const t = new Date(r.timestamp); if (!Number.isFinite(t.getTime())) continue;
    const start = interval === "day" ? new Date(t.getFullYear(), t.getMonth(), t.getDate()) : weekStart(t);
    const key = dayKey(start); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(r);
  }
  return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([key, group]) => {
    const result = { [interval === "day" ? "Date" : "Week Starting (Monday)"]: key, "Recorded Readings": group.length };
    for (const [field, title] of EXPORT_METRICS) {
      const values = group.map(r => r[field]).filter(v => v !== null && v !== undefined && v !== "").map(Number).filter(Number.isFinite);
      result[title + " Average"] = values.length ? +(values.reduce((s, n) => s + n, 0) / values.length).toFixed(2) : "";
      result[title + " Minimum"] = values.length ? +Math.min(...values).toFixed(2) : "";
      result[title + " Maximum"] = values.length ? +Math.max(...values).toFixed(2) : "";
    }
    for (const [field, title] of EXPORT_STATES) { const v = group.map(r => r[field]).filter(x => x !== null && x !== undefined); result[title + " ON Readings"] = v.filter(Boolean).length; result[title + " ON (%)"] = v.length ? +v.filter(Boolean).length / v.length * 100 : ""; }
    // Digital light is categorical, so don't calculate meaningless numeric averages.
    const light = group.map(r => r.light_level).filter(v => v !== null && v !== undefined);
    const darkCount = light.filter(v => Number(v) === 1).length;
    const brightCount = light.length - darkCount;
    result["Bright Light Readings"] = brightCount;
    result["Dark Light Readings"] = darkCount;
    result["Bright Readings (%)"] = light.length ? +(brightCount / light.length * 100).toFixed(2) : "";
    result["Dark Readings (%)"] = light.length ? +(darkCount / light.length * 100).toFixed(2) : "";
    return result;
  });
}
function growthSheetRows(rows) { return rows.map(r => ({ "Measurement Date": new Date(r.timestamp).toLocaleString(), "Height (cm)": r.height_cm, "Method": "Ruler", "Notes": r.notes || "" })); }
function growthSummaryRows(rows, interval) {
  const groups = new Map();
  for (const r of rows) { const t = new Date(r.timestamp); if (!Number.isFinite(t.getTime())) continue; const s = interval === "day" ? new Date(t.getFullYear(), t.getMonth(), t.getDate()) : weekStart(t); const k = dayKey(s); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(r); }
  return [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([key,g])=>{g.sort((a,b)=>new Date(a.timestamp)-new Date(b.timestamp)); return { [interval === "day" ? "Date" : "Week Starting (Monday)"]:key, "Measurements":g.length, "First Height (cm)":g[0].height_cm, "Latest Height (cm)":g[g.length-1].height_cm, "Change (cm)":+(g[g.length-1].height_cm-g[0].height_cm).toFixed(2) };});
}
function appendSheet(book, name, rows, note) {
  const safeRows = rows.length ? rows : [{ Note: note || "No data available for this period." }];
  const ws = XLSX.utils.json_to_sheet(safeRows); const keys = Object.keys(safeRows[0] || {}); ws["!cols"] = keys.map(k => ({ wch: Math.min(34, Math.max(14, k.length + 2)) })); XLSX.utils.book_append_sheet(book, ws, name);
}
async function exportReadingsToExcel() {
  const button = $("#exportExcel");
  if (!window.XLSX) { setExportStatus("Excel workbook library failed to load. Check internet access and retry.", true); return; }
  button.disabled = true; button.textContent = "Preparing workbook…";
  try {
    const range = getExportRange();
    setExportStatus("Loading real database records for " + range.label.replaceAll("_", " ") + "…");
    const [rows, rulerRows, tests] = await Promise.all([
      Api.exportHistory(range.start, range.end),
      Api.growthHistory(range.start, range.end),
      Api.ultrasonicTests(range.start, range.end)
    ]);
    if (!rows.length && !rulerRows.length && !tests.length) { setExportStatus("No records were found for this period. Try another date range.", true); return; }
    const book = XLSX.utils.book_new(), format = exportFormat.value;
    if (format === "raw" || format === "both") appendSheet(book, "Sensor Readings", toRawSheetRows(rows), "No environmental readings for this period.");
    if (format === "daily" || format === "both") appendSheet(book, "Daily Summary", buildSummaryRows(rows, "day"), "No environmental readings for this period.");
    if (format === "weekly" || format === "both") appendSheet(book, "Weekly Summary", buildSummaryRows(rows, "week"), "No environmental readings for this period.");
    // Ruler and ultrasonic observations always remain in separate sheets from environmental readings.
    appendSheet(book, "Official Plant Growth", growthSheetRows(rulerRows), "No ruler-measured plant-height records for this period.");
    if (format === "daily" || format === "both") appendSheet(book, "Daily Growth Summary", growthSummaryRows(rulerRows, "day"), "No ruler measurements for this period.");
    if (format === "weekly" || format === "both") appendSheet(book, "Weekly Growth Summary", growthSummaryRows(rulerRows, "week"), "No ruler measurements for this period.");
    appendSheet(book, "Ultrasonic Tests", tests.map(r => ({ "Timestamp": new Date(r.recorded_at).toLocaleString(), "Distance (cm)": r.distance_cm ?? "", "Estimated Height (cm)": r.estimated_height_cm ?? "", "Classification": "Experimental — not official plant height" })), "No ultrasonic test records for this period.");
    XLSX.writeFile(book, `tomato_greenhouse_${range.label}_${new Date().toISOString().slice(0, 10)}.xlsx`);
    setExportStatus(`Exported ${rows.length} environmental readings, ${rulerRows.length} ruler measurements, and ${tests.length} experimental ultrasonic records.`);
  } catch (e) { setExportStatus(e.message || "Export failed. Please try again.", true); }
  finally { button.disabled = false; button.innerHTML = '<span aria-hidden="true">↓</span> Export to Excel <span class="file-extension">.xlsx</span>'; }
}
$("#exportExcel").addEventListener("click", exportReadingsToExcel);

async function tick() {
  try { render(await Api.latest()); const status = await Api.deviceStatus(); renderWifi(status.wifi_connected); showError(""); }
  catch (e) { renderWifi(false); showError(e.message); }
}
tick(); loadHistory();
setInterval(tick, CONFIG.REFRESH_MS);
setInterval(loadHistory, 30000);
