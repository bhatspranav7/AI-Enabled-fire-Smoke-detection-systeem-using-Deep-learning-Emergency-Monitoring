/* Phase-2 review deck. Run:  node ppt/build_deck.js   (reads real metrics from models/*.json) */
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("C:/Users/Pranav Bhat/AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin/d82b2145-c6d4-4885-b9ea-f8a285ffdd84/511cbaba-f7bd-4b8e-b8a4-4367e61b13e1/skills/pptx/scripts/apply_theme.js");

const ROOT = path.resolve(__dirname, "..");
const FIG = (f) => path.join(ROOT, "paper", "figs", f);
const j = (p, d) => { try { return JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8")); } catch { return d; } };
const M = j("models/eval_metrics.json", null);
const TC = j("models/training_config.json", {});
const f3 = (x) => (x == null ? "–" : Number(x).toFixed(3));
const ov = M ? M.overall : { precision: 0, recall: 0, f1: 0, mAP50: 0, "mAP50-95": 0 };
const pc = M ? M.per_class : { fire: ov, smoke: ov };
const op = M ? M.operating_point : { negatives: 60, negatives_clean: 0, tp: 0, fp: 0, fn: 0 };
const lat = M ? M.latency : { mean_ms: 0, fps: 0 };

// ---------------------------------------------------------------- theme
const THEME = {
  name: "Ember",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B1F24", lt1: "FFFFFF", dk2: "4A5563", lt2: "F3F4F6",
    accent1: "E8532E", accent2: "F4A226", accent3: "8A8F98", accent4: "2EA043", accent5: "E5484D", accent6: "3B82F6",
    hlink: "E8532E", folHlink: "F4A226",
  },
};
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "AI-Enabled Fire/Smoke Detection - Phase 2 Review";
const C = pres.SchemeColor;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "DARK", background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.7, w: 8.8, h: 1.4, fontSize: 36, bold: true, color: C.background1, align: "left", margin: 0 } } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.2, w: 8.8, h: 1.6, fontSize: 16, color: C.background2, align: "left", margin: 0 } } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: THEME.colors.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.35, w: 9.0, h: 0.7, fontSize: 28, bold: true, color: C.text1, align: "left", margin: 0 } } },
    { text: { text: "AI-Enabled Fire/Smoke Detection · Phase-2 Review", options: { x: 0.5, y: 5.2, w: 6, h: 0.3, fontSize: 9, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: 9.1, y: 5.2, w: 0.5, h: 0.3, fontSize: 9, color: THEME.colors.accent3 },
});

