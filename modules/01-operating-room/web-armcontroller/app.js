// Arm Controller web UI — polls /api/state and issues motor jog/play
// commands via plain HTTP POST (no WebSocket, for proxy compatibility).

const MOTOR_NAMES = {
    BASE: "Base",
    SHOULDER: "Shoulder",
    ELBOW: "Elbow",
    WRIST: "Wrist",
    HAND: "Hand",
};
const MOTOR_ORDER = ["BASE", "SHOULDER", "ELBOW", "WRIST", "HAND"];

const POLL_INTERVAL_MS = 500;
const JOG_REPEAT_MS = 50;

let lastAlertCount = 0;
let renderedOnce = false;
let shutdownHandled = false;
let consecutiveFailures = 0;
const jogTimers = {};

const motorsEl = document.getElementById("motors");
const alertsEl = document.getElementById("alerts");
const statusEl = document.getElementById("device-status");

function statusClass(status) {
    if (status === "ON") return "status-on";
    if (status === "PAUSED") return "status-paused";
    return "status-off";
}

function handleShutdown() {
    if (shutdownHandled) return;
    shutdownHandled = true;
    const overlay = document.createElement("div");
    overlay.id = "shutdown-overlay";
    overlay.innerHTML = "Device shut down<span>You can close this tab.</span>";
    document.body.appendChild(overlay);
    clearInterval(pollTimer);
    setTimeout(() => window.close(), 1200);
}

function buildMotorRow(motorId) {
    const row = document.createElement("div");
    row.className = "motor-row";
    row.dataset.motorId = motorId;

    const name = document.createElement("span");
    name.className = "motor-name " + motorId;
    name.textContent = MOTOR_NAMES[motorId] || motorId;
    row.appendChild(name);

    const dec = document.createElement("button");
    dec.textContent = "−";
    dec.addEventListener("mousedown", () => startJog(motorId, "dec"));
    dec.addEventListener("mouseup", stopJog);
    dec.addEventListener("mouseleave", stopJog);
    dec.addEventListener("touchstart", (e) => {
        e.preventDefault();
        startJog(motorId, "dec");
    });
    dec.addEventListener("touchend", stopJog);
    row.appendChild(dec);

    const inc = document.createElement("button");
    inc.textContent = "+";
    inc.addEventListener("mousedown", () => startJog(motorId, "inc"));
    inc.addEventListener("mouseup", stopJog);
    inc.addEventListener("mouseleave", stopJog);
    inc.addEventListener("touchstart", (e) => {
        e.preventDefault();
        startJog(motorId, "inc");
    });
    inc.addEventListener("touchend", stopJog);
    row.appendChild(inc);

    const playToggle = document.createElement("button");
    playToggle.className = "play-toggle";
    playToggle.textContent = "AUTO";
    playToggle.dataset.motorId = motorId;
    playToggle.addEventListener("click", () => togglePlay(motorId, playToggle));
    row.appendChild(playToggle);

    return row;
}

function renderMotors(motors) {
    if (!renderedOnce) {
        motorsEl.innerHTML = "";
        MOTOR_ORDER.forEach((motorId) => motorsEl.appendChild(buildMotorRow(motorId)));
        renderedOnce = true;
    }
    motors.forEach((m) => {
        const toggle = motorsEl.querySelector(
                `.play-toggle[data-motor-id="${m.id}"]`);
        if (toggle) {
            toggle.classList.toggle("active", m.playing);
        }
    });
}

function renderStatus(status) {
    statusEl.textContent = status;
    statusEl.className = statusClass(status);
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
        renderMotors(state.motors || []);
        renderStatus(state.status || "OFF");
        renderAlerts(state.alerts || []);
        if (state.status === "OFF") handleShutdown();
    } catch (err) {
        console.warn("Failed to fetch /api/state:", err);
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) handleShutdown();
    }
}

async function sendMotor(motorId, action) {
    try {
        await fetch("/api/motor", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ motor: motorId, action }),
        });
    } catch (err) {
        console.warn("Failed to send motor command:", err);
    }
}

async function sendPlay(motorId, active) {
    try {
        await fetch("/api/play", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ motor: motorId, active }),
        });
    } catch (err) {
        console.warn("Failed to send play command:", err);
    }
}

async function sendPlayAll(active) {
    try {
        await fetch("/api/play_all", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ active }),
        });
    } catch (err) {
        console.warn("Failed to send play_all command:", err);
    }
}

function startJog(motorId, action) {
    stopJog();
    sendMotor(motorId, action);
    jogTimers.id = setInterval(() => sendMotor(motorId, action), JOG_REPEAT_MS);
}

function stopJog() {
    if (jogTimers.id) {
        clearInterval(jogTimers.id);
        jogTimers.id = null;
    }
}

function togglePlay(motorId, toggleEl) {
    const nowActive = !toggleEl.classList.contains("active");
    toggleEl.classList.toggle("active", nowActive);
    sendPlay(motorId, nowActive);
}

document.getElementById("btn-play-all").addEventListener("click", () => sendPlayAll(true));
document.getElementById("btn-stop-all").addEventListener("click", () => sendPlayAll(false));

pollState();
const pollTimer = setInterval(pollState, POLL_INTERVAL_MS);
