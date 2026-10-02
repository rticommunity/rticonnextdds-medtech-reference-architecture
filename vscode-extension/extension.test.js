const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

test("arm drawing keeps upstream joints fixed when a downstream joint moves", () => {
    const source = fs.readFileSync(path.join(__dirname, "../modules/01-operating-room/web-arm/app.js"), "utf8");
    const circles = [];
    const ctx = Object.fromEntries(["setTransform", "clearRect", "fillRect", "fillText", "beginPath", "moveTo", "lineTo", "stroke", "fill", "closePath"].map(name => [name, () => {}]));
    ctx.arc = (horizontal, vertical) => circles.push([horizontal, vertical]);
    const sandbox = {
        ctx, canvas: { width: 270, height: 285, getBoundingClientRect: () => ({ width: 270, height: 285 }) },
        window: { devicePixelRatio: 1 }, JOINT_ORDER: ["BASE", "SHOULDER", "ELBOW", "WRIST", "HAND"],
        JOINT_COLORS: {}, armView: { zoom: 1, panX: 0, panY: 0 }, displayedAngles: {},
        document: { getElementById: () => ({ addEventListener() {} }) },
    };
    sandbox.canvas.addEventListener = () => {};
    vm.runInNewContext(source.slice(source.indexOf("function drawArm("), source.indexOf("\nasync function pollState(")), sandbox);
    const angles = { BASE: 180, SHOULDER: 180, ELBOW: 180, WRIST: 180, HAND: 180 };
    sandbox.drawArm(angles);
    const initial = circles.splice(0);
    assert.ok(initial[0][1] - initial[4][1] >= 150, "Default arm must occupy most of the pane height");
    sandbox.drawArm({ ...angles, WRIST: 240 });
    assert.deepEqual(circles.slice(0, 4), initial.slice(0, 4));
    assert.notDeepEqual(circles[4], initial[4]);
    for (let angle = 0; angle <= 360; angle += 30) {
        circles.length = 0;
        sandbox.drawArm(Object.fromEntries(Object.keys(angles).map(joint => [joint, angle])));
        assert.deepEqual(circles[0], initial[0]);
        sandbox.fitArmView();
        const fitted = circles.slice(-5);
        assert.ok(fitted.every(([horizontal, vertical]) => horizontal >= 8 && horizontal <= 262 && vertical >= 8 && vertical <= 277));
        sandbox.armView.zoom = 1;
        sandbox.armView.panX = 0;
        sandbox.armView.panY = 0;
    }
});

