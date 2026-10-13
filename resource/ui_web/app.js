import { createClient } from "/sdk/client.js";

const client = createClient({ transport: "sse" });
const $ = (selector) => document.querySelector(selector);
const appMain = $("#app-main");
const headerBadges = $("#header-badges");
const activityToggle = $("#activity-toggle");
const appFooter = $("#app-footer");
let pendingCommand = Promise.resolve();
let nextHoldId = 0;
const activeHolds = new Map();
let currentVitals = null;
let waveformFrame = 0;
let activityVisible = true;
let renderedKind = null;
let renderedControlSignature = null;
const waveformSampleRate = 200;
const waveformBufferLength = waveformSampleRate * 6;
const waveformStates = {
  ecg: {
    rate: 1,
    amplitude: 1,
    minimum: -0.2,
    maximum: 1.1,
    color: "#00e676",
  },
  pleth: {
    rate: 1,
    amplitude: 1,
    minimum: -0.1,
    maximum: 1.1,
    color: "#00b0ff",
  },
  capno: {
    rate: 1,
    amplitude: 1,
    minimum: -0.1,
    maximum: 1.1,
    color: "#ffd600",
  },
};

function ecgTemplate() {
  return Array.from({ length: waveformSampleRate }, (_, index) => {
    const time = index / (waveformSampleRate - 1);
    const gaussian = (center, width, amplitude) =>
      amplitude * Math.exp(-((time - center) ** 2) / (2 * width ** 2));
    return gaussian(.12, .008, .15) - gaussian(.22, .004, .08)
      + gaussian(.26, .003, 1) - gaussian(.30, .004, .15)
      + gaussian(.42, .015, .3);
  });
}

function plethTemplate() {
  return Array.from({ length: waveformSampleRate }, (_, index) => {
    const time = index / (waveformSampleRate - 1);
    return Math.min(
      1,
      Math.exp(-((time - .35) ** 2) / (2 * .05 ** 2))
        + .25 * Math.exp(-((time - .55) ** 2) / (2 * .04 ** 2)),
    );
  });
}

function capnoTemplate() {
  return Array.from({ length: waveformSampleRate }, (_, index) => {
    const time = index / (waveformSampleRate - 1);
    if (time >= .3 && time < .6) return (time - .3) / .3;
    if (time >= .6 && time < .85) return 1;
    if (time >= .85 && time < .95) return 1 - (time - .85) / .1;
    return 0;
  });
}

const waveformTemplates = {
  ecg: ecgTemplate(),
  pleth: plethTemplate(),
  capno: capnoTemplate(),
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

function sendCommand(command, payload) {
  const request = pendingCommand.then(() =>
    client.invokeCommand(command, payload || {}),
  );
  pendingCommand = request.catch(() => {});
  request.catch((error) => {
    console.error(`RTI Demo UI command '${command}' failed:`, error);
  });
  return request;
}

function stopActiveHolds() {
  for (const stop of [...activeHolds.values()]) stop();
}

window.addEventListener("blur", stopActiveHolds);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopActiveHolds();
});

function bindHold(button, control) {
  const holdId = nextHoldId++;
  let pressed = false;
  let refreshTimer = 0;

  const stop = () => {
    if (!pressed) return;
    pressed = false;
    window.clearInterval(refreshTimer);
    activeHolds.delete(holdId);
    sendCommand(control.command, {
      axis: control.axis,
      direction: "STOPPED",
    });
  };

  const start = (event) => {
    event.preventDefault();
    if (pressed || button.disabled) return;
    pressed = true;
    activeHolds.set(holdId, stop);
    if (event.pointerId !== undefined) {
      button.setPointerCapture?.(event.pointerId);
    }
    const payload = { axis: control.axis, direction: control.direction };
    sendCommand(control.command, payload);
    refreshTimer = window.setInterval(() => {
      if (pressed) sendCommand(control.command, payload);
    }, 200);
  };

  button.addEventListener("pointerdown", start);
  button.addEventListener("pointerup", stop);
  button.addEventListener("pointercancel", stop);
  button.addEventListener("lostpointercapture", stop);
  button.addEventListener("keydown", (event) => {
    if (event.key === " " || event.key === "Enter") start(event);
  });
  button.addEventListener("keyup", (event) => {
    if (event.key === " " || event.key === "Enter") stop();
  });
}