// ---------------------------------------------------------------- helpers
let n = 0;
function section(num, name) {
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: `${num}. ${name}` });
  s.addShape(pres.ShapeType.ellipse, { x: 0.6, y: 0.7, w: 0.8, h: 0.8, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "num-circle" });
  s.addText(String(num), { x: 0.6, y: 0.7, w: 0.8, h: 0.8, fontSize: 24, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "num" });
  s.addText(name, { placeholder: "title" });
  return s;
}
function content(title, sec) {
  n++;
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: sec });
  s.addText(title, { placeholder: "title" });
  return s;
}
function card(s, x, y, w, h, head, body, opts = {}) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08, fill: { color: opts.fill || C.background2 }, line: { color: opts.fill || C.background2 }, objectName: `card-${head}` });
  if (opts.num != null) {
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.15, y: y + 0.15, w: 0.4, h: 0.4, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: `card-num-${head}` });
    s.addText(String(opts.num), { x: x + 0.15, y: y + 0.15, w: 0.4, h: 0.4, fontSize: 12, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: `card-numtxt-${head}` });
  }
  const hx = opts.num != null ? x + 0.65 : x + 0.15;
  const compact = h < 1.0;
  const headY = compact ? y + 0.06 : y + 0.12, headH = compact ? 0.3 : 0.45, bodyY = compact ? y + 0.38 : y + 0.62;
  s.addText(head, { x: hx, y: headY, w: w - (hx - x) - 0.15, h: headH, fontSize: opts.headSize || 14, bold: true, color: opts.headColor || C.text1, valign: "middle", margin: 0, isTextBox: true, objectName: `card-head-${head}` });
  s.addText(body, { x: x + 0.15, y: bodyY, w: w - 0.3, h: y + h - bodyY - 0.08, fontSize: opts.bodySize || 11.5, color: opts.bodyColor || C.text2, valign: "top", margin: 0, isTextBox: true, objectName: `card-body-${head}` });
}
function bullets(s, items, x, y, w, h, size = 14, color = C.text2) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })),
    { x, y, w, h, fontSize: size, color, valign: "top", paraSpaceAfter: 6, margin: 0, isTextBox: true, objectName: "bullets" });
}
function stat(s, x, y, w, big, label, color = C.accent1) {
  s.addText(big, { x, y, w, h: 0.8, fontSize: 40, bold: true, color, align: "center", margin: 0, isTextBox: true, objectName: `stat-${label}` });
  s.addText(label, { x, y: y + 0.8, w, h: 0.5, fontSize: 11, color: C.text2, align: "center", margin: 0, isTextBox: true, objectName: `stat-label-${label}` });
}
function flowBox(s, x, y, w, h, text, fill = C.background2, color = C.text1, size = 11) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.06, fill: { color: fill }, line: { color: fill }, objectName: `flow-${text}` });
  s.addText(text, { x, y, w, h, fontSize: size, bold: true, color, align: "center", valign: "middle", margin: 0.04, isTextBox: true, objectName: `flowtxt-${text}` });
}
function arrow(s, x1, y1, x2, y2) {
  s.addShape(pres.ShapeType.line, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: THEME.colors.accent3, width: 1.5, endArrowType: "triangle" }, objectName: "arrow" });
}
const tableOpts = (extra = {}) => ({ fontSize: 11, color: THEME.colors.dk2, border: { type: "solid", pt: 0.5, color: "D1D5DB" }, fill: { color: THEME.colors.lt1 }, valign: "middle", margin: 0.05, ...extra });
const th = (t) => ({ text: t, options: { bold: true, color: THEME.colors.lt1, fill: { color: THEME.colors.dk1 } } });

// ================================================================ TITLE
pres.addSection({ title: "Title" });
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Title" });
  s.addShape(pres.ShapeType.ellipse, { x: 0.6, y: 0.6, w: 0.9, h: 0.9, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "logo" });
  s.addText("🔥", { x: 0.6, y: 0.6, w: 0.9, h: 0.9, fontSize: 26, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "logo-emoji" });
  s.addText("AI-Enabled Fire/Smoke Detection and Automated Emergency Response System", { x: 0.6, y: 1.6, w: 8.8, h: 1.5, fontSize: 32, bold: true, color: C.background1, margin: 0, isTextBox: true, objectName: "title" });
  s.addText("Using Deep Learning and IoT  ·  Phase-2 Project Review", { x: 0.6, y: 3.1, w: 8.8, h: 0.45, fontSize: 16, color: C.accent2, margin: 0, isTextBox: true, objectName: "subtitle" });
  s.addText([
    { text: "M R Varun  ·  M H Mayur Gowda  ·  Kedar Lokesh Vandith", options: { breakLine: true, bold: true } },
    { text: "Guides: Dr. Janhavi V  ·  Dr. Ayesha Taranum", options: { breakLine: true } },
    { text: "Department of Computer Science and Engineering, Vidyavardhaka College of Engineering, Mysuru", options: {} },
  ], { x: 0.6, y: 3.9, w: 8.8, h: 1.2, fontSize: 13, color: C.background2, margin: 0, isTextBox: true, paraSpaceAfter: 4, objectName: "authors" });
}