test("device logs simplify known DDS prefixes and apply each app's scroll policy", () => {
    for (const app of ["web", "web-armcontroller"]) {
        const source = fs.readFileSync(path.join(__dirname, `../modules/01-operating-room/${app}/app.js`), "utf8");
        const alertsEl = { textContent: "", scrollHeight: 0, clientHeight: 80, scrollTop: 0 };
        const sandbox = { alertsEl };
        vm.runInNewContext('let lastAlertText = "";\n' + source.slice(
            source.indexOf("function formatAlert("), source.indexOf("\nasync function pollState(")), sandbox);
        const cases = [
            ["2026-10-02 18:00:00 - Started Arm Controller (web mode)", "2026-10-02 18:00:00 - Started Arm Controller"],
            ["Started Orchestrator (web mode)", "Started Orchestrator"],
            ["Writing DeviceCommands::SHUTDOWN to DeviceType::ARM_CONTROLLER", "Writing SHUTDOWN to ARM_CONTROLLER"],
            ["Received DeviceStatuses::ON status message from DeviceType::ARM", "Received ON status message from ARM"],
            ["Unknown::VALUE and MyDeviceType::ARM remain unchanged", "Unknown::VALUE and MyDeviceType::ARM remain unchanged"],
            ["The (web mode) setting is enabled", "The (web mode) setting is enabled"],
        ];
        for (const [raw, expected] of cases) assert.equal(sandbox.formatAlert(raw), expected);
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

function launcherModule(vscode) {
    const sandbox = {
        module: { exports: {} }, process,
        setInterval() { return 1; }, clearInterval() {},
        require(name) { return name === "vscode" ? vscode : require(name); },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
    return sandbox.module.exports;
}

test("Orchestrator device grid keeps the requested order regardless of API order", () => {
    const cards = [];
    const element = () => ({ textContent: "", classList: { toggle() {} }, addEventListener() {}, appendChild() {}, dataset: {} });
    const devicesEl = { appendChild(card) { cards.push(card); }, set innerHTML(value) { cards.length = 0; } };
    const sandbox = {
        window: { addEventListener() {} },
        document: { getElementById: id => id === "devices" ? devicesEl : element(), createElement: element },
        fetch: async () => ({ ok: false }), setInterval() {}, console,
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../modules/01-operating-room/web/app.js"), "utf8"), sandbox);
    const expected = ["ARM_CONTROLLER", "PATIENT_SENSOR", "ARM", "PATIENT_MONITOR"];
    for (const order of [["ARM", "ARM_CONTROLLER", "PATIENT_MONITOR", "PATIENT_SENSOR"], [...expected].reverse()]) {
        const devices = Object.freeze(order.map(id => Object.freeze({ id, status: "ON" })));
        sandbox.renderDevices(devices);
        assert.deepEqual(cards.map(card => card.dataset.deviceId), expected);
        assert.deepEqual(devices.map(device => device.id), order);
        cards[2].classList.toggle = (_name, selected) => assert.equal(selected, true);
        sandbox.document.querySelectorAll = () => cards;
        sandbox.selectDevice("ARM");
        cards[2].classList.toggle = () => {};
    }
});

test("Orchestrator Start uses recovery for stopped apps and DDS for running apps", async () => {
    for (const [state, deviceStatus, shutdownRequested] of [["starting", "OFF"], ["running", "PAUSED"], ["unknown", "OFF"], ["starting", "ON", true]]) {
        const elements = new Map();
        const element = () => ({ textContent: "", disabled: false, classList: { toggle() {} }, addEventListener() {}, appendChild() {}, dataset: {} });
        const requests = [];
        const starts = [];
        let onMessage;
        const parent = { postMessage(message) { starts.push(message); queueMicrotask(() => onMessage({
            source: parent, origin: "http://127.0.0.1:8080", data: { type: "medtech-device-start-result", requestId: message.requestId, status: state },
        })); } };
        const sandbox = {
            window: { parent, addEventListener(_event, callback) { onMessage = callback; } },
            document: {
                getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
                createElement: element, querySelectorAll() { return []; },
            },
            fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => ({ devices: [] }) }; },
            setInterval() { return 1; }, clearInterval() {}, setTimeout, clearTimeout, console: { warn() {} },
        };
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../modules/01-operating-room/web/app.js"), "utf8"), sandbox);
        onMessage({ source: parent, origin: "http://127.0.0.1:8080", data: { type: "medtech-launcher-ready" } });
        sandbox.renderDevices([{ id: "ARM", status: deviceStatus }]);
        sandbox.selectDevice("ARM");
        if (shutdownRequested) await sandbox.sendCommand("SHUTDOWN");
        await sandbox.sendCommand("START");
        assert.equal(starts[0].stopped, !!shutdownRequested || deviceStatus === "OFF");
        const commands = requests.filter(request => request.options?.method === "POST" && JSON.parse(request.options.body).command === "START");
        assert.equal(commands.length, state === "running" ? 1 : 0);
        if (state === "running") assert.deepEqual(JSON.parse(commands[0].options.body), { device: "ARM", command: "START" });
        assert.equal(elements.get("btn-start").disabled, state === "starting");
        if (state === "unknown") assert.match(elements.get("command-status").textContent, /cannot be started/);
    }
});

test("Orchestrator bridge accepts messages only from its own device frame and origin", () => {
    const sandbox = { module: { exports: {} }, process, URL, URLSearchParams,
        require(name) { return name === "vscode" ? { ViewColumn: {} } : require(name); } };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
    const html = sandbox.module.exports.webviewHtml(new URL("http://127.0.0.1:8080/proxy/8090/"), "Orchestrator");
    const script = html.match(/<script nonce="medtech-orchestrator">([\s\S]*?)<\/script>/)[1];
    const forwarded = [];
    const replies = [];
    let onMessage;
    let onLoad;
    const frame = { contentWindow: { postMessage(message, origin) { replies.push({ message, origin }); } },
        addEventListener(_event, callback) { onLoad = callback; } };
    vm.runInNewContext(script, {
        acquireVsCodeApi: () => ({ postMessage(message) { forwarded.push(message); } }),
        document: { querySelector: () => frame }, window: { addEventListener(_event, callback) { onMessage = callback; } },
    });
    const data = { type: "medtech-device-start", device: "ARM", requestId: 1 };
    onMessage({ source: {}, origin: "http://127.0.0.1:8080", data });
    onMessage({ source: frame.contentWindow, origin: "http://evil.invalid", data });
    assert.equal(forwarded.length, 0);
    onMessage({ source: frame.contentWindow, origin: "http://127.0.0.1:8080", data });
    assert.deepEqual(JSON.parse(JSON.stringify(forwarded)), [{ action: "start", device: "ARM", requestId: 1, stopped: false }]);
    onLoad();
    assert.equal(replies[0].message.type, "medtech-launcher-ready");
    assert.equal(replies[0].origin, "http://127.0.0.1:8080");
});

test("Orchestrator device messages and recovery command use the guarded launcher", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-start-test-"));
    const started = [];
    const replies = [];
    let handler;
    let onMessage;
    let command;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4 },
        commands: { executeCommand: async () => {}, registerCommand(name, callback) { command = callback; assert.equal(name, "rti.medtech.openOrchestrator"); return {}; } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            showErrorMessage(message) { throw new Error(message); },
            createWebviewPanel() { return { webview: {
                onDidReceiveMessage(callback) { onMessage = callback; }, postMessage(message) { replies.push(message); },
            }, onDidDispose() {} }; },
        },
    };
    const sandbox = { module: { exports: {} }, process, URL, URLSearchParams,
        require(name) {
            if (name === "vscode") return vscode;
            if (name === "os") return { tmpdir: () => directory };
            if (name === "fs") return { ...fs, existsSync: file => file !== "/app/code-server" && fs.existsSync(file) };
            if (name === "./device-launcher") return {
                DEVICE_NAMES: { ARM: "Arm", ARM_CONTROLLER: "ArmController", PATIENT_MONITOR: "PatientMonitor", PATIENT_SENSOR: "PatientSensor" },
                DeviceLauncher: class { constructor() { this.seenDevices = new Set(); this.pendingRestores = new Map(); } startMonitoring() {} async restoreDevice(name) { started.push(name); return "starting"; } stop() {} },
            };
            return require(name);
        },
    };
    try {
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
        sandbox.module.exports.activate({ subscriptions: [] });
        await handler.handleUri({ path: "/open", query: "title=Orchestrator&url=http%3A%2F%2Flocalhost%3A8090%2F" });
        await onMessage({ action: "start", device: "arbitrary-script", requestId: 1 });
        await onMessage({ action: "start", device: "ARM", requestId: "bad" });
        assert.equal(started.length, 0);
        for (const device of ["ARM", "ARM_CONTROLLER", "PATIENT_MONITOR", "PATIENT_SENSOR"]) {
            await onMessage({ action: "start", device, requestId: 2 });
        }
        assert.deepEqual(started, ["Arm", "ArmController", "PatientMonitor", "PatientSensor"]);
        assert.ok(replies.every(reply => reply.type === "medtech-device-start-result" && reply.status === "starting"));
        await command();
        assert.equal(started.at(-1), "Orchestrator");
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});

test("sensor health requires an owned record and distinguishes alive, stopped and unknown", () => {
    for (const [record, error, expected] of [[{ pid: 123 }, null, true], [{ pid: 123 }, "ESRCH", false], [{ pid: null }, null, false], [{ pid: -1 }, null, null], [null, "ENOENT", null]]) {
        const sandbox = { module: { exports: {} }, process: { getuid: () => 911, kill() { if (error) throw Object.assign(new Error(error), { code: error }); } },
            require(name) {
                if (name === "vscode") return {};
                if (name === "fs") return { readFileSync() { if (record === null) throw Object.assign(new Error("missing"), { code: error }); return JSON.stringify(record); } };
                return require(name);
            },
        };
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
        assert.equal(sandbox.module.exports.sensorRunning(), expected);
    }
});

for (const device of ["Arm", "PatientSensor"]) test(`immediate Start waits for ${device} to stop before relaunching`, async () => {
    let probes = 0;
    let spawned = 0;
    const sandbox = { module: { exports: {} }, process, setTimeout,
        require(name) {
            if (name === "vscode") return {};
            if (name === "fs") return { ...fs, readFileSync(file, ...args) {
                if (file.endsWith("PatientSensor.process")) return JSON.stringify({ pid: ++probes === 1 ? process.pid : null });
                return fs.readFileSync(file, ...args);
            } };
            if (name === "http") return { get(_url, callback) {
                probes++;
                if (probes === 1) callback({ resume() {} });
                return { setTimeout() {}, on(_event, onError) { if (probes > 1) onError({ code: probes === 2 ? "ECONNRESET" : "ECONNREFUSED" }); } };
            } };
            if (name === "child_process") return { spawn() { spawned++; return { pid: 12345, exitCode: null, on() {} }; } };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
    const controller = new sandbox.module.exports.DeviceLauncher({ subscriptions: [] });
    controller.root = "/workspace";
    controller.active = true;
    assert.equal(await controller.restoreDevice(device, true), "starting");
    assert.equal(probes, device === "PatientSensor" ? 2 : 3);
    assert.equal(spawned, 1);
});

test("cloud frames use code-server proxy paths on port 8080", () => {
    const sandbox = {
        module: { exports: {} }, process, URL, URLSearchParams,
        require(name) {
            if (name === "vscode") return { ViewColumn: {} };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
    assert.equal(sandbox.module.exports.cloudTargetUrl(new URL("http://localhost:8092/")).href,
        "http://127.0.0.1:8080/proxy/8092/");
});

test("device extension contributes no tutorial panel or activity-bar container", () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "package.json"), "utf8"));
    assert.equal(manifest.contributes.views, undefined);
    assert.equal(manifest.contributes.viewsContainers, undefined);
    assert.ok(!fs.existsSync(path.join(__dirname, "tutorial-view.js")));
    assert.ok(!fs.readFileSync(path.join(__dirname, "extension.js"), "utf8").includes("registerWebviewViewProvider"));
});

test("only the focused cloud extension host consumes launcher requests", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-owner-test-"));
    const hosts = [];
    try {
        for (const pid of [101, 202]) {
            const host = { sessions: 0, stops: 0 };
            const vscode = {
                ViewColumn: {},
                commands: {},
                window: {
                    registerUriHandler: () => ({}), registerWebviewViewProvider() { assert.fail("Tutorial panel must not be registered"); },
                    onDidChangeWindowState(callback) { host.focus = callback; return {}; },
                    showErrorMessage(message) { throw new Error(message); },
                },
            };
            const sandbox = {
                module: { exports: {} }, URL, URLSearchParams,
                process: { pid, getuid: process.getuid, env: {} },
                setInterval(callback) { host.tick = callback; return 1; }, clearInterval() {},
                require(name) {
                    if (name === "vscode") return vscode;
                    if (name === "./device-launcher") return { DeviceLauncher: class {
                        startMonitoring() {} stop() { host.stops++; }
                        set active(value) { if (value) host.sessions++; }
                    } };
                    if (name === "os") return { tmpdir: () => directory };
                    if (name === "fs") return { ...fs, existsSync: file => file === "/app/code-server" || fs.existsSync(file) };
                    return require(name);
                },
            };
            vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
            sandbox.module.exports.activate({ subscriptions: [] });
            hosts.push(host);
        }
        const requests = path.join(directory, `medtech-web-tabs-${process.getuid()}`, "requests");
        const send = () => fs.writeFileSync(path.join(requests, "test.json"), JSON.stringify({ uri: "vscode://rti.medtech-web-tabs/session" }));
        send();
        await hosts[0].tick();
        assert.equal(hosts[0].sessions, 0);
        await hosts[1].tick();
        assert.equal(hosts[1].sessions, 1);
        hosts[0].focus({ focused: true });
        send();
        await hosts[1].tick();
        await hosts[0].tick();
        assert.equal(hosts[0].sessions, 1);
        assert.equal(hosts[1].sessions, 1);
        fs.writeFileSync(path.join(requests, "targeted.json"), JSON.stringify({
            uri: "vscode://rti.medtech-web-tabs/close", targetHost: "202",
        }));
        await hosts[0].tick();
        assert.equal(hosts[0].stops, 0);
        await hosts[1].tick();
        assert.equal(hosts[1].stops, 1);
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});

test("device recovery cannot start devices before a full demo launch", async () => {
    let spawned = false;
    const sandbox = {
        module: { exports: {} },
        require(name) {
            if (name === "vscode") return {};
            if (name === "child_process") return { spawn() { spawned = true; } };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
    const view = new sandbox.module.exports.DeviceLauncher({ subscriptions: [] });
    await view.restoreDevice("Arm");
    assert.equal(spawned, false);
    assert.equal(view.active, false);
});

test("restored devices have owned process groups that shutdown stops together", async () => {
    const signals = [];
    let options;
    const sandbox = {
        module: { exports: {} },
        process: { env: {}, kill: (pid, signal) => signals.push([pid, signal]) },
        require(name) {
            if (name === "vscode") return {};
            if (name === "http") return { get: () => ({
                setTimeout() {}, on(_event, callback) { callback({ code: "ECONNREFUSED" }); },
            }) };
            if (name === "child_process") return { spawn(_command, _args, value) {
                options = value;
                return { pid: 12345, exitCode: null, on() {} };
            } };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
    const view = new sandbox.module.exports.DeviceLauncher({ subscriptions: [] });
    view.root = "/workspace";
    view.active = true;
    await view.restoreDevice("Arm");
    assert.equal(options.detached, true);
    view.stop();
    assert.deepEqual(signals, [[-12345, "SIGTERM"]]);
    assert.equal(view.active, false);
});

test("device health detects stopped restored devices even while their launcher is alive", async () => {
    const messages = [];
    let spawned = 0;
    const sandbox = {
        module: { exports: {} }, process,
        require(name) {
            if (name === "vscode") return {
                workspace: { workspaceFolders: [{ uri: { fsPath: path.resolve(__dirname, "../..") } }] },
            };
            if (name === "http") return { get: () => ({
                setTimeout() {}, on(_event, callback) { callback({ code: "ECONNREFUSED" }); },
            }) };
            if (name === "child_process") return { spawn() {
                spawned++;
                return { pid: 12345, exitCode: null, on() {} };
            } };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
    const tutorial = new sandbox.module.exports.DeviceLauncher({ subscriptions: [] });
    tutorial.active = true;
    tutorial.children.set("Arm", { pid: 12344, exitCode: null });
    assert.equal((await tutorial.refreshHealth()).Arm, false);
    await tutorial.restoreDevice("Arm");
    assert.equal(spawned, 1);
    await tutorial.restoreDevice("Arm");
    assert.equal(spawned, 1);
});

test("device health releases startup guards as soon as devices are healthy", async () => {
    const messages = [];
    let tick;
    let running = true;
    let probes = 0;
    const sandbox = {
        module: { exports: {} },
        setInterval(callback) { tick = callback; return 1; }, clearInterval() {},
        require(name) {
            if (name === "vscode") return {
                workspace: { workspaceFolders: [{ uri: { fsPath: path.resolve(__dirname, "../..") } }] },
            };
            if (name === "http") return { get(_url, callback) {
                probes++;
                if (running === true) callback({ resume() {} });
                return {
                    setTimeout() {}, on(_event, onError) {
                        if (running !== true) onError({ code: running === false ? "ECONNREFUSED" : "ECONNRESET" });
                    },
                };
            } };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
    const tutorial = new sandbox.module.exports.DeviceLauncher({ subscriptions: [] });
    tutorial.active = true;
    tutorial.startupDeadline = Date.now() + 15000;
    tutorial.pendingRestores.set("Arm", Date.now() + 15000);
    await tutorial.refreshHealth();
    assert.equal(tutorial.pendingRestores.has("Arm"), false);
    assert.equal(probes, 4);
    running = false;
    for (const state of Object.values(await tutorial.refreshHealth())) assert.equal(state, false);
    running = null;
    for (const state of Object.values(await tutorial.refreshHealth())) assert.equal(state, null);
    tutorial.stop();
    for (const state of Object.values(await tutorial.refreshHealth())) assert.equal(state, true);
});

test("concurrent Restore clicks start only one launcher and failures release the lock", async () => {
    const probes = [];
    const callbacks = {};
    let spawned = 0;
    const sandbox = {
        module: { exports: {} }, process,
        require(name) {
            if (name === "vscode") return { window: { showErrorMessage() {} } };
            if (name === "http") return { get: () => ({
                setTimeout() {}, on(_event, callback) { probes.push(callback); },
            }) };
            if (name === "child_process") return { spawn() {
                spawned++;
                return { pid: 12345, exitCode: null, on(event, callback) { callbacks[event] = callback; } };
            } };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "device-launcher.js"), "utf8"), sandbox);
    const tutorial = new sandbox.module.exports.DeviceLauncher({ subscriptions: [] });
    tutorial.root = "/workspace";
    tutorial.active = true;
    const restore = tutorial.restoreDevice("Arm");
    await tutorial.restoreDevice("Arm");
    assert.equal(probes.length, 1);
    probes[0]({ code: "ECONNREFUSED" });
    await restore;
    assert.equal(spawned, 1);
    callbacks.error(new Error("spawn failed"));
    assert.equal(tutorial.restorePending("Arm"), false);
    assert.equal(tutorial.ownedChildren.size, 0);
    const retry = tutorial.restoreDevice("Arm");
    probes[1]({ code: "ECONNRESET" });
    await retry;
    assert.equal(spawned, 1);
    assert.equal(tutorial.restorePending("Arm"), false);
});

test("concurrent opens reuse one panel and disposal explicitly reports closed", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-tabs-test-"));
    const panels = [];
    let documentWrites = 0;
    let layoutCount = 0;
    let handler;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        commands: { executeCommand: async () => { layoutCount++; } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            createWebviewPanel() {
                const panel = {
                    webview: { set html(value) { documentWrites++; this.content = value; }, get html() { return this.content; } },
                    reveal() {},
                    onDidChangeViewState(callback) { this.onChangeViewState = callback; },
                    onDidDispose(callback) { this.onDispose = callback; },
                    dispose() { this.onDispose(); },
                };
                panels.push(panel);
                return panel;
            },
            showErrorMessage(message) { throw new Error(message); },
        },
    };
    const sandbox = {
        module: { exports: {} },
        process,
        URL,
        URLSearchParams,
        require(name) {
            if (name === "vscode") return vscode;
            if (name === "./device-launcher") return launcherModule(vscode);
            if (name === "fs") return { ...fs, existsSync: file => file !== "/app/code-server" && fs.existsSync(file) };
            if (name === "os") return { tmpdir: () => directory };
            return require(name);
        },
    };
    try {
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
        sandbox.module.exports.activate({ subscriptions: [] });
        const request = {
            path: "/open",
            query: new URLSearchParams({
                url: "http://localhost:8092/", title: "Arm", closeToken: "a".repeat(32),
            }).toString(),
        };
        await Promise.all([handler.handleUri(request), handler.handleUri(request)]);
        assert.equal(layoutCount, 1);
        assert.equal(panels.length, 1);
        assert.equal(documentWrites, 1);
        const marker = path.join(directory, `medtech-web-tabs-${process.getuid()}`, "Arm");
        assert.equal(fs.readFileSync(marker, "utf8"), String(process.pid));
        panels[0].dispose();
        assert.equal(fs.readFileSync(marker, "utf8"), String(-process.pid));
        const closeRequest = path.join(path.dirname(marker), `${"a".repeat(32)}.close`);
        assert.equal(fs.existsSync(closeRequest), true);
        fs.unlinkSync(closeRequest);
        await handler.handleUri(request);
        assert.equal(panels.length, 2);
        assert.equal(fs.readFileSync(marker, "utf8"), String(process.pid));
        const restarted = { ...request, query: request.query.replace("a".repeat(32), "b".repeat(32)) };
        await handler.handleUri(restarted);
        assert.equal(panels.length, 2);
        assert.equal(documentWrites, 3);
        await handler.handleUri(restarted);
        assert.equal(documentWrites, 3);
        await handler.handleUri({ path: "/close", query: "title=Arm" });
        assert.equal(fs.readFileSync(marker, "utf8"), String(-process.pid));
        assert.equal(fs.existsSync(closeRequest), false);
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});

test("restoring Arm keeps all four tabs in separate grid slots", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-grid-test-"));
    const panels = [];
    const layoutCommands = [];
    const settings = [];
    let workspaceValue;
    let emptyArmSlot = false;
    let handler;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        ConfigurationTarget: { Workspace: 2 },
        workspace: { getConfiguration(section) {
            assert.equal(section, "workbench.editor");
            return {
                inspect() { return { workspaceValue }; },
                async update(name, value, target) {
                    assert.equal(name, "closeEmptyGroups");
                    assert.equal(target, 2);
                    workspaceValue = value;
                    settings.push(value);
                },
            };
        } },
        commands: { executeCommand: async (name, layout) => {
            if (name === "vscode.setEditorLayout") assert.equal(layout.orientation, 1);
            layoutCommands.push(name);
            if (layoutCommands.length > 1) {
                emptyArmSlot = true;
            }
        } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            createWebviewPanel(_type, title, viewColumn) {
                if (typeof viewColumn === "object") {
                    assert.equal(viewColumn.preserveFocus, true);
                    viewColumn = viewColumn.viewColumn;
                }
                const panel = {
                    title,
                    viewColumn,
                    slot: title === "Arm" && layoutCommands.length > 1 && !emptyArmSlot
                        ? "bottom-left" : {
                            ArmController: "top-left", Arm: "bottom-left",
                            Orchestrator: "top-right", PatientMonitor: "bottom-right",
                        }[title],
                    webview: { html: "" },
                    reveal(column) {
                        if (emptyArmSlot && this.title === "Orchestrator") {
                            this.viewColumn = vscode.ViewColumn.Two;
                            emptyArmSlot = false;
                        } else if (column) {
                            this.viewColumn = column;
                        }
                        this.onChangeViewState?.();
                    },
                    onDidChangeViewState(callback) { this.onChangeViewState = callback; },
                    onDidDispose(callback) { this.onDispose = callback; },
                    dispose() { this.onDispose(); },
                };
                if (title === "Arm") emptyArmSlot = false;
                panels.push(panel);
                return panel;
            },
            showErrorMessage(message) { throw new Error(message); },
        },
    };
    const sandbox = {
        module: { exports: {} }, process, URL, URLSearchParams,
        require(name) {
            if (name === "vscode") return vscode;
            if (name === "./device-launcher") return launcherModule(vscode);
            if (name === "fs") return { ...fs, existsSync: file => file !== "/app/code-server" && fs.existsSync(file) };
            if (name === "os") return { tmpdir: () => directory };
            return require(name);
        },
    };
    try {
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
        sandbox.module.exports.activate({ subscriptions: [] });
        const open = (title, port) => handler.handleUri({
            path: "/open",
            query: new URLSearchParams({ url: `http://localhost:${port}/`, title }).toString(),
        });
        await open("ArmController", 8091);
        await open("Arm", 8092);
        await open("Orchestrator", 8094);
        await open("PatientMonitor", 8093);
        panels[1].viewColumn = vscode.ViewColumn.Two;
        panels[1].onChangeViewState?.();
        panels[1].dispose();
        await open("Arm", 8092);
        assert.equal(layoutCommands.length, 1);
        assert.equal(panels.length, 5);
        const currentPanels = [panels[0], panels[4], panels[2], panels[3]];
        assert.deepEqual(currentPanels.map((panel) => panel.viewColumn), [1, 3, 2, 4]);
        assert.deepEqual(currentPanels.map((panel) => panel.slot),
            ["top-left", "bottom-left", "top-right", "bottom-right"]);
        panels[4].dispose();
        await open("Arm", 8092);
        assert.equal(layoutCommands.length, 1);
        assert.equal(panels.length, 6);
        assert.deepEqual([panels[0], panels[5], panels[2], panels[3]].map((panel) => panel.viewColumn), [1, 3, 2, 4]);
        assert.equal(panels[5].slot, "bottom-left");
        assert.deepEqual(settings, [false]);
        await sandbox.module.exports.deactivate();
        assert.deepEqual(settings, [false, undefined]);
        await handler.handleUri({ path: "/close", query: "" });
        assert.deepEqual(settings, [false, undefined]);
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});

test("recovery preserves surviving panels, documents and close tokens", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-grid-close-test-"));
    const panels = new Map();
    let handler;
    let layoutCount = 0;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        commands: { executeCommand: async (name) => {
            if (++layoutCount === 2 && name === "workbench.action.editorLayoutTwoByTwoGrid") {
                panels.get("Orchestrator").dispose();
                panels.get("PatientMonitor").dispose();
            }
        } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            createWebviewPanel(_type, title) {
                const panel = {
                    webview: { html: "" },
                    reveal() {},
                    onDidDispose(callback) { this.onDispose = callback; },
                    dispose() { this.onDispose(); },
                };
                panels.set(title, panel);
                return panel;
            },
            showErrorMessage(message) { throw new Error(message); },
        },
    };
    const sandbox = {
        module: { exports: {} }, process, URL, URLSearchParams,
        require(name) {
            if (name === "vscode") return vscode;
            if (name === "./device-launcher") return launcherModule(vscode);
            if (name === "fs") return { ...fs, existsSync: file => file !== "/app/code-server" && fs.existsSync(file) };
            if (name === "os") return { tmpdir: () => directory };
            return require(name);
        },
    };
    try {
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
        sandbox.module.exports.activate({ subscriptions: [] });
        const open = (title, port, token) => handler.handleUri({
            path: "/open",
            query: new URLSearchParams({
                url: `http://localhost:${port}/`, title, closeToken: token,
            }).toString(),
        });
        await open("ArmController", 8091, "a".repeat(32));
        await open("Orchestrator", 8090, "b".repeat(32));
        await open("PatientMonitor", 8093, "c".repeat(32));
        const survivors = [panels.get("Orchestrator"), panels.get("PatientMonitor")];
        const documents = survivors.map(panel => panel.webview.html);
        panels.get("ArmController").dispose();
        await open("ArmController", 8091, "d".repeat(32));
        assert.equal(panels.get("Orchestrator"), survivors[0]);
        assert.equal(panels.get("PatientMonitor"), survivors[1]);
        assert.deepEqual(survivors.map(panel => panel.webview.html), documents);
        const stateDir = path.join(directory, `medtech-web-tabs-${process.getuid()}`);
        assert.equal(fs.existsSync(path.join(stateDir, `${"b".repeat(32)}.close`)), false);
        assert.equal(fs.existsSync(path.join(stateDir, `${"c".repeat(32)}.close`)), false);
        assert.equal(fs.readFileSync(path.join(stateDir, "Orchestrator"), "utf8"), String(process.pid));
        assert.equal(fs.readFileSync(path.join(stateDir, "PatientMonitor"), "utf8"), String(process.pid));
        panels.get("Orchestrator").dispose();
        assert.equal(fs.existsSync(path.join(stateDir, `${"b".repeat(32)}.close`)), true);
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});

test("restoring ArmController preserves the Orchestrator panel and focus", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-controller-test-"));
    const panels = new Map();
    let handler;
    let layoutCount = 0;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        commands: { executeCommand: async (name) => {
            if (++layoutCount > 1 && name === "workbench.action.editorLayoutTwoByTwoGrid") {
                const oldPanel = panels.get("Orchestrator");
                setImmediate(() => oldPanel.dispose());
            }
        } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            createWebviewPanel(_type, title, column) {
                if (typeof column === "object") {
                    assert.equal(column.preserveFocus, true);
                    column = column.viewColumn;
                }
                const panel = {
                    column,
                    webview: { html: "" },
                    reveal() {},
                    onDidDispose(callback) { this.onDispose = callback; },
                    dispose() { setImmediate(() => this.onDispose()); },
                };
                panels.set(title, panel);
                return panel;
            },
            showErrorMessage(message) { throw new Error(message); },
        },
    };
    const sandbox = {
        module: { exports: {} }, process, URL, URLSearchParams,
        require(name) {
            if (name === "vscode") return vscode;
            if (name === "./device-launcher") return launcherModule(vscode);
            if (name === "fs") return { ...fs, existsSync: file => file !== "/app/code-server" && fs.existsSync(file) };
            if (name === "os") return { tmpdir: () => directory };
            return require(name);
        },
    };
    try {
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "extension.js"), "utf8"), sandbox);
        sandbox.module.exports.activate({ subscriptions: [] });
        const open = (title, port, token) => handler.handleUri({
            path: "/open",
            query: new URLSearchParams({
                url: `http://localhost:${port}/`, title, closeToken: token,
            }).toString(),
        });
        await open("ArmController", 8091, "a".repeat(32));
        await open("Orchestrator", 8090, "b".repeat(32));
        const orchestrator = panels.get("Orchestrator");
        await handler.handleUri({ path: "/close", query: "title=ArmController" });
        await new Promise((resolve) => setImmediate(resolve));
        await open("ArmController", 8091, "c".repeat(32));
        await new Promise((resolve) => setImmediate(resolve));
        const stateDir = path.join(directory, `medtech-web-tabs-${process.getuid()}`);
        assert.equal(layoutCount, 1);
        assert.equal(panels.get("Orchestrator"), orchestrator);
        assert.equal(panels.get("ArmController").column, vscode.ViewColumn.One);
        assert.equal(panels.get("Orchestrator").column, vscode.ViewColumn.Two);
        assert.equal(fs.readFileSync(path.join(stateDir, "Orchestrator"), "utf8"), String(process.pid));
        assert.equal(fs.existsSync(path.join(stateDir, `${"b".repeat(32)}.close`)), false);
        await handler.handleUri({ path: "/close-owned", query: "" });
        await handler.handleUri({ path: "/close-owned", query: "closeToken=invalid" });
        await handler.handleUri({ path: "/close-owned", query: `closeToken=${"a".repeat(32)}` });
        assert.equal(panels.get("ArmController").closedByLauncher, undefined);
        assert.equal(orchestrator.closedByLauncher, undefined);
        await handler.handleUri({ path: "/close-owned", query: `closeToken=${"c".repeat(32)}` });
        await new Promise((resolve) => setImmediate(resolve));
        assert.equal(panels.get("ArmController").closedByLauncher, true);
        assert.equal(orchestrator.closedByLauncher, undefined);
        assert.equal(fs.existsSync(path.join(stateDir, `${"c".repeat(32)}.close`)), false);
        panels.get("Orchestrator").dispose();
        await new Promise((resolve) => setImmediate(resolve));
        assert.equal(fs.existsSync(path.join(stateDir, `${"b".repeat(32)}.close`)), true);
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});