function renderDpad(command, disabled) {
  const pad = element("div", "dpad-pad");
  const cells = [
    null,
    { label: "▲  Y+", axis: "Y", direction: "POSITIVE" },
    null,
    { label: "◀  X−", axis: "X", direction: "NEGATIVE" },
    null,
    { label: "X+  ▶", axis: "X", direction: "POSITIVE" },
    null,
    { label: "▼  Y−", axis: "Y", direction: "NEGATIVE" },
    null,
  ];
  for (const cell of cells) {
    if (!cell) {
      pad.append(element("span", "dpad-center"));
      continue;
    }
    const button = element("button", "dpad-button", cell.label);
    button.type = "button";
    button.setAttribute("aria-label", cell.label);
    button.disabled = disabled;
    bindHold(button, { command, axis: cell.axis, direction: cell.direction });
    pad.append(button);
  }
  return pad;
}

function renderControl(control) {
  if (control.type === "dpad") {
    const row = element("div", "dpad-row");
    row.append(renderDpad(control.command, Boolean(control.disabled)));
    return row;
  }

  if (control.type === "range") {
    const group = element("div", "range-control");
    const label = element("label", "range-label");
    label.append(element("span", "", control.label));
    const value = element("span", "range-value", `${control.value}${control.unit || ""}`);
    label.append(value);
    const input = element("input");
    input.type = "range";
    input.min = control.min;
    input.max = control.max;
    input.step = control.step || 1;
    input.value = control.value;
    input.disabled = Boolean(control.disabled);
    input.addEventListener("input", () => {
      value.textContent = `${input.value}${control.unit || ""}`;
    });
    input.addEventListener("change", () => {
      sendCommand(control.command, {
        [control.parameter]: Number(input.value),
      });
    });
    group.append(label, input);
    return group;
  }

  const styleClass = { primary: "run-demo", danger: "stop-motion" }[control.style];
  const button = element(
    "button",
    control.className || styleClass || "",
    control.label,
  );
  button.type = "button";
  button.disabled = Boolean(control.disabled);
  if (control.type === "hold") {
    bindHold(button, control);
  } else {
    button.addEventListener("click", () =>
      sendCommand(control.command, control.payload),
    );
  }
  return button;
}

function renderControlGroups(groups = []) {
  const container = element("div", "control-groups");
  for (const group of groups) {
    const section = element(
      "section",
      `control-group ${group.layout || ""}`.trim(),
    );
    if (group.title) section.append(element("h2", "control-title", group.title));
    const controls = element("div", "control-row");
    for (const control of group.controls || []) {
      controls.append(renderControl(control));
    }
    section.append(controls);
    container.append(section);
  }
  return container;
}

function renderActivity(logs = [], title = "ALERTS") {
  const panel = element("section", "alerts-panel");
  panel.id = "activity-panel";
  panel.hidden = !activityVisible;
  panel.append(element("h2", "", title));
  const body = element("div", "activity-log");
  for (const entry of logs.slice(-120)) {
    const row = element("div", "activity-entry");
    row.append(element("time", "", entry.time || ""));
    row.append(
      element(
        "span",
        `log-${String(entry.level || "info").toLowerCase()}`,
        entry.message,
      ),
    );
    body.append(row);
  }
  panel.append(body);
  requestAnimationFrame(() => {
    body.scrollTop = body.scrollHeight;
  });
  return panel;
}

function svgNode(name, attrs = {}, text = "") {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  if (text) node.textContent = text;
  return node;
}

