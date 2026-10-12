/* Dashboard client: polls the FastAPI backend (no build step, no external libs). */
const $ = (s) => document.querySelector(s);
const DEVICE = "cam01";
const SMOKE_MAX = 1000, SMOKE_WARN = 600, TEMP_MAX = 80, TEMP_WARN = 45;
let lastState = "NORMAL", estopOn = false;

// ---------------------------------------------------------------- tabs
document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#tab-" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "history") loadHistory();
    if (b.dataset.tab === "devices") loadDevices();
  })
);

// ---------------------------------------------------------------- helpers
const fmtTime = (t) => (t ? new Date(t * 1000).toLocaleTimeString() : "–");
const fmtDate = (t) => (t ? new Date(t * 1000).toLocaleString() : "–");
const ago = (t) => (t ? Math.max(0, Math.round(Date.now() / 1000 - t)) + "s ago" : "never");
const dur = (a, b) => (a ? Math.round((b || Date.now() / 1000) - a) + "s" : "–");
async function api(path, opts) {
  const r = await fetch(path, { cache: "no-store", ...opts });
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}
function setState(el, st) {
  el.className = el.className.replace(/\b(NORMAL|WARNING|CONFIRMED|RECOVERY|SENSOR_WARNING)\b/g, "").trim() + " " + st;
  el.textContent = st.replace("_", " ");
}

// ---------------------------------------------------------------- alarm sound (browser-side buzzer)
let audioCtx = null, alarmTimer = null;
function beep() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = "square"; o.frequency.value = 880; g.gain.value = 0.05;
    o.connect(g); g.connect(audioCtx.destination); o.start(); o.stop(audioCtx.currentTime + 0.25);
  } catch (e) { /* autoplay blocked until user interacts */ }
}
function alarm(on) {
  if (on && !alarmTimer) alarmTimer = setInterval(beep, 600);
  if (!on && alarmTimer) { clearInterval(alarmTimer); alarmTimer = null; }
}

// ---------------------------------------------------------------- status loop (1 s)
async function pollStatus() {
  try {
    const s = await api("/status");
    $("#backend-dot").classList.add("on");
    setState($("#overall"), s.overall_state);
    setState($("#state-big"), s.overall_state);
    const d = (s.devices && s.devices[DEVICE]) || {};
    $("#state-reason").textContent = d.reason || "—";
    $("#kv-fps").textContent = d.fps != null ? d.fps.toFixed(1) : "–";
    $("#kv-lat").textContent = d.latency_ms != null ? d.latency_ms.toFixed(0) + " ms" : "–";
    $("#kv-sensors").textContent = d.sensors_elevated ? "ELEVATED" : "normal";
    $("#kv-sensors").style.color = d.sensors_elevated ? "var(--confirmed)" : "";
    estopOn = !!(s.emergency_stop && s.emergency_stop.on);
    $("#kv-estop").textContent = estopOn ? "ON" : "off";
    $("#kv-estop").style.color = estopOn ? "var(--confirmed)" : "";
    $("#estop").classList.toggle("on", estopOn);
    $("#estop").textContent = estopOn ? "RELEASE E-STOP" : "EMERGENCY STOP";
    const stale = !d.updated || Date.now() / 1000 - d.updated > 5;
    $("#cam-meta").textContent = stale ? "inference offline" : (d.camera_connected ? `live · ${ago(d.updated)}` : "CAMERA LOST");
    $("#live-overlay").classList.toggle("hidden", !stale && d.camera_connected !== false);
    $("#live-overlay").textContent = stale ? "INFERENCE OFFLINE" : "CAMERA LOST";
    $("#stat-events").textContent = s.stats.events_24h;
    $("#stat-confirmed").textContent = s.stats.confirmed_24h;
    $("#stat-dets").textContent = s.stats.detections_24h;

    // sensors
    const sen = s.sensor;
    if (sen) {
      $("#v-smoke").textContent = Math.round(sen.smoke);
      $("#v-temp").textContent = sen.temperature.toFixed(1) + " °C";
      $("#g-smoke").style.width = Math.min(100, (sen.smoke / SMOKE_MAX) * 100) + "%";
      $("#g-temp").style.width = Math.min(100, (sen.temperature / TEMP_MAX) * 100) + "%";
      $("#g-smoke").classList.toggle("hot", sen.smoke >= SMOKE_WARN);
      $("#g-temp").classList.toggle("hot", sen.temperature >= TEMP_WARN);
      $("#sensor-age").textContent = sen.stale ? "STALE · " + ago(sen.timestamp) : ago(sen.timestamp);
      $("#sensor-age").style.color = sen.stale ? "var(--confirmed)" : "";
    } else {
      $("#sensor-age").textContent = "no sensor data";
    }

    // latest detections
    $("#detections").innerHTML = (s.latest_detections || []).map((x) =>
      `<li><span class="cls-${x.class}">${x.class}</span><span>${(x.confidence * 100).toFixed(0)}%</span><span class="muted">${fmtTime(x.timestamp)}</span></li>`
    ).join("") || `<li class="muted">no detections yet</li>`;

    // open events with ack buttons
    $("#open-events").innerHTML = (s.open_events || []).map(evRow).join("");
    alarm(s.overall_state === "CONFIRMED" && !estopOn);
    if (s.overall_state !== lastState) { lastState = s.overall_state; loadTimeline(); }
  } catch (e) {
    $("#backend-dot").classList.remove("on");
    $("#cam-meta").textContent = "backend unreachable";
  }
}