// ================================================================ 1. INTRODUCTION
pres.addSection({ title: "1. Introduction" });
section(1, "Introduction");
{
  const s = content("Background and motivation", "1. Introduction");
  bullets(s, [
    "Fire is a leading cause of property loss and casualties; the gap between ignition and human detection drives escalation.",
    "Point-type smoke/heat sensors are slow in open or high-ceiling spaces and cannot localise an event.",
    "CCTV is already installed almost everywhere, but humans cannot watch feeds reliably over long shifts.",
    "Deep learning (YOLO family) now runs in real time on commodity hardware — the camera itself can become the detector.",
    "Detection alone is not safety: alerts need confirmation, evidence, logging and a monitoring interface.",
  ], 0.5, 1.25, 5.4, 3.8, 14);
  stat(s, 6.3, 1.5, 3.2, "seconds", "typical delay that decides escalation", C.accent1);
  stat(s, 6.3, 3.1, 3.2, "0 → 1", "cameras reused: no new sensors needed for vision", C.accent2);
}
{
  const s = content("Objectives and scope", "1. Introduction");
  const objs = [
    ["Real-time detector", "YOLOv11n fire/smoke detector that runs on a laptop CPU, usable with existing CCTV/USB cameras."],
    ["Robust dataset", "Stratified indoor + outdoor corpus with explicit negatives; augmentation for scale, lighting and scene variation."],
    ["Temporal confirmation", "Convert noisy per-frame boxes into NORMAL → WARNING → CONFIRMED → RECOVERY states; never trigger on one frame."],
    ["Alerts and evidence", "Snapshots, event database, buzzer, multi-channel notifications, acknowledgement and emergency stop."],
    ["Backend and dashboard", "REST API + SQLite + live web dashboard for monitoring, history and device health."],
    ["Evaluation", "Precision, recall, F1, mAP, false-alarm rate on negatives, CPU latency; fail-safe integration tests."],
  ];
  objs.forEach(([h, b], i) => card(s, 0.5 + (i % 3) * 3.05, 1.25 + Math.floor(i / 3) * 1.95, 2.9, 1.8, h, b, { num: i + 1 }));
  s.addText("Scope: academic prototype with isolated low-voltage outputs — not certified fire-safety equipment.", { x: 0.5, y: 5.0, w: 9, h: 0.25, fontSize: 10, italic: true, color: C.accent3, margin: 0, isTextBox: true, objectName: "scope" });
}
{
  const s = content("Proposed solution and expected outcome", "1. Introduction");
  const steps = ["Camera", "Dataset", "YOLO detector", "Real-time inference", "Decision engine", "IoT verification", "Alerts / response", "Dashboard"];
  steps.forEach((t, i) => { flowBox(s, 0.5 + i * 1.17, 1.4, 1.05, 0.8, t, i === 4 ? C.accent1 : C.background2, i === 4 ? C.background1 : C.text1, 10); if (i < steps.length - 1) arrow(s, 1.55 + i * 1.17, 1.8, 1.67 + i * 1.17, 1.8); });
  card(s, 0.5, 2.6, 4.4, 2.4, "What we build", "Vision-first detection on existing cameras · temporal confirmation with hysteresis · optional ESP32 gas/temperature fusion · evidence + events + notifications · live dashboard with acknowledge and emergency stop.", { bodySize: 12.5 });
  card(s, 5.1, 2.6, 4.4, 2.4, "Expected outcome", "Alert within seconds of a sustained flame/smoke, far fewer false alarms than single-frame or colour-rule detectors, a complete audit trail (who acknowledged, when, with evidence), and a reproducible model build with documented metrics.", { bodySize: 12.5 });
}

// ================================================================ 2. PROBLEM STATEMENT
pres.addSection({ title: "2. Problem Statement" });
section(2, "Problem Statement");
{
  const s = content("Problem definition and existing gaps", "2. Problem Statement");
  card(s, 0.5, 1.25, 9.0, 1.1, "Problem", "Build a system that is simultaneously accurate on real CCTV-like footage, fast enough for live streams on commodity hardware, and embedded in a complete confirmation–alerting–monitoring pipeline.", { fill: C.accent1, headColor: C.background1, bodyColor: C.background1, bodySize: 13 });
  const gaps = [
    ["Benchmark ≠ field", "Published detectors are evaluated on curated images, not noisy, variably lit multi-angle CCTV — accuracy does not transfer."],
    ["Accuracy vs latency", "Deeper nets and Transformer blocks gain accuracy at a latency cost that is unacceptable when seconds matter."],
    ["Detection ≠ safety", "A raw bounding box cannot be operationalised without temporal confirmation, alerting, evidence and logging."],
  ];
  gaps.forEach(([h, b], i) => card(s, 0.5 + i * 3.05, 2.55, 2.9, 1.45, h, b, { num: i + 1, bodySize: 11 }));
  card(s, 0.5, 4.15, 9.0, 0.95, "Our approach", "Lightweight YOLOv11n fine-tuned on a stratified corpus with hard negatives  →  time-windowed state machine with separate enter/clear thresholds  →  IoT fusion  →  evidence, API, dashboard, fail-safes.", { bodySize: 12 });
}