function renderArm(arm, { compact = false } = {}) {
  const angles = arm?.angles || {};
  const width = compact ? 360 : 640;
  const height = compact ? 600 : 520;
  const scale = compact ? .65 : 1;
  const svg = svgNode("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "arm-scene",
    role: "img",
    "aria-label": "Simulated surgical arm",
  });
  const defs = svgNode("defs");
  const pattern = svgNode("pattern", {
    id: "arm-grid",
    width: "36",
    height: "36",
    patternUnits: "userSpaceOnUse",
  });
  pattern.append(
    svgNode("path", {
      d: "M 36 0 L 0 0 0 36",
      fill: "none",
      stroke: "#162230",
      "stroke-width": "1",
    }),
  );
  defs.append(pattern);
  svg.append(defs, svgNode("rect", { width, height, fill: "url(#arm-grid)" }));

  const base = { x: width / 2, y: compact ? height - 74 : 430 };
  const shoulder = { x: base.x, y: base.y - (compact ? 43 : 52) * scale };
  const radians = (degrees) => degrees * Math.PI / 180;
  const theta1 = radians(90 + (angles.shoulder ?? 220) - 180);
  const theta2 = theta1 + radians((angles.elbow ?? 120) - 180);
  const theta3 = theta2 + radians((angles.wrist ?? 220) - 180);
  const endpoint = (point, theta, length) => ({
    x: point.x + length * Math.cos(theta),
    y: point.y - length * Math.sin(theta),
  });
  const elbow = endpoint(shoulder, theta1, (compact ? 145 : 165) * scale);
  const wrist = endpoint(elbow, theta2, (compact ? 110 : 125) * scale);
  const tip = endpoint(wrist, theta3, (compact ? 45 : 55) * scale);
  const jawOpening = radians(10 + 28 * Number(angles.hand ?? 45) / 90);
  const jawStart = {
    x: tip.x - 5 * Math.cos(theta3),
    y: tip.y + 5 * Math.sin(theta3),
  };

  svg.append(
    svgNode("text", {
      x: 20,
      y: 28,
      fill: "#91a7bb",
      "font-size": "11",
      "font-weight": "700",
    }, "SIMULATED SURGICAL MANIPULATOR  /  SIDE VIEW"),
    svgNode("rect", {
      x: base.x - 48 * scale,
      y: base.y - 44 * scale,
      width: 96 * scale,
      height: 44 * scale,
      rx: 8,
      fill: "#182635",
      stroke: "#36495c",
      "stroke-width": "2",
    }),
    svgNode("ellipse", {
      cx: base.x,
      cy: base.y - 43 * scale,
      rx: 20 * scale,
      ry: 9 * scale,
      fill: "#182635",
      stroke: "#73879a",
      "stroke-width": 3,
    }),
    svgNode("ellipse", {
      cx: base.x,
      cy: base.y - 43 * scale,
      rx: 32 * scale,
      ry: 15 * scale,
      fill: "none",
      stroke: "#33485d",
      "stroke-width": 2,
    }),
  );

  const links = [
    [shoulder, elbow, 25, "#8296a9"],
    [elbow, wrist, 20, "#6f8498"],
    [wrist, tip, 12, "#a9bbcb"],
  ];
  for (const [from, to, width, color] of links) {
    svg.append(
      svgNode("line", {
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y,
        stroke: "#101924",
        "stroke-width": width * scale + 6,
        "stroke-linecap": "round",
      }),
      svgNode("line", {
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y,
        stroke: arm?.active ? color : "#536273",
        "stroke-width": Math.max(3, (width - 7) * scale),
        "stroke-linecap": "round",
      }),
    );
  }
  for (const offset of [-jawOpening, jawOpening]) {
    const jawEnd = endpoint(jawStart, theta3 + offset, 31 * scale);
    svg.append(
      svgNode("line", {
        x1: jawStart.x,
        y1: jawStart.y,
        x2: jawEnd.x,
        y2: jawEnd.y,
        stroke: arm?.active ? "#dce6ee" : "#536273",
        "stroke-width": 4 * scale,
        "stroke-linecap": "round",
      }),
    );
  }
  for (const [point, label, joint] of [
    [shoulder, "SHOULDER", "shoulder"],
    [elbow, "ELBOW", "elbow"],
    [wrist, "WRIST", "wrist"],
  ]) {
    svg.append(
      svgNode("circle", {
        cx: point.x,
        cy: point.y,
        r: 12 * scale,
        fill: "#25384a",
        stroke: "#d0dce6",
        "stroke-width": "2",
      }),
      svgNode("circle", {
        cx: point.x,
        cy: point.y,
        r: 6 * scale,
        fill: "none",
        stroke: arm?.active ? "#8296a9" : "#536273",
        "stroke-width": 3 * scale,
      }),
      svgNode("text", {
        x: point.x + 16 * scale,
        y: point.y - 8 * scale,
        fill: "#c8d7e5",
        "font-size": "12",
        "font-weight": "700",
      }, `${label}  ${Number(angles[joint] ?? 0).toFixed(0)}°`),
    );
  }
  svg.append(
    svgNode("text", {
      x: base.x,
      y: base.y - (compact ? 10 : 18) * scale,
      fill: "#c8d7e5",
      "font-size": "12",
      "font-weight": "700",
      "text-anchor": "middle",
    }, `BASE  ${Number(angles.base ?? 204).toFixed(0)}°`),
    svgNode("text", {
      x: tip.x - 16 * scale,
      y: tip.y + 14 * scale,
      "text-anchor": "end",
      fill: arm?.active ? "#52d69a" : "#536273",
      "font-size": "12",
      "font-weight": "700",
    }, `GRIPPER  ${Number(angles.hand ?? 45).toFixed(0)}°`),
  );
  return svg;
}