function evRow(e) {
  const img = e.evidence_path ? `<img src="/evidence/${e.evidence_path}" onclick="openEvent(${e.id})">` : `<div></div>`;
  const tag = e.acknowledged ? `<span class="tag ack">ACK</span>` : e.end_time ? `<span class="tag closed">closed</span>` : `<span class="tag open">OPEN</span>`;
  const ack = e.acknowledged ? "" : `<button class="btn small ok" onclick="ackEvent(${e.id})">Acknowledge</button>`;
  return `<div class="ev ${e.state}">${img}<div><b>${e.state}</b><div class="t">#${e.id} · ${fmtTime(e.start_time)} · ${dur(e.start_time, e.end_time)}</div></div>
    <div class="muted">${e.reason || ""}${e.peak_class ? ` · peak ${e.peak_class} ${(e.peak_confidence * 100).toFixed(0)}%` : ""}</div>${tag}${ack}</div>`;
}

async function loadTimeline() {
  try {
    const evs = await api("/events?limit=30");
    $("#timeline").innerHTML = evs.map(evRow).join("") || `<div class="muted">no events yet</div>`;
  } catch (e) { /* ignore */ }
}

async function ackEvent(id) {
  await api(`/events/${id}/ack`, { method: "POST" });
  loadTimeline(); pollStatus();
}
async function openEvent(id) {
  const e = await api(`/events/${id}`);
  $("#modal-body").innerHTML = `<h3>Event #${e.id} · ${e.state}</h3>
    <p>${e.device_id} · ${fmtDate(e.start_time)} → ${e.end_time ? fmtDate(e.end_time) : "open"} (${dur(e.start_time, e.end_time)})<br>
    reason: ${e.reason || "–"}${e.peak_class ? `<br>peak: ${e.peak_class} ${(e.peak_confidence * 100).toFixed(0)}%` : ""}<br>
    acknowledged: ${e.acknowledged ? fmtDate(e.ack_time) : "no"}</p>
    ${e.evidence_path ? `<img src="/evidence/${e.evidence_path}">` : "<p class='muted'>no evidence image</p>"}
    <h3>Notifications</h3>${(e.notifications || []).map((n) => `<div>${fmtTime(n.sent_at)} · ${n.channel} · <b>${n.status}</b> ${n.detail || ""}</div>`).join("") || "<div class='muted'>none</div>"}`;
  $("#modal").classList.remove("hidden");
}
window.ackEvent = ackEvent; window.openEvent = openEvent;
$("#modal-close").onclick = () => $("#modal").classList.add("hidden");
$("#modal").onclick = (e) => { if (e.target.id === "modal") $("#modal").classList.add("hidden"); };

