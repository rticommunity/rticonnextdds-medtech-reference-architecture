// Orchestrator web UI — polls the embedded HTTP server for state and posts
// commands back over plain HTTP. Polling (instead of WebSocket) is used
// deliberately so this works reliably behind simple HTTP proxies (e.g. a
// cloud-IDE port-forwarding proxy) that may not support the WS upgrade.

const DEVICE_LABELS = {
    ARM: "Arm",
    ARM_CONTROLLER: "Arm Controller",
    PATIENT_SENSOR: "Patient Sensor",
    PATIENT_MONITOR: "Patient Monitor",
};

const POLL_INTERVAL_MS = 1000;

let selectedDevice = null;
let lastAlertCount = 0;
let shutdownHandled = false;
let consecutiveFailures = 0;

const devicesEl = document.getElementById("devices");
const alertsEl = document.getElementById("alerts");
const selectedDeviceEl = document.getElementById("selected-device");
const securityEl = document.getElementById("security-indicator");
const btnStart = document.getElementById("btn-start");
const btnPause = document.getElementById("btn-pause");
const btnOff = document.getElementById("btn-off");

function handleShutdown() {
    if (shutdownHandled) return;
    shutdownHandled = true;
    const overlay = document.createElement("div");
    overlay.id = "shutdown-overlay";
    overlay.innerHTML = "Orchestrator shut down<span>You can close this tab.</span>";
    document.body.appendChild(overlay);
    clearInterval(pollTimer);
    setTimeout(() => window.close(), 1200);
}

function statusClass(status) {
    if (status.indexOf("ON") !== -1) return "status-on";
    if (status.indexOf("PAUSED") !== -1) return "status-paused";
    return "status-off";
}

function renderDevices(devices) {
    devicesEl.innerHTML = "";
    devices.forEach((device) => {
        const card = document.createElement("div");
        card.className = "device-card" + (device.id === selectedDevice ? " selected" : "");
        card.dataset.deviceId = device.id;

        const name = document.createElement("div");
        name.className = "device-name";
        name.textContent = DEVICE_LABELS[device.id] || device.id;

        const status = document.createElement("span");
        status.className = "status-badge " + statusClass(device.status);
        status.textContent = device.status;

        card.appendChild(name);
        card.appendChild(status);
        card.addEventListener("click", () => selectDevice(device.id));
        devicesEl.appendChild(card);
    });
}

function selectDevice(deviceId) {
    selectedDevice = deviceId;
    selectedDeviceEl.textContent = DEVICE_LABELS[deviceId] || deviceId;
    document.querySelectorAll(".device-card").forEach((card) => {
        card.classList.toggle("selected", card.dataset.deviceId === deviceId);
    });
    [btnStart, btnPause, btnOff].forEach((btn) => (btn.disabled = false));
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

function renderAlerts(alerts) {
    if (alerts.length === lastAlertCount) return;
    lastAlertCount = alerts.length;
    alertsEl.textContent = alerts.join("\n");
    alertsEl.scrollTop = alertsEl.scrollHeight;
}

async function pollState() {
    try {
        const res = await fetch("/api/state", { cache: "no-store" });
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
    }
}

async function sendCommand(command) {
    if (!selectedDevice) return;
    try {
        await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device: selectedDevice, command }),
        });
    } catch (err) {
        console.warn("Failed to send command:", err);
    }
}

btnStart.addEventListener("click", () => sendCommand("START"));
btnPause.addEventListener("click", () => sendCommand("PAUSE"));
btnOff.addEventListener("click", () => sendCommand("SHUTDOWN"));

pollState();
const pollTimer = setInterval(pollState, POLL_INTERVAL_MS);