// ================================================================ 3. LITERATURE SURVEY
pres.addSection({ title: "3. Literature Survey" });
section(3, "Literature Survey");
{
  const s = content("Review of relevant research", "3. Literature Survey");
  const rows = [
    ["YOLOv8/v7 fine-tuned (Saleh et al.)", "single-stage detector", "2024", "wildfire smoke, flame"],
    ["Improved YOLOv8s (Kong et al.)", "light backbone + attention", "2024", "coal-mine fire/smoke"],
    ["Improved YOLOv5s (Dou et al.)", "feature-fusion refinement", "2024", "general fire"],
    ["FS-YOLO (Wang et al.)", "joint fire–smoke head", "2024", "fire and smoke"],
    ["YOLOv11 (Khanam & Hussain)", "C3k2, SPPF, C2PSA", "2024", "general detection"],
    ["Shallow guide deep net (Li et al.)", "lightweight CNN", "2024", "early-stage fire"],
    ["Fire-ViT (Liu & Mariano)", "Vision Transformer", "2025", "tunnel fire"],
    ["CN2VF-Net / FireNet-KD (Ahmad et al.)", "hybrid CNN–ViT, distillation", "2025", "complex scenes, wildfire"],
    ["SmokeSeger (Jing et al.)", "Transformer–CNN segmentation", "2023", "urban smoke"],
    ["CAS-ViT (Zhang et al.)", "additive self-attention ViT", "2024", "mobile vision"],
  ];
  s.addTable([[th("Method"), th("Core technique"), th("Year"), th("Focus")], ...rows.map((r) => r.map((c) => ({ text: c })))],
    { x: 0.5, y: 1.25, w: 9.0, colW: [3.3, 2.7, 0.8, 2.2], ...tableOpts({ fontSize: 10.5 }), objectName: "lit-table" });
}
{
  const s = content("Comparison of methods and research gap", "3. Literature Survey");
  const cmp = [
    ["Two-stage (Faster R-CNN)", "Highest localisation accuracy, but 5–17 fps: too slow for multi-camera live monitoring."],
    ["SSD / classic CNN classifiers", "Fast, but frame-level only; weak on thin smoke and small flames."],
    ["YOLO family (v5 → v8 → v11)", "Best accuracy-per-millisecond; anchor-free head and C2PSA attention help diffuse smoke. Chosen backbone."],
    ["ViT / hybrid (Fire-ViT, CN2VF-Net)", "Strong in-domain accuracy; heavier inference, reduced robustness outside training domain."],
  ];
  cmp.forEach(([h, b], i) => card(s, 0.5, 1.25 + i * 0.98, 5.3, 0.9, h, b, { bodySize: 10.5, headSize: 12 }));
  card(s, 6.0, 1.25, 3.5, 3.85, "Research gap identified", "Reviewed work stops at per-frame metrics.\n\nRarely specified: how a detection becomes a verified alert; how steam, fog and lighting false alarms are suppressed over time; what happens when a camera, sensor or network fails.\n\nOur contribution: robust false-alarm reduction + multi-stage automated response — not a new architecture.", { fill: C.text1, headColor: C.accent2, bodyColor: C.background2, bodySize: 12 });
}

