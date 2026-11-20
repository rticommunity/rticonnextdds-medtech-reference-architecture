import { createClient } from "/sdk/client.js";

const client = createClient({ transport: "sse" });
const $ = (selector) => document.querySelector(selector);
const appMain = $("#app-main");
const headerBadges = $("#header-badges");
const headerDevice = $("#header-device");
const headerDeviceValue = headerDevice.querySelector("strong");
const headerSecurity = $("#header-security");
const headerSecurityPath = headerSecurity.querySelector("path");
const activityToggle = $("#activity-toggle");
const appFooter = $("#app-footer");
const ddsTopics = $("#dds-topics");
let displayedTopicKind;
// Keep aligned with ParticipantLibrary.xml and ThreatParticipants.xml.
const controllerTopics = {
  Publish: ["t/robot/arm/control", "t/robot/tool/control", "t/device/status", "t/device/heartbeat"],
  Subscribe: ["t/device/command", "t/robot/arm/status", "t/robot/arm/telemetry"],
};
const topicsByKind = {
  arm: {
    Publish: ["t/device/status", "t/device/heartbeat", "t/robot/arm/status", "t/robot/arm/telemetry"],
    Subscribe: ["t/robot/arm/control", "t/robot/tool/control", "t/device/command"],
  },
  "arm-controller": controllerTopics,
  "gamepad-controller": controllerTopics,
  orchestrator: {
    Publish: ["t/device/command"],
    Subscribe: ["t/device/status", "t/device/heartbeat"],
  },
  "patient-monitor": {
    Publish: ["t/device/status", "t/device/heartbeat"],
    Subscribe: ["t/device/command", "t/patient/vitals"],
  },
  "threat-injector": { Publish: ["t/robot/arm/control", "t/device/command"] },
  "threat-exfiltrator": { Subscribe: ["t/patient/vitals"] },
};
let pendingCommand = Promise.resolve();
let nextHoldId = 0;
const activeHolds = new Map();
const controlNodes = new Map();
const activityEntries = new WeakMap();
let currentVitals = null;
let waveformFrame = 0;
let activityVisible = true;
let renderedKind = null;
let renderedControlSignature = null;
let renderedGamepadSignature = null;
let sceneRendererPromise = null;
let sceneComponentId = null;
let pendingSceneComponent = null;
let sceneReconcileRunning = false;
let telemetryPublicationSequence = null;
let telemetryPublicationTimer = null;
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

function updateText(node, value) {
  const text = String(value);
  if (node.textContent === text) return;
  // Keep text hit targets intact during native WebKit pointer gestures.
  if (node.firstChild?.nodeType === Node.TEXT_NODE) {
    node.firstChild.nodeValue = text;
  } else {
    node.textContent = text;
  }
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
  for (const hold of [...activeHolds.values()]) hold.stop();
}

window.addEventListener("blur", stopActiveHolds);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopActiveHolds();
});

