const vscode = require("vscode");
const fs = require("fs");
const os = require("os");
const path = require("path");

const LOCALHOST_NAMES = new Set(["localhost", "127.0.0.1", "::1"]);
const APP_VIEW_COLUMNS = {
    ArmController: vscode.ViewColumn.One,
    Arm: vscode.ViewColumn.Three,
    Orchestrator: vscode.ViewColumn.Two,
    PatientMonitor: vscode.ViewColumn.Four,
};
const DEMO_GRID_LAYOUT = {
    orientation: 1,
    groups: [{ groups: [{}, {}] }, { groups: [{}, {}] }],
};

let demoGridCreated = false;
let demoGridCreation;
let gridConfiguration;
let previousCloseEmptyGroups;
const demoPanels = new Set();
const appPanels = new Map();
const appColumns = new Map();
const tabStateDir = path.join(os.tmpdir(), `medtech-web-tabs-${process.getuid()}`);
const cloudWorkspace = fs.existsSync("/app/code-server");
let recoveryView;
let extensionContext;

function recovery() {
    if (!recoveryView) {
        const { DeviceLauncher } = require("./device-launcher");
        recoveryView = new DeviceLauncher(extensionContext);
    }
    return recoveryView;
}

function cloudTargetUrl(targetUrl, origin = process.env.MEDTECH_CLOUD_URL || "http://127.0.0.1:8080") {
    return new URL(`${origin.replace(/\/$/, "")}/proxy/${targetUrl.port}${targetUrl.pathname}${targetUrl.search}`);
}

function tabStatePath(title) {
    return path.join(tabStateDir, title);
}

function escapeHtml(value) {
    return value.replace(/[&<>"]/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
    })[character]);
}

function isLocalHttpUrl(url) {
    return (url.protocol === "http:" || url.protocol === "https:")
        && LOCALHOST_NAMES.has(url.hostname);
}

async function preserveDemoGroups() {
    const configuration = vscode.workspace?.getConfiguration?.("workbench.editor");
    if (!configuration || gridConfiguration) return;
    previousCloseEmptyGroups = configuration.inspect("closeEmptyGroups")?.workspaceValue;
    await configuration.update("closeEmptyGroups", false, vscode.ConfigurationTarget.Workspace);
    gridConfiguration = configuration;
}

async function restoreDemoGroups() {
    if (!gridConfiguration) return;
    const configuration = gridConfiguration;
    gridConfiguration = undefined;
    if (configuration.inspect("closeEmptyGroups")?.workspaceValue === false) {
        await configuration.update("closeEmptyGroups", previousCloseEmptyGroups, vscode.ConfigurationTarget.Workspace);
    }
}

async function createDemoGrid() {
    if (demoGridCreated) {
        return;
    }

    if (!demoGridCreation) {
        demoGridCreation = preserveDemoGroups()
            .then(() => vscode.commands.executeCommand("vscode.setEditorLayout", DEMO_GRID_LAYOUT))
            .then(() => { demoGridCreated = true; })
            .finally(() => { demoGridCreation = undefined; });
    }
    await demoGridCreation;
}

