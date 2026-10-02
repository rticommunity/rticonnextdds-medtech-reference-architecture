const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function tutorialModule(vscode) {
    const sandbox = {
        module: { exports: {} }, process,
        require(name) { return name === "vscode" ? vscode : require(name); },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    return sandbox.module.exports;
}

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
            if (name === "./tutorial-view") return {
                DEVICE_NAMES: { ARM: "Arm", ARM_CONTROLLER: "ArmController", PATIENT_MONITOR: "PatientMonitor", PATIENT_SENSOR: "PatientSensor" },
                TutorialView: class { constructor() { this.seenDevices = new Set(); this.pendingRestores = new Map(); } async restoreDevice(name) { started.push(name); return "starting"; } stop() {} },
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
        vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
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
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    const controller = new sandbox.module.exports.TutorialView({ subscriptions: [] });
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

test("tutorial sidebar includes all steps and escaped file actions without recovery controls", () => {
    const sandbox = {
        module: { exports: {} },
        require(name) { return name === "vscode" ? {} : require(name); },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    const tutorial = JSON.parse(fs.readFileSync(path.join(__dirname, "../../tutorial/digital-or-tutorial.json"), "utf8"));
    tutorial.steps[0].body.push("<script>unsafe</script>");
    const html = sandbox.module.exports.tutorialHtml(tutorial);
    assert.equal((html.match(/<details /g) || []).length, 10);
    assert.equal((html.match(/<button data-action="restore"/g) || []).length, 0);
    assert.ok(html.includes("Open Types.xml"));
    assert.ok(html.includes("&lt;script&gt;unsafe&lt;/script&gt;"));
    assert.ok(!html.includes("<script>unsafe"));
});

test("only the focused cloud extension host consumes launcher requests", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-owner-test-"));
    const hosts = [];
    try {
        for (const pid of [101, 202]) {
            const host = { commands: [] };
            const vscode = {
                ViewColumn: {},
                commands: { executeCommand: async name => host.commands.push(name) },
                window: {
                    registerUriHandler: () => ({}), registerWebviewViewProvider: () => ({}),
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
                    if (name === "./tutorial-view") return { TutorialView: class { stop() {} } };
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
        const send = () => fs.writeFileSync(path.join(requests, "test.json"), JSON.stringify({ uri: "vscode://rti.medtech-web-tabs/tutorial" }));
        send();
        await hosts[0].tick();
        assert.equal(hosts[0].commands.length, 0);
        await hosts[1].tick();
        assert.deepEqual(hosts[1].commands, ["rti.medtechTutorial.focus"]);
        hosts[0].focus({ focused: true });
        send();
        await hosts[1].tick();
        await hosts[0].tick();
        assert.deepEqual(hosts[0].commands, ["rti.medtechTutorial.focus"]);
        assert.equal(hosts[1].commands.length, 1);
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});

test("sidebar recovery cannot start devices before a full demo launch", async () => {
    let spawned = false;
    const sandbox = {
        module: { exports: {} },
        require(name) {
            if (name === "vscode") return {};
            if (name === "child_process") return { spawn() { spawned = true; } };
            return require(name);
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    const view = new sandbox.module.exports.TutorialView({ subscriptions: [] });
    await view.handleMessage({ action: "restore", name: "Arm" });
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
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    const view = new sandbox.module.exports.TutorialView({ subscriptions: [] });
    view.root = "/workspace";
    view.active = true;
    await view.handleMessage({ action: "restore", name: "Arm" });
    assert.equal(options.detached, true);
    view.stop();
    assert.deepEqual(signals, [[-12345, "SIGTERM"]]);
    assert.equal(view.active, false);
});

test("sidebar detects stopped restored devices even while their launcher is alive", async () => {
    const messages = [];
    let tick;
    let interval;
    let spawned = 0;
    const sandbox = {
        module: { exports: {} }, process,
        setInterval(callback, milliseconds) { tick = callback; interval = milliseconds; return 1; },
        clearInterval() {},
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
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    const tutorial = new sandbox.module.exports.TutorialView({ subscriptions: [] });
    tutorial.active = true;
    tutorial.children.set("Arm", { pid: 12344, exitCode: null });
    tutorial.resolveWebviewView({
        webview: { onDidReceiveMessage() { return {}; }, postMessage(message) { messages.push(message); } },
        onDidChangeVisibility() { return {}; }, onDidDispose() {},
    });
    await new Promise(resolve => setImmediate(resolve));
    await tick();
    assert.equal(messages.at(-1).devices.Arm, false);
    assert.ok(interval <= 250);
    await tutorial.handleMessage({ action: "restore", name: "Arm" });
    assert.equal(spawned, 1);
    await tutorial.handleMessage({ action: "restore", name: "Arm" });
    assert.equal(spawned, 1);
});

test("sidebar releases startup guards as soon as devices are healthy", async () => {
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
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    const tutorial = new sandbox.module.exports.TutorialView({ subscriptions: [] });
    tutorial.active = true;
    tutorial.startupDeadline = Date.now() + 15000;
    tutorial.pendingRestores.set("Arm", Date.now() + 15000);
    tutorial.resolveWebviewView({
        webview: { onDidReceiveMessage() { return {}; }, postMessage(message) { messages.push(message); } },
        onDidChangeVisibility() { return {}; }, onDidDispose() {},
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(tutorial.pendingRestores.has("Arm"), false);
    assert.equal(probes, 4);
    running = false;
    await tick();
    for (const state of Object.values(messages.at(-1).devices)) assert.equal(state, false);
    running = null;
    await tick();
    for (const state of Object.values(messages.at(-1).devices)) assert.equal(state, null);
    tutorial.stop();
    await tick();
    for (const state of Object.values(messages.at(-1).devices)) assert.equal(state, true);
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
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "tutorial-view.js"), "utf8"), sandbox);
    const tutorial = new sandbox.module.exports.TutorialView({ subscriptions: [] });
    tutorial.root = "/workspace";
    tutorial.active = true;
    const restore = tutorial.handleMessage({ action: "restore", name: "Arm" });
    await tutorial.handleMessage({ action: "restore", name: "Arm" });
    assert.equal(probes.length, 1);
    probes[0]({ code: "ECONNREFUSED" });
    await restore;
    assert.equal(spawned, 1);
    callbacks.error(new Error("spawn failed"));
    assert.equal(tutorial.restorePending("Arm"), false);
    assert.equal(tutorial.ownedChildren.size, 0);
    const retry = tutorial.handleMessage({ action: "restore", name: "Arm" });
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
            if (name === "./tutorial-view") return tutorialModule(vscode);
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
                            ArmController: "top-left", Arm: "top-right",
                            Orchestrator: "bottom-left", PatientMonitor: "bottom-right",
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
            if (name === "./tutorial-view") return tutorialModule(vscode);
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
        panels[1].viewColumn = vscode.ViewColumn.Three;
        panels[1].onChangeViewState?.();
        panels[1].dispose();
        await open("Arm", 8092);
        assert.equal(layoutCommands.length, 1);
        assert.equal(panels.length, 5);
        const currentPanels = [panels[0], panels[4], panels[2], panels[3]];
        assert.deepEqual(currentPanels.map((panel) => panel.viewColumn), [1, 2, 3, 4]);
        assert.deepEqual(currentPanels.map((panel) => panel.slot),
            ["top-left", "top-right", "bottom-left", "bottom-right"]);
        panels[4].dispose();
        await open("Arm", 8092);
        assert.equal(layoutCommands.length, 1);
        assert.equal(panels.length, 6);
        assert.deepEqual([panels[0], panels[5], panels[2], panels[3]].map((panel) => panel.viewColumn), [1, 2, 3, 4]);
        assert.equal(panels[5].slot, "top-right");
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
            if (name === "./tutorial-view") return tutorialModule(vscode);
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
            if (name === "./tutorial-view") return tutorialModule(vscode);
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
        assert.equal(panels.get("Orchestrator").column, vscode.ViewColumn.Three);
        assert.equal(fs.readFileSync(path.join(stateDir, "Orchestrator"), "utf8"), String(process.pid));
        assert.equal(fs.existsSync(path.join(stateDir, `${"b".repeat(32)}.close`)), false);
        panels.get("Orchestrator").dispose();
        await new Promise((resolve) => setImmediate(resolve));
        assert.equal(fs.existsSync(path.join(stateDir, `${"b".repeat(32)}.close`)), true);
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});