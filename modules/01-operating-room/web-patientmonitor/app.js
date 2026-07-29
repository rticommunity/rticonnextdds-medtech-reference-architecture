// Patient Monitor web UI — polls /api/state for live vitals, then animates
// synthetic ECG/plethysmograph/capnography waveforms client-side (same
// templates as the native PySide6 app) driven by the live vitals values.

const POLL_INTERVAL_MS = 500;
const SAMPLE_RATE = 200; // samples/sec in the waveform buffer
const DISPLAY_SECS = 6;
const BUFFER_LEN = SAMPLE_RATE * DISPLAY_SECS;
const FRAME_MS = 40; // ~25 fps
const NEW_PER_TICK = Math.round((SAMPLE_RATE * FRAME_MS) / 1000);

function linspace(a, b, n) {
    const out = new Array(n);
    const step = (b - a) / (n - 1);
    for (let i = 0; i < n; i++) out[i] = a + step * i;
    return out;
}

function gauss(t, mu, sigma) {
    return Math.exp(-((t - mu) ** 2) / (2 * sigma * sigma));
}

function ecgTemplate(n = SAMPLE_RATE) {
    const t = linspace(0, 1, n);
    return t.map((v) => {
        const p = 0.15 * gauss(v, 0.12, 0.008);
        const q = -0.08 * gauss(v, 0.22, 0.004);
        const r = 1.0 * gauss(v, 0.26, 0.003);
        const s = -0.15 * gauss(v, 0.3, 0.004);
        const tw = 0.3 * gauss(v, 0.42, 0.015);
        return p + q + r + s + tw;
    });
}

function plethTemplate(n = SAMPLE_RATE) {
    const t = linspace(0, 1, n);
    return t.map((v) => {
        const val = gauss(v, 0.35, 0.05) + 0.25 * gauss(v, 0.55, 0.04);
        return Math.max(0, Math.min(1, val));
    });
}

function capnoTemplate(n = SAMPLE_RATE) {
    const t = linspace(0, 1, n);
    return t.map((v) => {
        if (v >= 0.3 && v < 0.6) return (v - 0.3) / 0.3;
        if (v >= 0.6 && v < 0.85) return 1.0;
        if (v >= 0.85 && v < 0.95) return 1.0 - (v - 0.85) / 0.1;
        return 0.0;
    });
}

class Waveform {
    constructor(canvas, color, yMin, yMax, template) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d");
        this.color = color;
        this.yMin = yMin;
        this.yMax = yMax;
        this.template = template;
        this.buf = new Float32Array(BUFFER_LEN);
        this.ptr = 0;
        this.phase = 0;
        this.beatRate = 1.0; // beats/sec
        this.amplitude = 1.0;
    }

    advance(nNew) {
        const tLen = this.template.length;
        for (let i = 0; i < nNew; i++) {
            const idx = Math.floor(this.phase * tLen) % tLen;
            this.buf[this.ptr % BUFFER_LEN] = this.template[idx] * this.amplitude;
            this.ptr += 1;
            this.phase += this.beatRate / SAMPLE_RATE;
            if (this.phase >= 1.0) this.phase -= 1.0;
        }
    }

    draw() {
        const { ctx, canvas } = this;
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        const start = this.ptr % BUFFER_LEN;
        ctx.strokeStyle = this.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        const range = this.yMax - this.yMin;
        for (let i = 0; i < BUFFER_LEN; i++) {
            const val = this.buf[(start + i) % BUFFER_LEN];
            const x = (i / BUFFER_LEN) * w;
            const norm = (val - this.yMin) / range;
            const y = h - norm * h;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
}

const hrWave = new Waveform(document.getElementById("wave-hr"), "#00E676", -0.2, 1.1, ecgTemplate());
const spo2Wave = new Waveform(document.getElementById("wave-spo2"), "#00B0FF", -0.1, 1.1, plethTemplate());
const etco2Wave = new Waveform(document.getElementById("wave-etco2"), "#FFD600", -0.1, 1.1, capnoTemplate());

const statusEl = document.getElementById("device-status");
let paused = false;
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

async function pollState() {
    try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (!res.ok) return;
        const state = await res.json();

        statusEl.textContent = state.status || "OFF";
        statusEl.className = statusClass(state.status || "OFF");
        paused = state.status === "PAUSED" || Boolean(state.data_stale);

        document.getElementById("value-hr").textContent = Math.round(state.hr ?? 0);
        document.getElementById("value-spo2").textContent = Math.round(state.spo2 ?? 0);
        document.getElementById("value-etco2").textContent = Math.round(state.etco2 ?? 0);
        document.getElementById("value-sys").textContent = Math.round(state.nibp_s ?? 0);
        document.getElementById("value-dia").textContent = Math.round(state.nibp_d ?? 0);
        const map = ((state.nibp_s ?? 0) + 2 * (state.nibp_d ?? 0)) / 3;
        document.getElementById("value-map").textContent = `MAP: ${Math.round(map)}`;

        const hr = state.hr ?? 60;
        hrWave.beatRate = hr / 60.0;
        spo2Wave.beatRate = hr / 60.0;
        const rr = Math.max(8.0, Math.min(30.0, hr / 4.0));
        etco2Wave.beatRate = rr / 60.0;
        etco2Wave.amplitude = Math.max(0, Math.min(60, state.etco2 ?? 38)) / 60.0;

        consecutiveFailures = 0;
        if (state.status === "OFF") handleShutdown();
    } catch (err) {
        console.warn("Failed to fetch /api/state:", err);
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) handleShutdown();
    }
}

function tick() {
    if (!paused) {
        hrWave.advance(NEW_PER_TICK);
        spo2Wave.advance(NEW_PER_TICK);
        etco2Wave.advance(NEW_PER_TICK);
    }
    hrWave.draw();
    spo2Wave.draw();
    etco2Wave.draw();
}

pollState();
const pollTimer = setInterval(pollState, POLL_INTERVAL_MS);
setInterval(tick, FRAME_MS);