function createAppPanel(title, targetUrl, closeToken, preserveFocus = false) {
    const column = appColumns.get(title) || APP_VIEW_COLUMNS[title] || vscode.ViewColumn.Beside;
    const panel = vscode.window.createWebviewPanel(
        "rti.medtechWebTab",
        title,
        preserveFocus ? { viewColumn: column, preserveFocus: true } : column,
        { enableScripts: true, retainContextWhenHidden: true }
    );
    panel.closeToken = closeToken;
    panel.targetUrl = targetUrl;
    demoPanels.add(panel);
    if (APP_VIEW_COLUMNS[title]) {
        appColumns.set(title, APP_VIEW_COLUMNS[title]);
        appPanels.set(title, panel);
        fs.mkdirSync(tabStateDir, { recursive: true });
        fs.writeFileSync(tabStatePath(title), String(process.pid));
    }
    panel.disposed = new Promise((resolve) => {
        panel.onDidDispose(() => {
            demoPanels.delete(panel);
            if (appPanels.get(title) === panel) {
                appPanels.delete(title);
                fs.writeFileSync(tabStatePath(title), String(-process.pid));
                if (panel.closeToken && !panel.closedByLauncher) {
                    fs.writeFileSync(path.join(tabStateDir, `${panel.closeToken}.close`), "");
                }
            }
            resolve();
        });
    });
    panel.webview.html = webviewHtml(targetUrl, title);
    if (title === "Orchestrator") {
        panel.webview.onDidReceiveMessage?.(async message => {
            const { DEVICE_NAMES } = require("./device-launcher");
            if (message.action !== "start" || !Object.hasOwn(DEVICE_NAMES, message.device)
                    || !Number.isSafeInteger(message.requestId)) return;
            try {
                const name = DEVICE_NAMES[message.device];
                const status = await recovery().restoreDevice(name, !appPanels.has(name) || message.stopped === true);
                await panel.webview.postMessage({ type: "medtech-device-start-result", requestId: message.requestId, status });
            } catch (error) {
                await panel.webview.postMessage({ type: "medtech-device-start-result", requestId: message.requestId, status: "error" });
                vscode.window.showErrorMessage(`Unable to start device: ${error.message}`);
            }
        });
    }
    return panel;
}

function activate(context) {
    extensionContext = context;
    recovery().startMonitoring();
    context.subscriptions.push({ dispose: () => recoveryView?.stop() });
    const uriHandler = {
        async handleUri(uri) {
            if (uri.path === "/session") {
                const controller = recovery();
                controller.secure = new URLSearchParams(uri.query).get("secure") === "1";
                controller.active = true;
                controller.startupDeadline = Date.now() + 15000;
                return;
            }
            if (uri.path === "/close" || uri.path === "/close-owned") {
                const parameters = new URLSearchParams(uri.query);
                const token = parameters.get("closeToken");
                if (uri.path === "/close-owned" && token === null) return;
                let title = parameters.get("title");
                if (token !== null) {
                    if (!/^[a-f0-9]{32}$/.test(token)) return;
                    const owned = [...appPanels].find(([, panel]) => panel.closeToken === token);
                    if (!owned) return;
                    title = owned[0];
                }
                if (title) {
                    const panel = appPanels.get(title);
                    if (panel) {
                        panel.closedByLauncher = true;
                        panel.dispose();
                    }
                } else {
                    recovery().stop();
                    for (const panel of demoPanels) {
                        panel.closedByLauncher = true;
                        panel.dispose();
                    }
                    demoPanels.clear();
                    appColumns.clear();
                }
                if (!demoPanels.size) {
                    demoGridCreated = false;
                    await restoreDemoGroups();
                }
                return;
            }

            if (uri.path !== "/open") {
                return;
            }

            const parameters = new URLSearchParams(uri.query);
            const requestedUrl = parameters.get("url");
            const requestedTitle = parameters.get("title");
            const requestedToken = parameters.get("closeToken");
            const closeToken = /^[a-f0-9]{32}$/.test(requestedToken || "") ? requestedToken : null;
            let targetUrl;

            try {
                targetUrl = new URL(requestedUrl);
            } catch {
                vscode.window.showErrorMessage("MedTech Web Tabs received an invalid URL.");
                return;
            }

            if (!isLocalHttpUrl(targetUrl)) {
                vscode.window.showErrorMessage(
                    "MedTech Web Tabs only opens HTTP URLs served from localhost."
                );
                return;
            }

            const title = requestedTitle || targetUrl.host;
            if (APP_VIEW_COLUMNS[title]) {
                const controller = recovery();
                if (title === "Orchestrator") controller.active = true;
                controller.seenDevices.add(title);
                controller.pendingRestores.delete(title);
            }
            if (cloudWorkspace) {
                targetUrl = cloudTargetUrl(targetUrl);
            }
            if (APP_VIEW_COLUMNS[title]) {
                await createDemoGrid();
            }
            const existingPanel = appPanels.get(title);
            if (existingPanel) {
                const restarted = closeToken && closeToken !== existingPanel.closeToken;
                if (closeToken) existingPanel.closeToken = closeToken;
                existingPanel.reveal(undefined, true);
                if (restarted || existingPanel.targetUrl.href !== targetUrl.href) {
                    existingPanel.targetUrl = targetUrl;
                    existingPanel.webview.html = webviewHtml(targetUrl, title);
                }
                return;
            }
            if (APP_VIEW_COLUMNS[title] && appColumns.has(title)) {
                if (!appPanels.has(title)) createAppPanel(title, targetUrl, closeToken, true);
            } else {
                createAppPanel(title, targetUrl, closeToken);
            }
        }
    };
    context.subscriptions.push(vscode.window.registerUriHandler(uriHandler));
    if (vscode.commands.registerCommand) {
        context.subscriptions.push(vscode.commands.registerCommand("rti.medtech.openOrchestrator", async () => {
            const controller = recovery();
            const status = await controller.restoreDevice("Orchestrator", !appPanels.has("Orchestrator"));
            if (status === "running") {
                await uriHandler.handleUri({ path: "/open", query: "title=Orchestrator&url=http%3A%2F%2Flocalhost%3A8090%2F" });
            } else if (status !== "starting") {
                vscode.window.showErrorMessage("Unable to open Orchestrator. Launch the Digital Operating Room demo first.");
            }
        }));
    }
    if (cloudWorkspace) {
        const requests = path.join(tabStateDir, "requests");
        fs.mkdirSync(requests, { recursive: true });
        const owner = path.join(tabStateDir, "owner");
        const claim = () => fs.writeFileSync(owner, String(process.pid));
        recovery().claim = claim;
        claim();
        context.subscriptions.push(vscode.window.onDidChangeWindowState(state => {
            if (state.focused) claim();
        }));
        let busy = false;
        const timer = setInterval(async () => {
            if (busy) return;
            busy = true;
            try {
                for (const name of fs.readdirSync(requests).filter(name => name.endsWith(".json")).sort()) {
                    const file = path.join(requests, name);
                    const request = JSON.parse(fs.readFileSync(file, "utf8"));
                    if (request.targetHost !== undefined) {
                        if (request.targetHost !== String(process.pid)) continue;
                    } else if (fs.readFileSync(owner, "utf8") !== String(process.pid)) {
                        continue;
                    }
                    fs.unlinkSync(file);
                    const uri = new URL(request.uri);
                    if (uri.protocol !== "vscode:" || uri.hostname !== "rti.medtech-web-tabs") continue;
                    await uriHandler.handleUri({ path: uri.pathname, query: uri.search.slice(1) });
                }
            } catch (error) {
                vscode.window.showErrorMessage(`MedTech launcher: ${error.message}`);
            } finally {
                busy = false;
            }
        }, 200);
        context.subscriptions.push({ dispose: () => clearInterval(timer) });
    }
}

