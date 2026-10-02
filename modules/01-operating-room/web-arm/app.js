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

const armView = { zoom: 1, panX: 0, panY: 0 };
let displayedAngles = {};
let panStart = null;

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
    displayedAngles = angles;
    const bounds = canvas.getBoundingClientRect();
    const pixelRatio = window.devicePixelRatio || 1;
    const pixelWidth = Math.max(1, Math.round(bounds.width * pixelRatio));
    const pixelHeight = Math.max(1, Math.round(bounds.height * pixelRatio));
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth;
        canvas.height = pixelHeight;
    }
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    const w = bounds.width;
    const h = bounds.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#0F1822";
    ctx.fillRect(0, 0, w, h);

    const seg = Math.max(1, (h - Math.min(48, h * 0.18)) / JOINT_ORDER.length) * armView.zoom;
    const jointRadius = Math.min(8, seg / 4);
    const markerRadius = Math.min(10, seg / 3);
    const bx = w / 2 + armView.panX;
    const by = h - Math.min(24, h * 0.08) + armView.panY;

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

    ctx.strokeStyle = "#334455";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(bx - 60, by);
    ctx.lineTo(bx + 60, by);
    ctx.stroke();

    // Links
    JOINT_ORDER.forEach((j, i) => {
        ctx.strokeStyle = JOINT_COLORS[j];
        ctx.lineWidth = Math.min(7, seg / 5);
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
        ctx.arc(cx, cy, jointRadius, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = JOINT_COLORS[j];
        ctx.font = `bold ${Math.min(13, Math.max(9, seg * 0.6))}px monospace`;
        ctx.fillText(j.slice(0, 3), cx + jointRadius + 4, cy + 4);
    });

    // End effector marker
    const [ex, ey] = points[points.length - 1];
    ctx.fillStyle = JOINT_COLORS.HAND;
    ctx.beginPath();
    ctx.moveTo(ex, ey - markerRadius);
    ctx.lineTo(ex + markerRadius, ey);
    ctx.lineTo(ex, ey + markerRadius);
    ctx.lineTo(ex - markerRadius, ey);
    ctx.closePath();
    ctx.fill();
    return points;
}

function zoomArm(factor) {
    armView.zoom = Math.max(0.1, Math.min(4, armView.zoom * factor));
    drawArm(displayedAngles);
}

function fitArmView() {
    armView.zoom = 1;
    armView.panX = 0;
    armView.panY = 0;
    const points = drawArm(displayedAngles);
    const bounds = canvas.getBoundingClientRect();
    const minX = Math.min(...points.map(point => point[0] - 12));
    const maxX = Math.max(...points.map(point => point[0] + 44));
    const minY = Math.min(...points.map(point => point[1] - 12));
    const maxY = Math.max(...points.map(point => point[1] + 12));
    const scale = Math.max(0.01, Math.min((bounds.width - 24) / (maxX - minX), (bounds.height - 24) / (maxY - minY)));
    armView.zoom = scale;
    armView.panX = (bounds.width - (maxX - minX) * scale) / 2 + (bounds.width / 2 - minX) * scale - bounds.width / 2;
    const baseY = bounds.height - Math.min(24, bounds.height * 0.08);
    armView.panY = (bounds.height - (maxY - minY) * scale) / 2 + (baseY - minY) * scale - baseY;
    drawArm(displayedAngles);
}

document.getElementById("btn-zoom-out").addEventListener("click", () => zoomArm(0.8));
document.getElementById("btn-zoom-in").addEventListener("click", () => zoomArm(1.25));
document.getElementById("btn-fit-arm").addEventListener("click", fitArmView);
canvas.addEventListener("pointerdown", event => {
    panStart = { x: event.clientX, y: event.clientY, panX: armView.panX, panY: armView.panY };
    canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener("pointermove", event => {
    if (!panStart) return;
    armView.panX = panStart.panX + event.clientX - panStart.x;
    armView.panY = panStart.panY + event.clientY - panStart.y;
    drawArm(displayedAngles);
});
canvas.addEventListener("pointerup", () => { panStart = null; });
canvas.addEventListener("pointercancel", () => { panStart = null; });

async function pollState() {
    try {
        const res = await fetch("api/state", { cache: "no-store" });
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