// ================================================================ 4. SYSTEM REQUIREMENTS
pres.addSection({ title: "4. System Requirements" });
section(4, "System Requirements");
{
  const s = content("Hardware and software requirements", "4. System Requirements");
  s.addTable([[th("Hardware"), th("Specification / role")],
    ["Development laptop", "Intel i5-1340P (12 cores), 16 GB RAM, no GPU — training and inference"],
    ["Camera", "USB webcam / IP / RTSP CCTV, 720p–1080p"],
    ["ESP32", "Sensor gateway + low-voltage actuator controller"],
    ["MQ-2 gas, temperature sensor", "Environmental evidence for fusion"],
    ["Buzzer, relay, LED", "Local alarm, isolated low-voltage prototype load"],
  ].map((r, i) => (i ? r.map((c) => ({ text: c })) : r)), { x: 0.5, y: 1.25, w: 4.4, colW: [1.7, 2.7], ...tableOpts({ fontSize: 10.5 }), objectName: "hw-table" });
  s.addTable([[th("Software / tool"), th("Use")],
    ["Python 3.10+", "all modules"],
    ["PyTorch (CPU) + Ultralytics 8.4", "YOLOv11n training/inference"],
    ["OpenCV", "capture, preprocessing, overlay"],
    ["FastAPI + Uvicorn, SQLite", "backend API, event database"],
    ["HTML/CSS/JavaScript", "dashboard (no framework)"],
    ["Requests, SMTP, Telegram Bot API", "notifications"],
    ["pytest", "23 unit + API tests"],
    ["Git/GitHub, VS Code", "version control, development"],
  ].map((r, i) => (i ? r.map((c) => ({ text: c })) : r)), { x: 5.1, y: 1.25, w: 4.4, colW: [2.2, 2.2], ...tableOpts({ fontSize: 10.5 }), objectName: "sw-table" });
}
{
  const s = content("Dataset, API and other dependencies", "4. System Requirements");
  s.addTable([[th("Split"), th("Images"), th("Fire"), th("Smoke"), th("Both"), th("Negative")],
    ["Train", "3,000", "988", "988", "723", "301"], ["Validation", "600", "189", "187", "164", "60"], ["Test (held-out)", "600", "203", "202", "135", "60"],
  ].map((r, i) => (i ? r.map((c) => ({ text: c })) : r)), { x: 0.5, y: 1.25, w: 5.2, colW: [1.3, 0.8, 0.75, 0.8, 0.75, 0.8], ...tableOpts({ fontSize: 10.5 }), objectName: "ds-table" });
  bullets(s, [
    "Sources: Hugging Face fog_fire_detection (40.9k, CC-BY-4.0, outdoor + CCTV) and ISFire-4 (7.4k, MIT, indoor); 4 fine classes mapped to fire / smoke.",
    "Stratified per source and split; no video leakage between train and test; dataset register documents licence and mapping.",
  ], 0.5, 2.75, 5.2, 2.3, 11.5);
  card(s, 6.0, 1.25, 3.5, 3.85, "Backend API (FastAPI)", "GET /health · GET /status\nGET /devices · /devices/{id}\nPOST /sensors (ESP32)\nPOST /detections (AI)\nGET /events · /events/{id}\nPOST /events/{id}/ack\nPOST /control/estop\nGET /stream/{id} (MJPEG)\n\nConfig in YAML: thresholds, device, model, notifications; secrets in .env.", { bodySize: 11.5 });
}

