// Orchestrator web UI — polls the embedded HTTP server for state and posts
// commands back over plain HTTP. Polling (instead of WebSocket) is used
// deliberately so this works reliably behind simple HTTP proxies (e.g. a
// cloud-IDE port-forwarding proxy) that may not support the WS upgrade.

const DEVICE_LABELS = {
    ARM_CONTROLLER: "Arm Controller",
    PATIENT_SENSOR: "Patient Sensor",
    ARM: "Arm",
    PATIENT_MONITOR: "Patient Monitor",
};

const DEVICE_ORDER = new Map(Object.keys(DEVICE_LABELS).map((id, index) => [id, index]));

const POLL_INTERVAL_MS = 100;

let selectedDevice = null;
let lastAlertText = "";
let shutdownHandled = false;
let consecutiveFailures = 0;
let launcherOrigin = null;
let nextRequestId = 0;
const startRequests = new Map();
const startingDevices = new Map();
const pendingCommands = new Set();
const commandErrors = new Map();
const deviceStatuses = new Map();
const deviceCards = new Map();
const stoppingDevices = new Set();

const devicesEl = document.getElementById("devices");
const alertsEl = document.getElementById("alerts");
const selectedDeviceEl = document.getElementById("selected-device");
const securityEl = document.getElementById("security-indicator");
const btnStart = document.getElementById("btn-start");
const btnPause = document.getElementById("btn-pause");
const btnOff = document.getElementById("btn-off");
const commandStatus = document.getElementById("command-status");

window.addEventListener("message", event => {
    if (event.source !== window.parent) return;
    if (event.data?.type === "medtech-launcher-ready") {
        launcherOrigin = event.origin;
    } else if (event.origin === launcherOrigin && event.data?.type === "medtech-device-start-result") {
        startRequests.get(event.data.requestId)?.(event.data.status);
    }
});

function requestStart(device) {
    return new Promise((resolve, reject) => {
        const requestId = ++nextRequestId;
        const timer = setTimeout(() => {
            startRequests.delete(requestId);
            reject(new Error("Launcher did not respond"));
        }, 5000);
        startRequests.set(requestId, status => {
            clearTimeout(timer);
            startRequests.delete(requestId);
            resolve(status);
        });
        window.parent.postMessage({ type: "medtech-device-start", device, requestId, stopped: stoppingDevices.has(device) || deviceStatuses.get(device) === "OFF" }, launcherOrigin);
    });
}

function updateCommands() {
    const pending = startingDevices.has(selectedDevice);
    const sending = pendingCommands.has(selectedDevice);
    [btnStart, btnPause, btnOff].forEach(button => {
        button.disabled = !selectedDevice || pending || sending;
    });
    btnStart.textContent = pending ? "Starting..." : "Start";
    commandStatus.textContent = sending ? "Sending command..." : (commandErrors.get(selectedDevice) || "");
}

function handleShutdown() {
    if (shutdownHandled) return;
    shutdownHandled = true;
    const overlay = document.createElement("div");
    overlay.id = "shutdown-overlay";
    overlay.innerHTML = "Orchestrator shut down<span>You can close this tab.</span>";
    document.body.appendChild(overlay);
    setTimeout(() => window.close(), 1200);
}

function statusClass(status) {
    if (status.indexOf("ON") !== -1) return "status-on";
    if (status.indexOf("PAUSED") !== -1) return "status-paused";
    return "status-off";
}

function createDeviceCard(id) {
    const card = document.createElement("div");
    card.className = "device-card";
    card.dataset.deviceId = id;

    const name = document.createElement("div");
    name.className = "device-name";
    name.textContent = DEVICE_LABELS[id] || id;

    const badge = document.createElement("span");
    card.appendChild(name);
    card.appendChild(badge);
    card.addEventListener("click", () => selectDevice(id));
    return { card, badge };
}

