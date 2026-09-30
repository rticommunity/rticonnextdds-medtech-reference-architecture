const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

test("concurrent opens reuse one panel and disposal explicitly reports closed", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-tabs-test-"));
    const panels = [];
    let layoutCount = 0;
    let handler;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        commands: { executeCommand: async () => { layoutCount++; } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            createWebviewPanel() {
                const panel = {
                    webview: { html: "" },
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
    let emptyArmSlot = false;
    let handler;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        commands: { executeCommand: async (name) => {
            layoutCommands.push(name);
            if (layoutCommands.length > 1) {
                emptyArmSlot = true;
            }
        } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            createWebviewPanel(_type, title, viewColumn) {
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
        assert.equal(layoutCommands.length, 4);
        assert.deepEqual(panels.slice(4).map((panel) => panel.viewColumn), [1, 2, 3, 4]);
        assert.deepEqual(panels.slice(4).map((panel) => panel.slot),
            ["top-left", "top-right", "bottom-left", "bottom-right"]);
        panels[5].dispose();
        await open("Arm", 8092);
        assert.equal(layoutCommands.length, 7);
        assert.deepEqual(panels.slice(8).map((panel) => panel.viewColumn), [1, 2, 3, 4]);
        assert.equal(panels[9].slot, "top-right");
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
});

test("resetting the grid does not kill surviving apps", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-grid-close-test-"));
    const panels = new Map();
    let handler;
    let layoutCount = 0;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        commands: { executeCommand: async () => {
            if (++layoutCount === 2) {
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
        panels.get("ArmController").dispose();
        await open("ArmController", 8091, "d".repeat(32));
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

test("restoring ArmController rebuilds its group without killing survivors", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medtech-controller-test-"));
    const panels = new Map();
    let handler;
    let layoutCount = 0;
    const vscode = {
        ViewColumn: { One: 1, Two: 2, Three: 3, Four: 4, Beside: 5 },
        commands: { executeCommand: async () => {
            if (++layoutCount > 1) {
                const oldPanel = panels.get("Orchestrator");
                setImmediate(() => oldPanel.dispose());
            }
        } },
        window: {
            registerUriHandler(value) { handler = value; return {}; },
            createWebviewPanel(_type, title, column) {
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
        await handler.handleUri({ path: "/close", query: "title=ArmController" });
        await new Promise((resolve) => setImmediate(resolve));
        await open("ArmController", 8091, "c".repeat(32));
        await new Promise((resolve) => setImmediate(resolve));
        const stateDir = path.join(directory, `medtech-web-tabs-${process.getuid()}`);
        assert.equal(layoutCount, 4);
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