function bindHold(button, control) {
  const holdId = nextHoldId++;
  let pressed = false;
  let refreshTimer = 0;
  const command = control.command;
  const payload = control.payload ?? control.rate_payload
    ?? (control.axis ? { axis: control.axis, direction: control.direction } : {});
  const stopPayload = control.stop_payload ?? (control.axis
    ? { axis: control.axis, direction: "STOPPED" }
    : zeroPayload(payload));

  const stop = () => {
    if (!pressed) return;
    pressed = false;
    window.clearInterval(refreshTimer);
    activeHolds.delete(holdId);
    publishHeldPayload(command, stopPayload);
  };

  const start = (event) => {
    event.preventDefault();
    if (pressed || button.disabled) return;
    pressed = true;
    if (event.pointerId !== undefined) {
      button.setPointerCapture?.(event.pointerId);
    }
    activeHolds.set(holdId, { button, command, payload, stopPayload, stop });
    publishHeldPayload(command, payload);
    refreshTimer = window.setInterval(() => {
      if (pressed) publishHeldPayload(command, payload);
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

function zeroPayload(value) {
  if (Array.isArray(value)) {
    return value.map((item) => typeof item === "number" ? 0 : zeroPayload(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        typeof item === "number" ? 0 : zeroPayload(item),
      ]),
    );
  }
  return value;
}

function addPayloadValues(left, right) {
  if (typeof left === "number" && typeof right === "number") return left + right;
  if (Array.isArray(left) && Array.isArray(right) && left.length === right.length) {
    return left.map((item, index) => addPayloadValues(item, right[index]));
  }
  if (left && right && typeof left === "object" && typeof right === "object"
      && !Array.isArray(left) && !Array.isArray(right)) {
    return Object.fromEntries(
      [...new Set([...Object.keys(left), ...Object.keys(right)])].map((key) => [
        key,
        key in left && key in right
          ? addPayloadValues(left[key], right[key])
          : left[key] ?? right[key],
      ]),
    );
  }
  return left ?? right;
}

function publishHeldPayload(command, fallback) {
  if (fallback && typeof fallback === "object" && "axis" in fallback) {
    sendCommand(command, fallback);
    return;
  }
  const active = [...activeHolds.values()]
    .filter((hold) => hold.command === command)
    .map((hold) => hold.payload);
  const payload = active.reduce(addPayloadValues, null) ?? fallback;
  sendCommand(command, active.length ? payload : fallback);
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

function controlKey(control) {
  const { disabled, value, label, className, style, ...definition } = control;
  return JSON.stringify(definition);
}

function controlClassName(control) {
  return control.className
    || { primary: "run-demo", danger: "stop-motion" }[control.style] || "";
}

function updateControls(groups) {
  for (const control of groups.flatMap((group) => group.controls || [])) {
    const node = controlNodes.get(controlKey(control));
    if (control.disabled) {
      for (const hold of [...activeHolds.values()]) {
        if (node.contains(hold.button)) hold.stop();
      }
    }
    if (control.type === "dpad") {
      for (const button of node.querySelectorAll("button")) {
        button.disabled = Boolean(control.disabled);
      }
    } else if (control.type === "range") {
      const input = node.querySelector("input");
      input.disabled = Boolean(control.disabled);
      updateText(node.querySelector(".range-label > span"), control.label);
      if (document.activeElement !== input && !input.matches(":active")) {
        input.value = control.value;
        updateText(node.querySelector(".range-value"), `${control.value}${control.unit || ""}`);
      }
    } else {
      node.disabled = Boolean(control.disabled);
      node.className = controlClassName(control);
      updateText(node, control.label);
    }
  }
}

function renderControl(control) {
  if (control.type === "dpad") {
    const row = element("div", "dpad-row");
    row.append(renderDpad(control.command, Boolean(control.disabled)));
    controlNodes.set(controlKey(control), row);
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
      updateText(value, `${input.value}${control.unit || ""}`);
    });
    input.addEventListener("change", () => {
      sendCommand(control.command, {
        [control.parameter]: Number(input.value),
      });
    });
    group.append(label, input);
    controlNodes.set(controlKey(control), group);
    return group;
  }

  const button = element(
    "button",
    controlClassName(control),
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
  controlNodes.set(controlKey(control), button);
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
  panel.append(body);
  updateActivity(logs, title, panel);
  requestAnimationFrame(() => { body.scrollTop = body.scrollHeight; });
  return panel;
}

function updateActivity(logs = [], title = "ALERTS", panel = $("#activity-panel")) {
  if (!panel) return;
  updateText(panel.querySelector("h2"), title);
  const body = panel.querySelector(".activity-log");
  const entries = logs.slice(-120);
  const keys = entries.map((entry) => JSON.stringify(entry));
  const previous = activityEntries.get(body) || [];
  if (JSON.stringify(keys) === JSON.stringify(previous)) return;
  const followTail = body.scrollHeight - body.scrollTop - body.clientHeight <= 4;
  const scrollTop = body.scrollTop;
  const oldHeight = body.scrollHeight;
  let overlap = Math.min(previous.length, keys.length);
  while (overlap && !previous.slice(-overlap).every((key, index) => key === keys[index])) {
    overlap--;
  }
  for (let index = 0; index < previous.length - overlap; index++) {
    body.firstElementChild.remove();
  }
  const removedHeight = oldHeight - body.scrollHeight;
  for (const entry of entries.slice(overlap)) {
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
  activityEntries.set(body, keys);
  body.scrollTop = followTail ? body.scrollHeight : Math.max(0, scrollTop - removedHeight);
}

function renderArmPreview(arm, previewLabel) {
  const panel = element("section", "arm-command-preview");
  panel.append(
    element("h2", "", previewLabel || "COMMAND PREVIEW · NOT OBSERVED ARM FEEDBACK"),
    element(
      "p",
      "",
      "This local simulation preview is not observed arm feedback and does not prove DDS actuation.",
    ),
  );
  panel.append(element("p", "preview-error"));
  const row = element("div", "command-preview-rates");
  for (let index = 0; index < 3; index++) row.append(element("span"));
  const state = element("div", "command-preview-state");
  for (let index = 0; index < 3; index++) state.append(element("span"));
  panel.append(row, state);
  updateArmPreview(arm, previewLabel, panel);
  return panel;
}

function updateArmPreview(arm, previewLabel, panel = $(".arm-command-preview")) {
  updateText(panel.querySelector("h2"), previewLabel || "COMMAND PREVIEW · NOT OBSERVED ARM FEEDBACK");
  const error = panel.querySelector(".preview-error");
  error.hidden = !arm?.error;
  updateText(error, arm?.error ? `Preview unavailable: ${arm.error}. DDS injection remains available.` : "");
  const rates = arm?.rates || arm?.command || arm || {};
  const rateLabels = [
    ["Linear", rates.linear_velocity, "m/s"],
    ["Angular", rates.angular_velocity, "rad/s"],
    ["Jaw opening", rates.opening_rate, "m/s"],
  ].map(([label, value, unit]) => {
    const formatted = label === "Linear"
      ? formatVector(value, ["x", "y", "z"], 3)
      : label === "Angular"
        ? formatVector(value, ["x", "y", "z"], 3)
        : Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "---";
    return `${label}: ${formatted} ${unit}`;
  });
  panel.querySelectorAll(".command-preview-rates > span").forEach((node, index) => {
    updateText(node, rateLabels[index]);
  });
  const pose = arm?.pose || {};
  const stateLabels = [
    `Simulated TCP position · m: ${formatVector(pose.position || arm?.position, ["x", "y", "z"], 3)}`,
    `Simulated TCP orientation · x y z w: ${formatVector(pose.orientation || arm?.orientation, ["x", "y", "z", "w"], 3)}`,
    `Simulated jaw gap · m: ${arm?.opening_width != null && Number.isFinite(Number(arm.opening_width)) ? Number(arm.opening_width).toFixed(3) : "---"}`,
  ];
  panel.querySelectorAll(".command-preview-state > span").forEach((node, index) => {
    updateText(node, stateLabels[index]);
  });
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
  const badges = data.header_badges || [];
  headerBadges.hidden = !badges.length;
  for (const [index, badge] of badges.entries()) {
    const label = badge.label.toLowerCase();
    const value = String(badge.value);
    const stateTone = label === "vitals"
      ? value === "LIVE VITALS"
        ? "good"
        : value === "MONITOR OFFLINE" || value === "APP OFFLINE"
        ? "danger"
        : "warn"
      : "";
    let item = headerBadges.children[index];
    if (!item || item.dataset.label !== label) {
      const previous = item;
      item = element("span");
      item.dataset.label = label;
      if (label !== "vitals") item.append(element("span", "header-badge-label", badge.label));
      item.append(element("strong", "header-badge-value"));
      if (previous) previous.replaceWith(item);
      else headerBadges.append(item);
    }
    item.className = `header-badge ${badge.tone || stateTone || ""}`.trim();
    updateText(item.querySelector(".header-badge-value"), label === "vitals" ? `● ${value}` : value);
  }
  while (headerBadges.children.length > badges.length) headerBadges.lastElementChild.remove();
}

function renderSharedStatus(data, connected) {
  const status = data.device_status;
  const value = connected ? status : "APP OFFLINE";
  headerDevice.hidden = !status;
  headerDevice.className = `header-badge ${
    { ON: "good", PAUSED: "warn", OFF: "danger", ERROR: "danger", "APP OFFLINE": "danger" }[value] || "muted"
  }`;
  updateText(headerDeviceValue, value ?? "");

  const enabled = connected ? data.dds_security : undefined;
  const mode = enabled === true ? "enabled" : enabled === false ? "disabled" : "unknown";
  if (headerSecurity.dataset.mode === mode) return;
  headerSecurity.dataset.mode = mode;
  const label = mode === "unknown" ? "DDS security status unavailable" : `DDS Security ${mode}`;
  headerSecurity.setAttribute("aria-label", label);
  headerSecurity.title = label;
  headerSecurityPath.setAttribute("d", {
    enabled: "M5 11h14v10H5z M8 11V7a4 4 0 0 1 8 0v4",
    disabled: "M5 11h14v10H5z M8 11V7a4 4 0 0 1 8 0",
    unknown: "M5 12h14",
  }[mode]);
}

function renderArmApp(data) {
  const body = element("div", "arm-view");
  const scenePanel = element("section", "arm-scene-panel");
  const heading = element("div", "arm-scene-heading");
  heading.append(
    element("h2", "", "ARTICULATED ARM · SIMULATION"),
    element("span", "arm-scene-status", "Connecting to 3D renderer"),
  );
  const host = element("div", "arm-scene-host");
  host.id = "arm-scene-host";
  const motion = element("p", "arm-motion-status");
  motion.setAttribute("role", "status");
  scenePanel.append(heading, host, motion);
  body.append(scenePanel);
  if (data.arm_feedback || data.feedback) {
    body.append(renderActualFeedback(data.arm_feedback || data.feedback));
  }
  appMain.append(body);
  updateArmMotionStatus(data);
}

function updateArmMotionStatus(data) {
  const motion = $(".arm-motion-status");
  if (!motion) return;
  const message = data.arm?.error || "";
  motion.textContent = message;
  motion.title = message;
  motion.classList.toggle("active", Boolean(message));
}

function findSceneComponent(snapshot) {
  for (const card of snapshot?.cards || []) {
    const component = (card.components || []).find((item) => item.type === "scene3d");
    if (component) return component;
  }
  return null;
}

function disposeArmScene() {
  const oldId = sceneComponentId;
  sceneComponentId = null;
  pendingSceneComponent = null;
  if (!oldId) return;
  if (sceneRendererPromise) {
    sceneRendererPromise.then((renderer) => renderer.disposeScene3d(oldId)).catch(() => {});
  }
}

function reconcileArmScene(snapshot) {
  const component = findSceneComponent(snapshot);
  if (!component) return;
  if (sceneComponentId && sceneComponentId !== component.id) disposeArmScene();
  sceneComponentId = component.id;
  pendingSceneComponent = component;
  if (sceneReconcileRunning) return;
  sceneReconcileRunning = true;
  sceneRendererPromise ||= import("/sdk/runtime3d.js");
  sceneRendererPromise
    .then(async (renderer) => {
      while (pendingSceneComponent) {
        const next = pendingSceneComponent;
        pendingSceneComponent = null;
        const host = $("#arm-scene-host");
        if (!host || !host.isConnected || next.id !== sceneComponentId) continue;
        await renderer.reconcileScene3d(next, host, {
          materialMode: "original",
          showNodeList: false,
          reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
          onLoadState: (state) => {
            const label = $(".arm-scene-status");
            if (label) {
              label.textContent = state === "loaded"
                ? "3D model loaded · drag: orbit · right or Shift-drag: pan · scroll: zoom"
                : state === "failed" ? "3D unavailable · text fallback active" : state;
            }
          },
          onSelection: () => {},
        });
        for (const [action, label, description] of [
          ["reset-camera", "Reset camera", "Restore the initial camera view. Does not reset the arm position."],
          ["zoom-model", "Fit arm", "Center and fit the model while keeping the current viewing direction."],
        ]) {
          const button = host.querySelector(`[data-action="${action}"]`);
          if (button) {
            if (button.textContent !== label) button.textContent = label;
            button.title = description;
            button.disabled = host.classList.contains("sdk-scene3d-fallback");
            if (!button.dataset.armCameraAction) {
              button.dataset.armCameraAction = action;
              button.addEventListener("click", () => {
                if (action === "reset-camera") {
                  renderer.setScene3dCamera(next.id, {
                    position: next.data.camera.position,
                    target: next.data.camera.target,
                    up: [0, 1, 0],
                  });
                }
                let status = host.querySelector(".camera-action-status");
                if (!status) {
                  status = element("span", "camera-action-status");
                  status.setAttribute("role", "status");
                  button.parentElement.append(status);
                }
                status.textContent = action === "reset-camera"
                  ? "Camera reset; arm position unchanged."
                  : "Arm fitted to the current view.";
              });
            }
          }
          const toolbar = host.querySelector(".sdk-scene3d-toolbar");
          if (toolbar && !toolbar.querySelector("[data-arm-view]")) {
            // Model Z-up is mapped to renderer Y-up by the GLB root transform.
            for (const [label, position, up] of [
              ["Side view", [0, 0.25, 1.2], [0, 1, 0]],
              ["Top view", [0, 1.45, 0], [0, 0, -1]],
            ]) {
              const button = element("button", "sdk-button", label);
              button.type = "button";
              button.dataset.armView = label;
              button.title = `${label} relative to the fixed arm base; does not change control axes.`;
              button.addEventListener("click", () => {
                renderer.setScene3dCamera(next.id, { position, target: [0, 0.25, 0], up });
                toolbar.querySelector('[data-action="zoom-model"]').click();
                toolbar.querySelector(".camera-action-status").textContent =
                  `${label}; arm position unchanged.`;
              });
              toolbar.insertBefore(button, toolbar.querySelector(".camera-action-status"));
            }
          }
          for (const button of host.querySelectorAll("[data-arm-view]")) {
            button.disabled = host.classList.contains("sdk-scene3d-fallback");
          }
        }
      }
    })
    .catch((error) => {
      const host = $("#arm-scene-host");
      if (!host) return;
      host.classList.add("arm-scene-fallback");
      host.textContent = `3D renderer unavailable: ${error.message}`;
      const label = $(".arm-scene-status");
      if (label) label.textContent = "3D unavailable · text fallback active";
    })
    .finally(() => {
      sceneReconcileRunning = false;
      if (pendingSceneComponent) reconcileArmScene(snapshot);
    });
}

function feedbackVector(value, keys) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return keys.map((key) => value[key]);
  return null;
}

function formatVector(value, keys, digits) {
  const components = feedbackVector(value, keys);
  if (!components || components.length !== keys.length
      || components.some((component) => !Number.isFinite(Number(component)))) return "---";
  return components.map((component) => Number(component).toFixed(digits)).join("  ");
}

function renderActualFeedback(feedback = {}) {
  const panel = element("section", "actual-feedback");
  const heading = element("h2");
  const publication = element("span", "telemetry-publication");
  publication.setAttribute("role", "img");
  heading.append(element("span", "feedback-heading"), publication);
  panel.append(
    heading,
    element("div", "feedback-readiness", ""),
    element("div", "feedback-freshness", ""),
  );
  for (const [label, key] of [
    ["TCP position · m", "position"],
    ["TCP orientation · x y z w", "orientation"],
    ["Total jaw gap · m", "opening_width"],
  ]) {
    const row = element("div", "feedback-row");
    row.append(element("span", "feedback-label", label), element("strong", "feedback-value", "---"));
    row.dataset.feedback = key;
    panel.append(row);
  }
  updateActualFeedback(feedback, panel);
  return panel;
}

function updateActualFeedback(feedback = {}, panel = $(".actual-feedback")) {
  if (!panel) return;
  const freshness = feedback.freshness || {};
  const telemetryFresh = freshness.telemetry === true;
  const reported = feedback.source === "reported";
  const displayValues = reported || telemetryFresh;
  const statusKnown = feedback.status_known === true;
  panel.querySelector(".feedback-heading").textContent =
    reported ? "REPORTED TELEMETRY" : "OBSERVED ARM FEEDBACK";
  const publication = panel.querySelector(".telemetry-publication");
  publication.hidden = !reported;
  const setPublishing = (active) => {
    publication.classList.toggle("publishing", active);
    publication.setAttribute("aria-label", active
      ? "Publishing telemetry" : "No recent telemetry publication");
    publication.title = publication.getAttribute("aria-label");
  };
  const sequence = feedback.publication_sequence;
  if (!reported || !Number.isSafeInteger(sequence) || sequence <= 0) {
    clearTimeout(telemetryPublicationTimer);
    telemetryPublicationSequence = null;
    setPublishing(false);
  } else if (sequence !== telemetryPublicationSequence) {
    telemetryPublicationSequence = sequence;
    clearTimeout(telemetryPublicationTimer);
    setPublishing(true);
    telemetryPublicationTimer = setTimeout(() => setPublishing(false), 500);
  }
  const readiness = panel.querySelector(".feedback-readiness");
  const freshReadout = panel.querySelector(".feedback-freshness");
  if (readiness) readiness.textContent =
    `${reported ? "Arm readiness" : "Readiness (last known)"}: ${statusKnown ? feedback.readiness || "UNKNOWN" : "UNKNOWN"}`;
  if (freshReadout) {
    freshReadout.hidden = reported;
    freshReadout.textContent =
      `Telemetry ${telemetryFresh ? "FRESH" : "STALE"}`;
    freshReadout.className = `feedback-freshness ${telemetryFresh ? "fresh" : "stale"}`;
  }
  const values = {
    position: displayValues ? formatVector(feedback.position, ["x", "y", "z"], 3) : "---",
    orientation: displayValues
      ? formatVector(feedback.orientation, ["x", "y", "z", "w"], 3)
      : "---",
    opening_width: displayValues && feedback.opening_width != null
      && Number.isFinite(Number(feedback.opening_width))
      ? Number(feedback.opening_width).toFixed(3)
      : "---",
  };
  for (const [key, value] of Object.entries(values)) {
    const row = panel.querySelector(`[data-feedback="${key}"] .feedback-value`);
    if (row) row.textContent = value;
  }
}

window.addEventListener("pagehide", disposeArmScene);

function renderPatientMonitor(data) {
  appMain.className = "app-main patient-monitor-main";
  appMain.append(renderVitals(data.vitals));
  updateVitals(data.vitals);
}

function renderArmController(data) {
  appMain.className = "app-main arm-controller";
  const teleop = element("section", "teleop-panel");
  teleop.append(element("h2", "", "TELEOPERATION  ·  SIX-AXIS BASE-FRAME VELOCITY HOLD"));
  const content = element("div", "teleop-content");
  const copy = element("div", "teleop-copy");
  copy.append(
    element("h3", "", "MASTER HAND CONTROL"),
    element("p", "", data.control_intro || ""),
    element("p", "teleop-note", data.control_note || ""),
  );
  const groups = data.control_groups || [];
  const demo = groups.find((group) => group.layout === "demo-controls");
  for (const group of groups) {
    if (group !== demo) content.append(renderControlGroups([group]));
  }
  content.insertBefore(copy, content.firstChild);
  teleop.append(content);
  appMain.append(teleop);

  if (demo) {
    const actionBar = element("div", "action-bar");
    actionBar.append(...demo.controls.map(renderControl));
    appMain.append(actionBar);
  }
  appMain.append(renderActualFeedback(data.feedback));
  appMain.append(renderActivity(data.logs, data.activity_title || "ALERTS"));
}

function renderGamepad(data) {
  appMain.className = "app-main gamepad-app";
  const connection = element("section", "gamepad-connection");
  connection.append(element("strong", "", "INPUT DEVICE"));
  connection.append(element("span"));
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
      "Hold a control to command a base-frame velocity (+Z up). Directions do not follow the camera or tool. Return it to neutral to stop.",
    ),
    renderActualFeedback(data.feedback),
  );
  updateGamepad(data);
}

function updateGamepad(data) {
  const connection = appMain.querySelector(".gamepad-connection > span");
  connection.classList.toggle("connected", Boolean(data.input_connected));
  updateText(connection, data.input_connected
    ? `●  ${data.gamepad_name} CONNECTED`
    : "●  NO SUPPORTED GAMEPAD CONNECTED; WAITING");
  appMain.querySelectorAll(".gamepad-input-row").forEach((row, index) => {
    const input = data.inputs[index];
    row.querySelector(".gamepad-input-label").classList.toggle("active", Boolean(input.active));
    updateText(row.querySelector(".gamepad-input-description"), input.description);
  });
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
    card.dataset.device = device.name;
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

function updateOrchestrator(data) {
  for (const device of data.devices || []) {
    const card = appMain.querySelector(`.device-card[data-device="${device.name}"]`);
    card.classList.toggle("selected", Boolean(device.selected));
    card.setAttribute("aria-pressed", String(Boolean(device.selected)));
    const status = card.querySelector(".device-status");
    const label = device.status || "OFF";
    status.className = `device-status ${String(label).toLowerCase()}`;
    updateText(status, label);
  }
  const target = appMain.querySelector(".command-panel > p");
  const label = `to ${data.selected_device || "selected device"}`;
  updateText(target, label);
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
    main.append(renderArmPreview(data.arm_preview || data.arm, data.preview_label));
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
  const label = `${activityVisible ? "▾" : "▸"}  LOG · ${count} ${eventLabel}`;
  updateText(activityToggle, label);
  activityToggle.onclick = () => {
    activityVisible = !activityVisible;
    setActivityToggle(data);
  };
}

function renderDdsTopics(kind) {
  if (kind === displayedTopicKind) return;
  displayedTopicKind = kind;
  const topics = Object.hasOwn(topicsByKind, kind) ? topicsByKind[kind] : null;
  ddsTopics.hidden = !topics;
  ddsTopics.open = false;
  const rows = [];
  for (const [direction, names] of Object.entries(topics || {})) {
    for (const name of names) {
      const row = element("li");
      const arrow = element("span", `dds-topic-arrow ${direction.toLowerCase()}`,
        direction === "Publish" ? "↑" : "↓");
      arrow.setAttribute("role", "img");
      arrow.setAttribute("aria-label", direction);
      arrow.title = direction;
      row.append(arrow, element("code", "", name));
      rows.push(row);
    }
  }
  ddsTopics.querySelector("ul").replaceChildren(...rows);
}

function render(snapshot, connectionState = "connected") {
  const sourceData = snapshot?.data || {};
  renderDdsTopics(sourceData.kind);
  renderSharedStatus(sourceData, connectionState === "connected");
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
  const controlSignature = JSON.stringify((data.control_groups || []).map((group) => [
    group.title, group.layout, (group.controls || []).map(controlKey),
  ]));
  const gamepadSignature = JSON.stringify((data.inputs || []).map((input) => input.label));
  if (
    data.kind === "arm" &&
    data.kind === renderedKind &&
    appMain.querySelector(".arm-view")
  ) {
    renderBadges(data);
    updateArmMotionStatus(data);
    updateActualFeedback(data.arm_feedback || data.feedback);
    reconcileArmScene(snapshot);
    return;
  }
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
    ["threat-injector", "threat-exfiltrator", "orchestrator", "arm-controller"].includes(data.kind) &&
    data.kind === renderedKind &&
    controlSignature === renderedControlSignature
  ) {
    renderBadges(data);
    updateControls(data.control_groups || []);
    if (data.kind === "threat-injector") {
      updateArmPreview(data.arm_preview || data.arm, data.preview_label);
    } else if (data.kind === "threat-exfiltrator") {
      updateVitals(data.vitals);
    } else if (data.kind === "orchestrator") {
      updateOrchestrator(data);
    } else {
      updateActualFeedback(data.feedback);
    }
    const activityTitle = data.kind.startsWith("threat-") ? "ACTIVITY" : "ALERTS";
    updateActivity(data.logs, data.activity_title || activityTitle);
    setActivityToggle(data);
    return;
  }
  if (
    data.kind === "gamepad-controller" &&
    data.kind === renderedKind &&
    gamepadSignature === renderedGamepadSignature
  ) {
    renderBadges(data);
    updateActualFeedback(data.feedback);
    updateGamepad(data);
    return;
  }
  stopActiveHolds();
  if (data.kind !== renderedKind && renderedKind === "arm") disposeArmScene();
  if (data.kind !== renderedKind) resetWaveforms();
  renderedKind = data.kind;
  renderedControlSignature = controlSignature;
  renderedGamepadSignature = data.kind === "gamepad-controller"
    ? gamepadSignature
    : null;
  document.body.dataset.appKind = data.kind || "";
  const title = data.title || snapshot?.title || "";
  $("#app-title").textContent = title;
  document.title = title || "RTI Connext";
  renderBadges(data);
  appMain.replaceChildren();
  controlNodes.clear();
  appMain.className = `app-main ${data.kind || ""}`;
  if (data.kind === "arm") {
    renderArmApp(data);
    reconcileArmScene(snapshot);
  }
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