// ================================================================ 5. SYSTEM DESIGN
pres.addSection({ title: "5. System Design" });
section(5, "System Design");
{
  const s = content("System architecture and workflow", "5. System Design");
  const layers = [
    ["Capture & inference", ["Camera (USB / RTSP)", "OpenCV capture, letterbox, reconnect", "YOLOv11n → class, conf, box"]],
    ["Decision & response", ["Temporal decision engine", "Sensor fusion + zone filter", "Evidence, buzzer, notifications"]],
    ["Backend & presentation", ["FastAPI REST + MJPEG", "SQLite: devices, readings, events", "Web dashboard: live, ack, e-stop"]],
    ["IoT node", ["ESP32: MQ-2 gas + temperature", "HTTP POST /sensors, polls commands", "Buzzer, isolated relay, fail-safe"]],
  ];
  layers.forEach(([name, boxes], r) => {
    const y = 1.25 + r * 0.98;
    s.addShape(pres.ShapeType.roundRect, { x: 0.5, y, w: 9.0, h: 0.88, rectRadius: 0.06, fill: { color: C.background2 }, line: { color: C.background2 }, objectName: `layer-${name}` });
    s.addText(name, { x: 0.65, y, w: 1.7, h: 0.88, fontSize: 11, bold: true, color: C.accent1, valign: "middle", margin: 0, isTextBox: true, objectName: `layer-name-${name}` });
    boxes.forEach((b, i) => flowBox(s, 2.5 + i * 2.35, y + 0.14, 2.2, 0.6, b, C.background1, C.text1, 10));
    if (r < 3) arrow(s, 3.6, y + 0.88, 3.6, y + 0.98);
  });
}
{
  const s = content("Modules and their functionalities", "5. System Design");
  const mods = [
    ["Dataset builder", "training/prepare_dataset.py — stratified sampling from two zips, class remapping, data.yaml, manifest + register."],
    ["Trainer & evaluator", "training/train.py, evaluate.py — YOLOv11n fine-tuning; per-class P/R/F1/mAP, FP/FN images, latency."],
    ["Camera & inference", "vision/, inference/run_live.py — webcam/video/RTSP/folder, reconnect, overlay, evidence snapshots, keys."],
    ["Decision engine", "decision_engine/ — time-window state machine, hysteresis, fusion, zone, ack, e-stop; 15 unit tests."],
    ["Backend & database", "backend/ — FastAPI + SQLite; devices, sensors, detections, events, notifications; command queue; 8 API tests."],
    ["Dashboard, alerts, IoT", "dashboard/, notifications/, iot/ — live UI, Telegram/e-mail, ESP32 firmware + sensor simulator."],
  ];
  mods.forEach(([h, b], i) => card(s, 0.5 + (i % 3) * 3.05, 1.25 + Math.floor(i / 3) * 1.95, 2.9, 1.8, h, b, { num: i + 1, bodySize: 11 }));
}
{
  const s = content("Algorithm: temporal decision engine", "5. System Design");
  const states = [["NORMAL", C.accent4], ["WARNING", C.accent2], ["CONFIRMED", C.accent5], ["RECOVERY", C.accent6]];
  states.forEach(([t, c], i) => { flowBox(s, 0.5 + i * 2.35, 1.3, 2.1, 0.7, t, c, C.background1, 14); if (i < 3) arrow(s, 2.6 + i * 2.35, 1.65, 2.85 + i * 2.35, 1.65); });
  s.addText("≥ 3 hits ≥ 0.35 in 3 s", { x: 2.4, y: 2.05, w: 2.2, h: 0.3, fontSize: 9.5, color: C.text2, align: "center", margin: 0, isTextBox: true, objectName: "t1" });
  s.addText("≥ 10 hits ≥ 0.55 over ≥ 2 s (≥ 6 if sensors elevated)", { x: 4.6, y: 2.05, w: 2.6, h: 0.3, fontSize: 9.5, color: C.text2, align: "center", margin: 0, isTextBox: true, objectName: "t2" });
  s.addText("nothing ≥ 0.25 for 4 s", { x: 7.2, y: 2.05, w: 2.3, h: 0.3, fontSize: 9.5, color: C.text2, align: "center", margin: 0, isTextBox: true, objectName: "t3" });
  bullets(s, [
    "Sliding 3 s window of best-detection confidences; a single frame can never trigger.",
    "Separate enter (0.35 / 0.55) and clear (0.25) thresholds = hysteresis, no flapping.",
    "Sensor fusion: elevated gas/temperature lowers the confirmation bar; sensor-only evidence → SENSOR_WARNING.",
    "Stale sensor readings (> 15 s) ignored; acknowledge → RECOVERY; emergency stop blocks all physical outputs.",
    "RECOVERY → NORMAL after 10 s stable; re-appearance re-confirms immediately.",
  ], 0.5, 2.55, 5.6, 2.6, 12.5);
  card(s, 6.4, 2.55, 3.1, 2.5, "Also used", "YOLOv11n (anchor-free, C2PSA) · IoU matching at 0.5 · NMS · mosaic/HSV/flip/scale augmentation · AdamW, seed 42 · precision/recall/F1/mAP@0.5/0.5:0.95.", { bodySize: 11.5 });
}