$("#estop").onclick = async () => {
  if (!estopOn && !confirm("Activate EMERGENCY STOP? All prototype actuators and the buzzer are blocked until released.")) return;
  await api("/control/estop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: !estopOn }) });
  pollStatus();
};

// ---------------------------------------------------------------- sensor chart (5 s)
async function pollSensorChart() {
  try {
    const rows = await api("/sensors/recent?seconds=600");
    const c = $("#sensor-chart"), ctx = c.getContext("2d");
    const W = c.width, H = c.height, pad = 6;
    ctx.clearRect(0, 0, W, H);
    if (rows.length < 2) return;
    const t0 = rows[0].timestamp, t1 = rows[rows.length - 1].timestamp || t0 + 1;
    const x = (t) => pad + ((t - t0) / Math.max(1, t1 - t0)) * (W - 2 * pad);
    const line = (key, max, color) => {
      ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2;
      rows.forEach((r, i) => { const y = H - pad - Math.min(1, r[key] / max) * (H - 2 * pad); i ? ctx.lineTo(x(r.timestamp), y) : ctx.moveTo(x(r.timestamp), y); });
      ctx.stroke();
    };
    // threshold guides
    ctx.setLineDash([4, 4]); ctx.strokeStyle = "#e5484d"; ctx.lineWidth = 1;
    const ys = H - pad - (SMOKE_WARN / SMOKE_MAX) * (H - 2 * pad);
    ctx.beginPath(); ctx.moveTo(pad, ys); ctx.lineTo(W - pad, ys); ctx.stroke(); ctx.setLineDash([]);
    line("smoke", SMOKE_MAX, "#a9b4c2");
    line("temperature", TEMP_MAX, "#f97316");
  } catch (e) { /* ignore */ }
}

// ---------------------------------------------------------------- history / devices
async function loadHistory() {
  const st = $("#hist-filter").value;
  const evs = await api("/events?limit=200" + (st ? "&state=" + st : ""));
  $("#hist-table tbody").innerHTML = evs.map((e) => `<tr><td>${e.id}</td><td><span class="state-badge ${e.state}" style="padding:2px 8px;font-size:11px">${e.state}</span></td>
    <td>${e.device_id}</td><td>${fmtDate(e.start_time)}</td><td>${dur(e.start_time, e.end_time)}</td>
    <td>${e.peak_class ? `${e.peak_class} ${(e.peak_confidence * 100).toFixed(0)}%` : "–"}</td><td>${e.reason || ""}</td>
    <td>${e.acknowledged ? "✔ " + fmtTime(e.ack_time) : `<button class="btn small ok" onclick="ackEvent(${e.id});loadHistory()">Ack</button>`}</td>
    <td><button class="btn small" onclick="openEvent(${e.id})">details</button></td></tr>`).join("");
  const files = await api("/evidence?limit=60");
  $("#gallery").innerHTML = files.map((f) => `<figure><img src="${f.url}" onclick="window.open('${f.url}')"><figcaption>${f.name}</figcaption></figure>`).join("") || `<div class="muted">no evidence images yet</div>`;
}
$("#hist-filter").onchange = loadHistory;

async function loadDevices() {
  const devs = await api("/devices");
  $("#dev-table tbody").innerHTML = devs.map((d) => `<tr><td>${d.id}</td><td>${d.name || ""}</td><td>${d.location || ""}</td><td>${d.kind}</td>
    <td><span class="dot ${d.online ? "on" : ""}"></span> ${d.status}</td><td>${ago(d.last_seen)}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">no devices registered</td></tr>`;
  const ns = await api("/notifications?limit=50");
  $("#notif-table tbody").innerHTML = ns.map((n) => `<tr><td>${fmtDate(n.sent_at)}</td><td>${n.event_id ?? "–"}</td><td>${n.channel}</td><td>${n.status}</td><td class="muted">${n.detail || ""}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">none yet</td></tr>`;
}

// ---------------------------------------------------------------- boot
$("#cam-name").textContent = DEVICE;
$("#live").onerror = () => setTimeout(() => { $("#live").src = "/stream/" + DEVICE + "?t=" + Date.now(); }, 2000);
pollStatus(); loadTimeline(); pollSensorChart();
setInterval(pollStatus, 1000);
setInterval(loadTimeline, 5000);
setInterval(pollSensorChart, 5000);
setInterval(() => { if ($("#tab-devices").classList.contains("active")) loadDevices(); }, 5000);
