// Arm web UI — read-only dashboard, polls /api/state and renders joint
// angles/directions plus a simple forward-kinematics stick-figure arm.

const JOINT_ORDER = ["BASE", "SHOULDER", "ELBOW", "WRIST", "HAND"];
const JOINT_COLORS = {
    BASE: "#004C97",
    SHOULDER: "#ED8B00",
    ELBOW: "#00BFFF",
    WRIST: "#7CFC00",
    HAND: "#DA70D6",
};

const POLL_INTERVAL_MS = 150;

const jointsEl = document.getElementById("joints");
const statusEl = document.getElementById("device-status");
const canvas = document.getElementById("arm-viz");
const ctx = canvas.getContext("2d");

let renderedOnce = false;
let shutdownHandled = false;
let consecutiveFailures = 0;

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

function buildJointRow(jointId) {
    const row = document.createElement("div");
    row.className = "joint-row";
    row.dataset.jointId = jointId;

    const name = document.createElement("span");
    name.className = "joint-name " + jointId;
    name.textContent = jointId.charAt(0) + jointId.slice(1).toLowerCase();
    row.appendChild(name);

    const angle = document.createElement("span");
    angle.className = "joint-angle";
    row.appendChild(angle);

    const dir = document.createElement("span");
    dir.className = "joint-dir";
    row.appendChild(dir);

    return row;
}

function renderJoints(angles, directions) {
    if (!renderedOnce) {
        jointsEl.innerHTML = "";
        JOINT_ORDER.forEach((j) => jointsEl.appendChild(buildJointRow(j)));
        renderedOnce = true;
    }
    JOINT_ORDER.forEach((j) => {
        const row = jointsEl.querySelector(`.joint-row[data-joint-id="${j}"]`);
        if (!row) return;
        row.querySelector(".joint-angle").textContent = `${(angles[j] || 0).toFixed(1)}°`;
        const dirEl = row.querySelector(".joint-dir");
        const dir = directions[j] || "STATIONARY";
        dirEl.textContent = dir;
        dirEl.className = "joint-dir " + dir;
    });
}

function renderStatus(status) {
    statusEl.textContent = status;
    statusEl.className = statusClass(status);
}

function drawArm(angles) {
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#0F1822";
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = "#445566";
    ctx.font = "bold 13px monospace";
    ctx.fillText("ARM VISUALIZATION", 12, 22);

    const usableH = h - 70;
    let seg = Math.floor((usableH * 0.9) / JOINT_ORDER.length);
    seg = Math.max(seg, 40);

    const bx = w / 2;
    const by = h - 36;

    // Ground line
    ctx.strokeStyle = "#334455";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(bx - 80, by);
    ctx.lineTo(bx + 80, by);
    ctx.stroke();

    // Forward kinematics — 180deg = straight up; deviations bend the arm.
    let cumulDir = Math.PI / 2;
    let x = bx;
    let y = by;
    const points = [[x, y]];

    JOINT_ORDER.forEach((j) => {
        const angle = angles[j] !== undefined ? angles[j] : 180.0;
        const deltaRad = ((angle - 180.0) * Math.PI) / 180.0;
        cumulDir += deltaRad;
        const nx = x + seg * Math.cos(cumulDir);
        const ny = y - seg * Math.sin(cumulDir);
        points.push([nx, ny]);
        x = nx;
        y = ny;
    });

    // Links
    JOINT_ORDER.forEach((j, i) => {
        ctx.strokeStyle = JOINT_COLORS[j];
        ctx.lineWidth = 7;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(points[i][0], points[i][1]);
        ctx.lineTo(points[i + 1][0], points[i + 1][1]);
        ctx.stroke();
    });

    // Joint circles + labels
    JOINT_ORDER.forEach((j, i) => {
        const [cx, cy] = points[i];
        ctx.fillStyle = JOINT_COLORS[j];
        ctx.beginPath();
        ctx.arc(cx, cy, 8, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = JOINT_COLORS[j];
        ctx.font = "bold 13px monospace";
        ctx.fillText(j.slice(0, 3), cx + 12, cy + 4);
    });

    // End effector marker
    const [ex, ey] = points[points.length - 1];
    ctx.fillStyle = JOINT_COLORS.HAND;
    ctx.beginPath();
    ctx.moveTo(ex, ey - 10);
    ctx.lineTo(ex + 10, ey);
    ctx.lineTo(ex, ey + 10);
    ctx.lineTo(ex - 10, ey);
    ctx.closePath();
    ctx.fill();
}

async function pollState() {
    try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (!res.ok) return;
        const state = await res.json();
        consecutiveFailures = 0;
        renderStatus(state.status || "OFF");
        renderJoints(state.angles || {}, state.directions || {});
        drawArm(state.angles || {});
        if (state.status === "OFF") handleShutdown();
    } catch (err) {
        console.warn("Failed to fetch /api/state:", err);
        consecutiveFailures += 1;
        // Backend process has likely exited (SHUTDOWN command) — the server
        // will never respond again, so treat repeated failures as shutdown.
        if (consecutiveFailures >= 3) handleShutdown();
    }
}

pollState();
const pollTimer = setInterval(pollState, POLL_INTERVAL_MS);