// ================================================================ 6. IMPLEMENTATION & DEMO
pres.addSection({ title: "6. Implementation and Demonstration" });
section(6, "Implementation and Demonstration");
{
  const s = content("Module 1 implemented: AI fire/smoke model", "6. Implementation and Demonstration");
  bullets(s, [
    "Downloaded and merged two public datasets; stratified 3,000 / 600 / 600 split with 15 % negatives.",
    `YOLOv11n fine-tuned from COCO weights: 416 px, batch 16, ${TC.epochs || 10} epochs, AdamW, seed 42 — on CPU (${TC.training_time_minutes || "~70"} min).`,
    "Evaluation script: per-class precision / recall / F1 / mAP, FP/FN example images, false-alarm rate on negatives, latency.",
    "Artifacts: models/best.pt, training_config.json, eval_report.md, PR curves, confusion matrix, dataset register.",
  ], 0.5, 1.25, 4.6, 3.8, 12.5);
  s.addImage({ path: FIG("results.png"), x: 5.3, y: 1.3, w: 4.2, h: 1.55, objectName: "curves" });
  s.addText("Training/validation loss and validation metrics per epoch", { x: 5.3, y: 2.88, w: 4.2, h: 0.25, fontSize: 9, color: C.accent3, align: "center", margin: 0, isTextBox: true, objectName: "cap1" });
  s.addImage({ path: FIG("BoxPR_curve.png"), x: 5.3, y: 3.2, w: 2.0, h: 1.5, objectName: "pr" });
  s.addImage({ path: FIG("confusion_matrix_normalized.png"), x: 7.5, y: 3.2, w: 2.0, h: 1.5, objectName: "cm" });
  s.addText("PR curves · normalised confusion matrix (test split)", { x: 5.3, y: 4.72, w: 4.2, h: 0.25, fontSize: 9, color: C.accent3, align: "center", margin: 0, isTextBox: true, objectName: "cap2" });
}
{
  const s = content("Module 2 implemented: real-time pipeline", "6. Implementation and Demonstration");
  s.addImage({ path: FIG("dashboard.png"), x: 0.5, y: 1.25, w: 5.4, h: 3.05, objectName: "dash" });
  s.addText("Live dashboard: annotated feed, state, sensors, latest detections, events", { x: 0.5, y: 4.32, w: 5.4, h: 0.25, fontSize: 9, color: C.accent3, align: "center", margin: 0, isTextBox: true, objectName: "cap3" });
  bullets(s, [
    "Camera → YOLO → filters → time-window engine → overlay, evidence, buzzer, notifications.",
    "FastAPI + SQLite backend with the full required endpoint set; MJPEG live stream.",
    "Dashboard: NORMAL / WARNING / CONFIRMED, sensor gauges + chart, timeline, acknowledge, history, device health, e-stop.",
    "ESP32 simulator + firmware for sensor fusion; fail-safes for camera, sensor and network loss.",
    "23 automated tests pass (engine + API); one-click setup/run scripts for any laptop.",
  ], 6.1, 1.25, 3.4, 3.9, 11);
}
{
  const s = content("Demonstration plan (two modules)", "6. Implementation and Demonstration");
  const steps = [
    ["Model artefacts", "Dataset register → training config → eval report, PR curve, confusion matrix, FP/FN examples."],
    ["Live NORMAL", "Room only: green state, FPS/latency, sensors normal, device online."],
    ["Single-frame test", "Flash a fire video < 1 s: boxes appear, state stays NORMAL."],
    ["WARNING → CONFIRMED", "Hold fire: WARNING in ~1 s, CONFIRMED after 2 s — buzzer, evidence, event, notification."],
    ["Acknowledge / recovery", "Dashboard Acknowledge → RECOVERY → NORMAL after 10 s; event closed with duration + peak."],
    ["Hard negative", "Steam / white cloth / torch: no alarm."],
    ["Sensor fusion", "Simulator smoke → SENSOR_WARNING; smoke+heat + fire → faster confirmation; disconnect → stale."],
    ["Fail-safes", "Cover camera → CAMERA LOST + auto-reconnect; stop backend → inference continues; EMERGENCY STOP."],
  ];
  steps.forEach(([h, b], i) => card(s, 0.5 + (i % 4) * 2.3, 1.25 + Math.floor(i / 4) * 1.95, 2.15, 1.8, h, b, { num: i + 1, bodySize: 10.5, headSize: 12 }));
}
{
  const s = content("Results on the held-out test split", "6. Implementation and Demonstration");
  s.addTable([[th("Class"), th("Precision"), th("Recall"), th("F1"), th("mAP@0.5"), th("mAP@0.5:0.95")],
    ["Fire", f3(pc.fire.precision), f3(pc.fire.recall), f3(pc.fire.f1), f3(pc.fire.mAP50), f3(pc.fire["mAP50-95"])],
    ["Smoke", f3(pc.smoke.precision), f3(pc.smoke.recall), f3(pc.smoke.f1), f3(pc.smoke.mAP50), f3(pc.smoke["mAP50-95"])],
    ["All", f3(ov.precision), f3(ov.recall), f3(ov.f1), f3(ov.mAP50), f3(ov["mAP50-95"])],
  ].map((r, i) => (i ? r.map((c, k) => ({ text: c, options: k === 0 ? { bold: true } : {} })) : r)), { x: 0.5, y: 1.25, w: 5.6, colW: [0.85, 0.95, 0.8, 0.7, 0.95, 1.35], ...tableOpts({ fontSize: 11 }), objectName: "metrics" });
  stat(s, 6.4, 1.2, 3.1, f3(ov.mAP50), "mAP@0.5 (600 images, 10-epoch CPU model)", C.accent1);
  stat(s, 6.4, 2.6, 3.1, `${op.negatives_clean}/${op.negatives}`, "negative images with zero false alarms", C.accent4);
  stat(s, 6.4, 4.0, 3.1, `${lat.fps} fps`, `CPU only, ${lat.mean_ms} ms per frame at 416 px`, C.accent6);
  bullets(s, [
    `Operating point (conf 0.35, IoU 0.5): TP ${op.tp}, FP ${op.fp}, FN ${op.fn}; the temporal engine filters isolated boxes before any alert.`,
    "Engine verified by 15 unit tests; backend by 8 API tests; live fail-safe scenarios executed on the demo laptop.",
    "Numbers are a lower bound: 4,200-image subset, 10 epochs, no GPU — same scripts scale to the full 48k corpus.",
  ], 0.5, 2.85, 5.6, 2.3, 11.5);
}
{
  const s = content("Challenges encountered", "6. Implementation and Demonstration");
  const ch = [
    ["No GPU", "CPU-only training limited us to a 4,200-image subset and 10 epochs (~7 min/epoch); mitigated with YOLOv11n, 416 px, RAM caching, stratified sampling."],
    ["Dataset mismatch", "Public sets are wildfire-heavy; indoor demo flames looked different. Merged an indoor set and balanced fire/smoke/both/negative."],
    ["False alarms", "Reflections, torch light and steam produce single high-confidence boxes; solved by time-windowed confirmation and hysteresis, not by lowering thresholds."],
    ["Robustness", "Camera disconnects, stale sensors and backend outages had to be handled explicitly (reconnect, staleness check, local buffering)."],
    ["Shared CPU", "Running live inference while training slowed both 10×; sequenced the work and added a headless/test mode."],
    ["Reproducibility", "Config in YAML, fixed seed, dataset register, committed small weights so any laptop runs the demo without retraining."],
  ];
  ch.forEach(([h, b], i) => card(s, 0.5 + (i % 3) * 3.05, 1.25 + Math.floor(i / 3) * 1.95, 2.9, 1.8, h, b, { bodySize: 10.5 }));
}

