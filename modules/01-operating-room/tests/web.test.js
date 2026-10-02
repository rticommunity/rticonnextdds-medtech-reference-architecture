const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const sourceFor = app => fs.readFileSync(path.join(__dirname, `../${app}/app.js`), "utf8");

test("arm drawing keeps upstream joints fixed when a downstream joint moves", () => {
    const source = sourceFor("web-arm");
    const circles = [];
    const ctx = Object.fromEntries(["setTransform", "clearRect", "fillRect", "fillText", "beginPath", "moveTo", "lineTo", "stroke", "fill", "closePath"].map(name => [name, () => {}]));
    ctx.arc = (horizontal, vertical) => circles.push([horizontal, vertical]);
    const sandbox = {
        ctx, canvas: { width: 270, height: 285, getBoundingClientRect: () => ({ width: 270, height: 285 }), addEventListener() {} },
        window: { devicePixelRatio: 1 }, JOINT_ORDER: ["BASE", "SHOULDER", "ELBOW", "WRIST", "HAND"],
        JOINT_COLORS: {}, armView: { zoom: 1, panX: 0, panY: 0 }, displayedAngles: {},
        document: { getElementById: () => ({ addEventListener() {} }) },
    };
    vm.runInNewContext(source.slice(source.indexOf("function drawArm("), source.indexOf("\nasync function pollState(")), sandbox);
    const angles = { BASE: 180, SHOULDER: 180, ELBOW: 180, WRIST: 180, HAND: 180 };
    sandbox.drawArm(angles);
    const initial = circles.splice(0);
    assert.ok(initial[0][1] - initial[4][1] >= 150);
    sandbox.drawArm({ ...angles, WRIST: 240 });
    assert.deepEqual(circles.slice(0, 4), initial.slice(0, 4));
    assert.notDeepEqual(circles[4], initial[4]);
    for (let angle = 0; angle <= 360; angle += 30) {
        circles.length = 0;
        sandbox.drawArm(Object.fromEntries(Object.keys(angles).map(joint => [joint, angle])));
        assert.deepEqual(circles[0], initial[0]);
        sandbox.fitArmView();
        assert.ok(circles.slice(-5).every(([horizontal, vertical]) => horizontal >= 8 && horizontal <= 262 && vertical >= 8 && vertical <= 277));
        sandbox.armView.zoom = 1;
        sandbox.armView.panX = 0;
        sandbox.armView.panY = 0;
    }
});

test("device logs simplify DDS prefixes and preserve each app's scroll policy", () => {
    for (const app of ["web", "web-armcontroller"]) {
        const source = sourceFor(app);
        const alertsEl = { textContent: "", scrollHeight: 0, clientHeight: 80, scrollTop: 0 };
        const sandbox = { alertsEl };
        vm.runInNewContext('let lastAlertText = "";\n' + source.slice(source.indexOf("function formatAlert("), source.indexOf("\nasync function pollState(")), sandbox);
        const cases = [
            ["2026-10-02 18:00:00 - Started Arm Controller (web mode)", "2026-10-02 18:00:00 - Started Arm Controller"],
            ["Writing DeviceCommands::SHUTDOWN to DeviceType::ARM_CONTROLLER", "Writing SHUTDOWN to ARM_CONTROLLER"],
            ["Received DeviceStatuses::ON status message from DeviceType::ARM", "Received ON status message from ARM"],
            ["Unknown::VALUE and MyDeviceType::ARM remain unchanged", "Unknown::VALUE and MyDeviceType::ARM remain unchanged"],
            ["The (web mode) setting is enabled", "The (web mode) setting is enabled"],
        ];
        const rawAlerts = Object.freeze(cases.map(([raw]) => raw));
        sandbox.renderAlerts(rawAlerts);
        assert.equal(alertsEl.textContent, cases.map(([, expected]) => expected).join("\n"));
        assert.deepEqual(rawAlerts, cases.map(([raw]) => raw));
        alertsEl.scrollHeight = 300;
        alertsEl.scrollTop = 220;
        sandbox.renderAlerts(["DeviceCommands::START"]);
        assert.equal(alertsEl.scrollTop, 300);
        alertsEl.scrollTop = 20;
        sandbox.renderAlerts(["DeviceCommands::PAUSE"]);
        assert.equal(alertsEl.textContent, "PAUSE");
        assert.equal(alertsEl.scrollTop, app === "web" ? 300 : 20);
        alertsEl.scrollTop = 20;
        sandbox.renderAlerts(["DeviceCommands::PAUSE"]);
        assert.equal(alertsEl.scrollTop, 20);
    }
});

function orchestrator() {
    const cards = [];
    const requests = [];
    const element = () => ({ textContent: "", classList: { toggle() {} }, addEventListener() {}, appendChild() {}, dataset: {} });
    const devicesEl = { appendChild(card) { cards.push(card); }, set innerHTML(value) { cards.length = 0; } };
    const sandbox = {
        document: { getElementById: id => id === "devices" ? devicesEl : element(), createElement: element, querySelectorAll: () => cards },
        fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => ({ devices: [] }) }; },
        setInterval() {}, console,
    };
    vm.runInNewContext(sourceFor("web"), sandbox);
    return { sandbox, cards, requests };
}

test("Orchestrator device grid keeps the requested order regardless of API order", () => {
    const { sandbox, cards } = orchestrator();
    const expected = ["ARM_CONTROLLER", "PATIENT_SENSOR", "ARM", "PATIENT_MONITOR"];
    for (const order of [["ARM", "ARM_CONTROLLER", "PATIENT_MONITOR", "PATIENT_SENSOR"], [...expected].reverse()]) {
        const devices = Object.freeze(order.map(id => Object.freeze({ id, status: "ON" })));
        sandbox.renderDevices(devices);
        assert.deepEqual(cards.map(card => card.dataset.deviceId), expected);
        assert.deepEqual(devices.map(device => device.id), order);
    }
});

test("Orchestrator commands use HTTP without an extension bridge", async () => {
    const { sandbox, requests } = orchestrator();
    sandbox.selectDevice("ARM");
    for (const command of ["START", "PAUSE", "SHUTDOWN"]) await sandbox.sendCommand(command);
    assert.deepEqual(requests.filter(request => request.options?.method === "POST").map(request => JSON.parse(request.options.body)),
        ["START", "PAUSE", "SHUTDOWN"].map(command => ({ device: "ARM", command })));
});