function drawWaveforms(timestamp) {
  if (!currentVitals?.fresh) {
    waveformFrame = 0;
    for (const canvas of appMain.querySelectorAll("canvas[data-waveform]")) {
      const context = canvas.getContext("2d");
      context?.clearRect(0, 0, canvas.width, canvas.height);
    }
    return;
  }
  waveformFrame = requestAnimationFrame(drawWaveforms);
  const heartRate = Number(currentVitals.heart_rate) || 60;
  waveformStates.ecg.rate = heartRate / 60;
  waveformStates.pleth.rate = heartRate / 60;
  waveformStates.capno.rate = Math.min(30, Math.max(8, heartRate / 4)) / 60;
  waveformStates.capno.amplitude = Math.min(60, Math.max(0, Number(currentVitals.etco2) || 0)) / 60;

  for (const canvas of appMain.querySelectorAll("canvas[data-waveform]")) {
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.floor(rect.width * ratio));
    const height = Math.max(1, Math.floor(rect.height * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, width, height);
    const state = waveformStates[canvas.dataset.waveform];
    context.strokeStyle = state.color;
    context.lineWidth = 2 * ratio;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.beginPath();
    const template = waveformTemplates[canvas.dataset.waveform];
    for (let index = 0; index < waveformBufferLength; index += 1) {
      const secondsBehind = (waveformBufferLength - 1 - index) / waveformSampleRate;
      let phase = (timestamp / 1000 * state.rate - secondsBehind * state.rate) % 1;
      if (phase < 0) phase += 1;
      const sample = template[Math.floor(phase * template.length)] * state.amplitude;
      const x = index / (waveformBufferLength - 1) * width;
      const y = height
        - ((sample - state.minimum) / (state.maximum - state.minimum)) * height;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.stroke();
  }
}

function displayedValue(vitals, key) {
  return !vitals?.fresh || vitals[key] === undefined
    ? undefined
    : Number(vitals[key]);
}

function updateVitals(vitals) {
  currentVitals = vitals;
  for (const key of ["heart_rate", "spo2", "etco2", "nibp_s", "nibp_d"]) {
    const value = displayedValue(vitals, key);
    const readout = appMain.querySelector(`[data-value="${key}"]`);
    if (readout) readout.textContent = value === undefined ? "---" : value.toFixed(0);
  }
  const systolic = displayedValue(vitals, "nibp_s");
  const diastolic = displayedValue(vitals, "nibp_d");
  const map = systolic === undefined || diastolic === undefined
    ? "---"
    : ((systolic + 2 * diastolic) / 3).toFixed(0);
  const mapReadout = appMain.querySelector(".nibp-map");
  if (mapReadout) mapReadout.textContent = `MAP: ${map}`;
  if (currentVitals?.fresh && !waveformFrame) {
    waveformFrame = requestAnimationFrame(drawWaveforms);
  }
  if (!currentVitals?.fresh && waveformFrame) {
    cancelAnimationFrame(waveformFrame);
    waveformFrame = 0;
    waveformLastFrameTime = 0;
    for (const canvas of appMain.querySelectorAll("canvas[data-waveform]")) {
      const context = canvas.getContext("2d");
      context?.clearRect(0, 0, canvas.width, canvas.height);
    }
  }
}

function resetWaveforms() {
  if (waveformFrame) cancelAnimationFrame(waveformFrame);
  waveformFrame = 0;
  currentVitals = null;
}

function renderVitals(vitals) {
  const grid = element("div", "vitals-grid");
  for (const [title, key, unit, color, waveform] of [
    ["ECG / Heart Rate", "heart_rate", "bpm", "#00e676", "ecg"],
    ["SpO₂", "spo2", "%", "#00b0ff", "pleth"],
    ["EtCO₂", "etco2", "mmHg", "#ffd600", "capno"],
  ]) {
    const panel = element("section", `vital-panel waveform-panel vital-${waveform}`);
    panel.style.setProperty("--vital-color", color);
    const heading = element("div", "vital-heading");
    heading.append(
      element("h2", "", title),
      element("span", "vital-unit", unit),
    );
    const readout = element("div", "vital-readout");
    const value = displayedValue(vitals, key);
    const number = element(
      "strong",
      "vital-number",
      value === undefined ? "---" : value.toFixed(0),
    );
    number.dataset.value = key;
    readout.append(number);
    const canvas = element("canvas");
    canvas.dataset.waveform = waveform;
    panel.append(heading, readout, canvas);
    grid.append(panel);
  }
  const pressure = element("section", "vital-panel pressure-panel");
  pressure.style.setProperty("--vital-color", "#ff7043");
  const pressureHeading = element("div", "vital-heading");
  pressureHeading.append(
    element("h2", "", "NiBP"),
    element("span", "vital-unit", "mmHg"),
  );
  const readouts = element("div", "nibp-readouts");
  for (const [label, key] of [
    ["Systolic", "nibp_s"],
    ["Diastolic", "nibp_d"],
  ]) {
    const item = element("div", "nibp-value");
    const value = displayedValue(vitals, key);
    const number = element("strong", "", value === undefined ? "---" : value.toFixed(0));
    number.dataset.value = key;
    item.append(
      number,
      element("span", "", label),
    );
    readouts.append(item);
  }
  readouts.insertBefore(element("span", "nibp-separator", "/"), readouts.children[1]);
  const systolic = displayedValue(vitals, "nibp_s");
  const diastolic = displayedValue(vitals, "nibp_d");
  const map = systolic === undefined || diastolic === undefined
    ? "---"
    : ((systolic + 2 * diastolic) / 3).toFixed(0);
  pressure.append(
    pressureHeading,
    readouts,
    element("div", "nibp-map", `MAP: ${map}`),
  );
  grid.append(pressure);
  return grid;
}

function renderBadges(data) {
  headerBadges.replaceChildren();
  for (const badge of data.header_badges || []) {
    const label = badge.label.toLowerCase();
    const value = String(badge.value);
    const stateTone = label === "status" || label === "device"
      ? { ON: "good", PAUSED: "warn", OFF: "danger" }[value]
      : label === "vitals"
      ? value === "LIVE VITALS"
        ? "good"
        : value === "MONITOR OFFLINE" || value === "APP OFFLINE"
        ? "danger"
        : "warn"
      : "";
    const item = element("span", `header-badge ${badge.tone || stateTone || ""}`.trim());
    item.dataset.label = label;
    if (label === "vitals") {
      item.append(element("strong", "header-badge-value", `● ${value}`));
    } else {
      item.append(
        element("span", "header-badge-label", badge.label),
        element("strong", "header-badge-value", value),
      );
    }
    headerBadges.append(item);
  }
}

function renderArmApp(data) {
  const body = element("div", "arm-view");
  body.append(renderArm(data.arm));
  appMain.append(body);
}

function renderPatientMonitor(data) {
  appMain.className = "app-main patient-monitor-main";
  appMain.append(renderVitals(data.vitals));
  updateVitals(data.vitals);
}

function renderArmController(data) {
  appMain.className = "app-main arm-controller";
  const teleop = element("section", "teleop-panel");
  teleop.append(element("h2", "", "TELEOPERATION  ·  END-EFFECTOR JOG"));
  const content = element("div", "teleop-content");
  const copy = element("div", "teleop-copy");
  copy.append(
    element("h3", "", "MASTER HAND CONTROL"),
    element("p", "", data.control_intro || ""),
    element("p", "teleop-note", data.control_note || ""),
  );
  const groups = data.control_groups || [];
  const planar = groups.find((group) => group.layout === "planar-pad");
  const tools = groups.find((group) => group.layout === "tool-controls");
  const demo = groups.find((group) => group.layout === "demo-controls");
  if (planar) content.append(renderControlGroups([planar]));
  if (tools) content.append(renderControlGroups([tools]));
  content.insertBefore(copy, content.firstChild);
  teleop.append(content);
  appMain.append(teleop);

  if (demo) {
    const actionBar = element("div", "action-bar");
    actionBar.append(...demo.controls.map(renderControl));
    appMain.append(actionBar);
  }
  if (data.logs?.length) {
    appMain.append(renderActivity(data.logs, data.activity_title || "ALERTS"));
  }
}

function renderGamepad(data) {
  appMain.className = "app-main gamepad-app";
  const connection = element("section", "gamepad-connection");
  connection.append(element("strong", "", "INPUT DEVICE"));
  connection.append(
    element(
      "span",
      data.input_connected ? "connected" : "",
      data.input_connected
        ? `●  ${data.gamepad_name} CONNECTED`
        : "●  NO SUPPORTED GAMEPAD CONNECTED; WAITING",
    ),
  );
  const panel = element("section", "gamepad-inputs");
  panel.append(element("h2", "", "TELEOPERATION CONTROLS"));
  for (const input of data.inputs || []) {
    const row = element("div", "gamepad-input-row");
    row.append(
      element(
        "strong",
        `gamepad-input-label${input.active ? " active" : ""}`,
        input.label,
      ),
      element("span", "gamepad-input-description", input.description),
    );
    panel.append(row);
  }
  appMain.append(
    connection,
    panel,
    element(
      "p",
      "gamepad-instruction",
      "Hold a control to jog. Return it to neutral to stop that axis.",
    ),
  );
}

function renderDeviceCards(data) {
  const grid = element("div", "device-grid");
  for (const device of data.devices || []) {
    const card = element(
      "button",
      `device-card${device.selected ? " selected" : ""}`,
      "",
    );
    card.type = "button";
    card.setAttribute("aria-pressed", String(Boolean(device.selected)));
    card.append(
      element("span", "device-name", device.name),
      element(
        "span",
        `device-status ${String(device.status || "OFF").toLowerCase()}`,
        device.status || "OFF",
      ),
    );
    card.addEventListener("click", () =>
      sendCommand("select-device", { device: device.name }),
    );
    grid.append(card);
  }
  return grid;
}

function renderOrchestrator(data) {
  appMain.className = "app-main orchestrator-app";
  const layout = element("div", "orchestrator-layout");
  layout.append(renderDeviceCards(data));
  const commandPanel = element("section", "command-panel");
  commandPanel.append(
    element("h2", "", "SEND COMMAND"),
    element("p", "", `to ${data.selected_device || "selected device"}`),
  );
  const commands = (data.control_groups || []).find(
    (group) => group.layout === "device-commands",
  );
  if (commands) {
    commandPanel.append(renderControlGroups([commands]));
  }
  layout.append(commandPanel);
  appMain.append(layout);
  appMain.append(renderActivity(data.logs, data.activity_title || "ALERTS"));
}

function renderThreat(data) {
  appMain.className = "app-main threat-app";
  const layout = element("div", `threat-layout ${data.kind}`);
  const controls = element("section", "threat-controls");
  for (const group of data.control_groups || []) {
    controls.append(renderControlGroups([group]));
  }
  layout.append(controls);

  const main = element("section", "threat-visual");
  if (data.kind === "threat-injector") {
    main.append(element("h2", "", "SURGICAL ARM"));
    main.append(renderArm(data.arm, { compact: true }));
  } else {
    main.classList.add("threat-vitals");
    main.append(
      element("h2", "threat-vitals-title", "SIMULATED VITALS · UNAUTHORIZED READOUT"),
      renderVitals(data.vitals),
    );
  }
  layout.append(main);

  const activity = element("section", "threat-activity");
  activity.append(renderActivity(data.logs, data.activity_title || "ACTIVITY"));
  layout.append(activity);
  appMain.append(layout);
  if (data.kind === "threat-exfiltrator") updateVitals(data.vitals);
}

function setActivityToggle(data) {
  activityToggle.hidden = !data.show_activity_toggle;
  const panel = $("#activity-panel");
  if (!panel) return;
  if (!data.show_activity_toggle) {
    panel.hidden = false;
    return;
  }
  panel.hidden = !activityVisible;
  const count = data.logs?.length || 0;
  const eventLabel = count === 1 ? "EVENT" : "EVENTS";
  activityToggle.textContent =
    `${activityVisible ? "▾" : "▸"}  LOG · ${count} ${eventLabel}`;
  activityToggle.onclick = () => {
    activityVisible = !activityVisible;
    panel.hidden = !activityVisible;
    activityToggle.textContent =
      `${activityVisible ? "▾" : "▸"}  LOG · ${count} ${eventLabel}`;
  };
}

function render(snapshot, connectionState = "connected") {
  const sourceData = snapshot?.data || {};
  let data = sourceData;
  if (
    connectionState !== "connected" &&
    ["patient-monitor", "threat-exfiltrator"].includes(sourceData.kind)
  ) {
    data = {
      ...sourceData,
      status: "APP OFFLINE",
      vitals_status: "DATA QUIET",
      vitals: { fresh: false },
      header_badges: (sourceData.header_badges || []).map((badge) => ({
        ...badge,
        value: badge.label === "Vitals" ? "DATA QUIET" : "APP OFFLINE",
        tone: badge.label === "Vitals" ? "warn" : "danger",
      })),
    };
  }
  const controlSignature = JSON.stringify(data.control_groups || []);
  const oldActivity = $("#activity-panel");
  if (
    data.kind === "patient-monitor" &&
    data.kind === renderedKind &&
    appMain.querySelector(".vitals-grid")
  ) {
    renderBadges(data);
    updateVitals(data.vitals);
    return;
  }
  if (
    data.kind === "threat-exfiltrator" &&
    data.kind === renderedKind &&
    controlSignature === renderedControlSignature &&
    appMain.querySelector(".vitals-grid")
  ) {
    renderBadges(data);
    updateVitals(data.vitals);
    if (oldActivity) {
      oldActivity.replaceWith(
        renderActivity(data.logs, data.activity_title || "EXFILTRATION ACTIVITY"),
      );
    }
    setActivityToggle(data);
    return;
  }
  if (
    data.kind === "arm-controller" &&
    data.kind === renderedKind &&
    controlSignature === renderedControlSignature
  ) {
    renderBadges(data);
    if (oldActivity) {
      oldActivity.replaceWith(
        renderActivity(data.logs, data.activity_title || "ALERTS"),
      );
    }
    setActivityToggle(data);
    return;
  }
  if (data.kind === "arm-controller" && data.kind === renderedKind) {
    stopActiveHolds();
  }
  if (data.kind !== renderedKind) resetWaveforms();
  renderedKind = data.kind;
  renderedControlSignature = controlSignature;
  document.body.dataset.appKind = data.kind || "";
  const title = data.title || snapshot?.title || "";
  $("#app-title").textContent = title;
  document.title = title || "RTI Connext";
  renderBadges(data);
  appMain.replaceChildren();
  appMain.className = `app-main ${data.kind || ""}`;
  if (data.kind === "arm") renderArmApp(data);
  else if (data.kind === "patient-monitor") renderPatientMonitor(data);
  else if (data.kind === "arm-controller") renderArmController(data);
  else if (data.kind === "gamepad-controller") renderGamepad(data);
  else if (data.kind === "orchestrator") renderOrchestrator(data);
  else if (data.kind === "threat-injector" || data.kind === "threat-exfiltrator") {
    renderThreat(data);
  }
  appFooter.hidden = !data.footer;
  setActivityToggle(data);
}

client.subscribe(render);
client.start();