// ================================================================ 7. PAPER STATUS
pres.addSection({ title: "7. Paper Status" });
section(7, "Paper Status");
{
  const s = content("Paper title, target and current status", "7. Paper Status");
  card(s, 0.5, 1.25, 9.0, 1.2, "Title", "AI-Based Fire and Smoke Detection System Using Deep Learning for Real-Time Emergency Monitoring", { fill: C.text1, headColor: C.accent2, bodyColor: C.background1, bodySize: 15 });
  card(s, 0.5, 2.65, 4.4, 2.4, "Target", "IEEE-sponsored international conference (IEEE Xplore indexed); prepared in the IEEE conference (IEEEtran) two-column format, 7 pages.\n\nAuthors: M R Varun, M H Mayur Gowda, Kedar Lokesh Vandith; Dr. Janhavi V, Dr. Ayesha Taranum.", { bodySize: 12 });
  card(s, 5.1, 2.65, 4.4, 2.4, "Current status", "Full draft complete with measured results, literature table (12 works), architecture/workflow figures, algorithm and 28 references.\n\nNext: guide review → final numbers from extended training → submission.", { bodySize: 12 });
}
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "7. Paper Status" });
  s.addText("Thank you", { placeholder: "title" });
  s.addText("Questions?\n\nRepository: github.com/bhatspranav7/AI-Enabled-fire-Smoke-detection-systeem-using-Deep-learning-Emergency-Monitoring", { placeholder: "body" });
}

(async () => {
  const out = path.join(__dirname, "Phase2_Review_Fire_Smoke_Detection.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("wrote", out);
})();