function renderDevices(devices) {
    const orderedDevices = [...devices].sort((left, right) =>
        (DEVICE_ORDER.get(left.id) ?? DEVICE_ORDER.size) - (DEVICE_ORDER.get(right.id) ?? DEVICE_ORDER.size));
    const visibleIds = new Set(devices.map(device => device.id));
    for (const [id, { card }] of deviceCards) {
        if (!visibleIds.has(id)) {
            devicesEl.removeChild(card);
            deviceCards.delete(id);
        }
    }

    // Keep existing click targets attached across state polls.
    orderedDevices.forEach((device, index) => {
        deviceStatuses.set(device.id, device.status);
        const deadline = startingDevices.get(device.id);
        if (deadline && (device.status.includes("ON") || device.status.includes("PAUSED") || Date.now() > deadline)) {
            startingDevices.delete(device.id);
            if (Date.now() > deadline) commandErrors.set(device.id, "Device startup timed out");
        }
        if (!deviceCards.has(device.id)) deviceCards.set(device.id, createDeviceCard(device.id));
        const { card, badge } = deviceCards.get(device.id);
        card.classList.toggle("selected", device.id === selectedDevice);
        const starting = startingDevices.has(device.id);
        const status = starting ? "STARTING" : device.status;
        if (badge.textContent !== status) {
            badge.textContent = status;
            badge.className = "status-badge " + (starting ? "status-paused" : statusClass(device.status));
        }
        if (devicesEl.children[index] !== card) {
            devicesEl.insertBefore(card, devicesEl.children[index] || null);
        }
    });
    updateCommands();
}

function selectDevice(deviceId) {
    selectedDevice = deviceId;
    selectedDeviceEl.textContent = DEVICE_LABELS[deviceId] || deviceId;
    for (const [id, { card }] of deviceCards) {
        card.classList.toggle("selected", id === deviceId);
    }
    updateCommands();
}

function renderSecurity(security) {
    if (!security) {
        securityEl.textContent = "";
        return;
    }
    if (security.threat) {
        securityEl.textContent = "SECURITY THREAT";
        securityEl.className = "security-threat-on";
    } else if (security.enabled) {
        securityEl.textContent = "SECURITY: OK";
        securityEl.className = "security-ok";
    } else {
        securityEl.textContent = "UNSECURE MODE";
        securityEl.className = "security-unsecure";
    }
}

function formatAlert(message) {
    return message.replace(/\b(?:DeviceCommands|DeviceType|DeviceStatuses)::/g, "")
    .replace(/[ \t]+/g, " ").trimEnd()
    .replace(/ \(web mode\)$/, "");
}

function renderAlerts(alerts) {
    const text = alerts.map(formatAlert).join("\n");
    if (text === lastAlertText) return;
    lastAlertText = text;
    alertsEl.textContent = text;
    alertsEl.scrollTop = alertsEl.scrollHeight;
}

async function pollState() {
    try {
        const res = await fetch("api/state", { cache: "no-store" });
        if (!res.ok) return;
        const state = await res.json();
        consecutiveFailures = 0;
        renderDevices(state.devices || []);
        renderSecurity(state.security);
        renderAlerts(state.alerts || []);
    } catch (err) {
        console.warn("Failed to fetch /api/state:", err);
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) handleShutdown();
    } finally {
        if (!shutdownHandled) setTimeout(pollState, POLL_INTERVAL_MS);
    }
}

async function sendCommand(command) {
    if (!selectedDevice) return;
    const device = selectedDevice;
    if (startingDevices.has(device) || pendingCommands.has(device)) return;
    pendingCommands.add(device);
    commandErrors.delete(device);
    updateCommands();
    if (command === "SHUTDOWN") stoppingDevices.add(device);
    try {
        if (command === "START" && launcherOrigin) {
            startingDevices.set(device, Date.now() + 15000);
            updateCommands();
            const status = await requestStart(device);
            if (status === "starting" || status === "running") stoppingDevices.delete(device);
            if (status === "starting") return;
            startingDevices.delete(device);
            if (status !== "running") throw new Error("Device cannot be started: " + status);
        }
        const response = await fetch("api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device, command }),
        });
        if (!response.ok) throw new Error("Command failed (" + response.status + ")");
    } catch (err) {
        startingDevices.delete(device);
        if (command === "SHUTDOWN") stoppingDevices.delete(device);
        commandErrors.set(device, err.message);
        console.warn("Failed to send command:", err);
    } finally {
        pendingCommands.delete(device);
        updateCommands();
    }
}

btnStart.addEventListener("click", () => sendCommand("START"));
btnPause.addEventListener("click", () => sendCommand("PAUSE"));
btnOff.addEventListener("click", () => sendCommand("SHUTDOWN"));

pollState();
