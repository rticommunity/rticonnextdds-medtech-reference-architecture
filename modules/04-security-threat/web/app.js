"use strict";

const element = id => document.getElementById(id);
let configured = false;
let sending = false;
let lastSample = -1;
const history = [];
const colors = ["#53a4f5", "#ed8b00", "#00bfff", "#7cfc00", "#da70d6"];

function showError(message) {
    element("error").textContent = message;
    element("error").hidden = !message;
}

async function command(payload) {
    if (sending) return;
    sending = true;
    try {
        const response = await fetch("api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const state = await response.json();
        if (!response.ok) throw new Error(state.error || `HTTP ${response.status}`);
        showError("");
        render(state);
    } catch (error) {
        showError(error.message);
    } finally {
        sending = false;
    }
}

function configure(state) {
    for (const mode of state.modes) {
        const button = document.createElement("button");
        button.textContent = mode;
        button.addEventListener("click", () => command({ action: "mode", mode }));
        element("modes").append(button);
    }
    const injector = state.kind === "Threat Injector";
    element("injector-controls").hidden = !injector;
    element("arm").hidden = !injector;
    element("vitals").hidden = injector;
    for (const attack of state.attacks || []) {
        const option = document.createElement("option");
        option.value = option.textContent = attack;
        element("attack").append(option);
    }
    element("attack").addEventListener("change", event =>
        command({ action: "attack", attack: event.target.value }));
    element("frequency").addEventListener("input", event => {
        element("hz").textContent = event.target.value;
    });
    element("frequency").addEventListener("change", event =>
        command({ action: "frequency", frequency: Number(event.target.value) }));
    element("launch").addEventListener("click", () => command({ action: "launch" }));
    element("stop").addEventListener("click", () => command({ action: "stop" }));
    configured = true;
}

function drawArm(angles) {
    const canvas = element("arm-canvas");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let x = 250, y = 450, direction = -Math.PI / 2;
    Object.entries(angles).forEach(([name, angle], index) => {
        direction -= (angle - 180) * Math.PI / 180;
        const nx = x + 70 * Math.cos(direction);
        const ny = y + 70 * Math.sin(direction);
        ctx.strokeStyle = ctx.fillStyle = colors[index];
        ctx.lineWidth = 6;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(nx, ny); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fill();
        ctx.font = "13px monospace";
        ctx.fillText(`${name}: ${angle.toFixed(1)}`, 12, 24 + index * 24);
        x = nx; y = ny;
    });
}

function drawVitals(state) {
    const vitals = state.vitals;
    for (const name of ["hr", "spo2", "etco2"]) {
        element(name).textContent = vitals ? vitals[name].toFixed(0) : "---";
    }
    element("nibp").textContent = vitals
        ? `${vitals.nibp_s.toFixed(0)}/${vitals.nibp_d.toFixed(0)}` : "---";
    element("patient").textContent = vitals
        ? `Patient ${vitals.patient_id}; received samples: ${state.sample}` : "Waiting for data";
    if (!vitals) history.length = 0;
    else if (state.sample !== lastSample) {
        history.push(vitals);
        if (history.length > 120) history.shift();
    }
    lastSample = state.sample;
    const canvas = element("vitals-canvas");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ["hr", "spo2", "etco2"].forEach((name, index) => {
        ctx.strokeStyle = colors[index];
        ctx.fillStyle = colors[index];
        ctx.fillText(name, 10 + index * 90, 15);
        ctx.beginPath();
        history.forEach((sample, i) => {
            const x = i * canvas.width / 119;
            const y = canvas.height - sample[name] / 200 * (canvas.height - 25);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
    });
}

function render(state) {
    if (!configured) configure(state);
    document.title = element("title").textContent = state.kind;
    element("status").textContent = state.status;
    element("status").dataset.status = state.status;
    element("stop").disabled = !state.mode;
    for (const button of element("modes").children) {
        button.classList.toggle("active", button.textContent === state.mode);
    }
    if (state.kind === "Threat Injector") {
        element("attack").value = state.attack;
        element("attack").disabled = !state.mode || state.attacking;
        element("launch").disabled = !state.mode;
        element("launch").textContent = state.attacking ? "Stop injection" : "Launch attack";
        element("frequency").disabled = !state.mode || state.attacking
            || state.attack !== "MOTOR INJECT";
        if (document.activeElement !== element("frequency")) {
            element("frequency").value = state.frequency;
            element("hz").textContent = state.frequency;
        }
        drawArm(state.angles);
    } else drawVitals(state);
    const log = element("log");
    log.textContent = state.logs.map(entry =>
        `${entry.time} [${entry.level}] ${entry.message}`).join("\n");
    log.scrollTop = log.scrollHeight;
}

async function poll() {
    try {
        const response = await fetch("api/state", { cache: "no-store" });
        if (!response.ok) throw new Error(`State request failed: HTTP ${response.status}`);
        const state = await response.json();
        if (element("error").textContent.startsWith("Connection lost:")) showError("");
        if (!sending) render(state);
    } catch (error) {
        showError(`Connection lost: ${error.message}`);
    } finally {
        setTimeout(poll, 250);
    }
}

poll();
