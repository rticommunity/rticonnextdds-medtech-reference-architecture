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

const POLL_INTERVAL_MS = 100;
const JOG_REPEAT_MS = 50;

let lastAlertText = "";
let renderedOnce = false;
let shutdownHandled = false;
let consecutiveFailures = 0;
let jogTimer;
let jogSession;
let jogRequest;
let playPending = false;
let motorRevision = 0;

const motorsEl = document.getElementById("motors");
const alertsEl = document.getElementById("alerts");
const statusEl = document.getElementById("device-status");
const commandStatus = document.getElementById("command-status");
const playAllButton = document.getElementById("btn-play-all");
const stopAllButton = document.getElementById("btn-stop-all");

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
    stopJog();
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
    dec.addEventListener("touchcancel", stopJog);
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
    inc.addEventListener("touchcancel", stopJog);
    row.appendChild(inc);

    const playToggle = document.createElement("button");
    playToggle.className = "play-toggle";
    playToggle.textContent = "AUTO";
    playToggle.setAttribute("aria-pressed", "false");
    playToggle.dataset.motorId = motorId;
    playToggle.addEventListener("click", () => togglePlay(motorId, playToggle));
    row.appendChild(playToggle);

    return row;
}

function setPlaying(button, active) {
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
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
            setPlaying(toggle, m.playing);
        }
    });
}

function renderStatus(status) {
    statusEl.textContent = status;
    statusEl.className = statusClass(status);
}

function formatAlert(message) {
    return message.replace(/\b(?:DeviceCommands|DeviceType|DeviceStatuses)::/g, "")
    .replace(/[ \t]+/g, " ").trimEnd()
    .replace(/ \(web mode\)$/, "");
}

function renderAlerts(alerts) {
    const text = alerts.map(formatAlert).join("\n");
    if (text === lastAlertText) return;
    const followLatest = alertsEl.scrollHeight - alertsEl.clientHeight - alertsEl.scrollTop <= 2;
    const previousScroll = alertsEl.scrollTop;
    lastAlertText = text;
    alertsEl.textContent = text;
    alertsEl.scrollTop = followLatest ? alertsEl.scrollHeight : previousScroll;
}

async function pollState() {
    const revision = motorRevision;
    try {
        const res = await fetch("api/state", { cache: "no-store" });
        if (!res.ok) return;
        const state = await res.json();
        consecutiveFailures = 0;
        if (!playPending && revision === motorRevision) renderMotors(state.motors || []);
        renderStatus(state.status || "OFF");
        renderAlerts(state.alerts || []);
        if (state.status === "OFF") handleShutdown();
    } catch (err) {
        console.warn("Failed to fetch /api/state:", err);
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) handleShutdown();
    } finally {
        if (!shutdownHandled) setTimeout(pollState, POLL_INTERVAL_MS);
    }
}

async function postCommand(endpoint, body) {
    const response = await fetch(`api/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    if (result.ok !== true) throw new Error("Command was not acknowledged");
}

async function sendPlay(active, motorId = null) {
    if (playPending || shutdownHandled) return;
    const toggles = [...motorsEl.querySelectorAll(".play-toggle")];
    const controls = [playAllButton, stopAllButton, ...motorsEl.querySelectorAll("button")];
    playPending = true;
    stopJog();
    controls.forEach(button => { button.disabled = true; });
    commandStatus.textContent = "Sending command...";
    try {
        if (jogRequest) {
            await jogRequest;
            if (shutdownHandled) return;
            commandStatus.textContent = "Sending command...";
        }
        await (motorId === null
            ? postCommand("play_all", { active })
            : postCommand("play", { motor: motorId, active }));
        toggles.filter(button => motorId === null || button.dataset.motorId === motorId)
            .forEach(button => setPlaying(button, active));
        commandStatus.textContent = "";
    } catch (err) {
        commandStatus.textContent = `Command not confirmed: ${err.message}`;
        console.warn("Failed to confirm play command:", err);
    } finally {
        // A poll started before the acknowledgement may carry older motor state.
        motorRevision++;
        playPending = false;
        controls.forEach(button => { button.disabled = false; });
    }
}

async function repeatJog(session) {
    const started = performance.now();
    if (jogRequest) await jogRequest;
    if (jogSession !== session) return;
    jogRequest = postCommand("motor", { motor: session.motorId, action: session.action })
        .then(() => {
            motorRevision++;
            const toggle = motorsEl.querySelector(`.play-toggle[data-motor-id="${session.motorId}"]`);
            if (toggle) setPlaying(toggle, false);
        })
        .catch(err => {
            if (jogSession === session) stopJog();
            commandStatus.textContent = `Jog not confirmed: ${err.message}`;
            console.warn("Failed to confirm jog command:", err);
        });
    await jogRequest;
    jogRequest = undefined;
    if (jogSession === session) {
        jogTimer = setTimeout(() => repeatJog(session),
            Math.max(0, JOG_REPEAT_MS - (performance.now() - started)));
    }
}

function startJog(motorId, action) {
    if (playPending || shutdownHandled) return;
    stopJog();
    commandStatus.textContent = "";
    jogSession = { motorId, action };
    repeatJog(jogSession);
}

function stopJog() {
    jogSession = undefined;
    clearTimeout(jogTimer);
}

function togglePlay(motorId, toggleEl) {
    sendPlay(!toggleEl.classList.contains("active"), motorId);
}

playAllButton.addEventListener("click", () => sendPlay(true));
stopAllButton.addEventListener("click", () => sendPlay(false));
window.addEventListener("blur", stopJog);

pollState();