function webviewHtml(targetUrl, title) {
    const safeUrl = escapeHtml(targetUrl.toString());
    const bridge = title === "Orchestrator" ? `<script nonce="medtech-orchestrator">
const api = acquireVsCodeApi();
const frame = document.querySelector('iframe');
const origin = ${JSON.stringify(targetUrl.origin)};
frame.addEventListener('load', () => frame.contentWindow.postMessage({type: 'medtech-launcher-ready'}, origin));
window.addEventListener('message', event => {
    if (event.source === frame.contentWindow && event.origin === origin && event.data?.type === 'medtech-device-start') {
        api.postMessage({action: 'start', device: event.data.device, requestId: event.data.requestId, stopped: event.data.stopped === true});
    } else if (event.source !== frame.contentWindow && event.data?.type === 'medtech-device-start-result') {
        frame.contentWindow.postMessage(event.data, origin);
    }
});
</script>` : "";
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${targetUrl.origin}; style-src 'unsafe-inline'; script-src 'nonce-medtech-orchestrator';">
<title>${escapeHtml(title)}</title>
<style>html, body, iframe { border: 0; height: 100%; margin: 0; padding: 0; width: 100%; }</style>
</head>
<body><iframe src="${safeUrl}" title="${escapeHtml(title)}"></iframe>${bridge}</body>
</html>`;
}

async function deactivate() {
    await restoreDemoGroups();
    for (const title of appPanels.keys()) {
        fs.rmSync(tabStatePath(title), { force: true });
    }
}

module.exports = { activate, deactivate, cloudTargetUrl, webviewHtml };