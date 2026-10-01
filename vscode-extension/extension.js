const vscode = require("vscode");
const fs = require("fs");
const os = require("os");
const path = require("path");

const LOCALHOST_NAMES = new Set(["localhost", "127.0.0.1", "::1"]);
const APP_VIEW_COLUMNS = {
    ArmController: vscode.ViewColumn.One,
    Arm: vscode.ViewColumn.Two,
    Orchestrator: vscode.ViewColumn.Three,
    PatientMonitor: vscode.ViewColumn.Four,
};

let demoGridCreated = false;
let demoGridCreation;
const demoPanels = new Set();
const appPanels = new Map();
const appColumns = new Map();
const tabStateDir = path.join(os.tmpdir(), `medtech-web-tabs-${process.getuid()}`);
const cloudWorkspace = fs.existsSync("/app/code-server");

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

async function createDemoGrid() {
    if (demoGridCreated) {
        return;
    }

    if (!demoGridCreation) {
        demoGridCreation = vscode.commands.executeCommand("workbench.action.editorLayoutTwoByTwoGrid")
            .then(() => { demoGridCreated = true; })
            .finally(() => { demoGridCreation = undefined; });
    }
    await demoGridCreation;
}

function createAppPanel(title, targetUrl, closeToken) {
    const panel = vscode.window.createWebviewPanel(
        "rti.medtechWebTab",
        title,
        appColumns.get(title) || APP_VIEW_COLUMNS[title] || vscode.ViewColumn.Beside,
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
    return panel;
}

function activate(context) {
    let tutorialView;
    if (cloudWorkspace) {
        const { TutorialView } = require("./tutorial-view");
        tutorialView = new TutorialView(context);
        context.subscriptions.push(vscode.window.registerWebviewViewProvider("rti.medtechTutorial", tutorialView, {
            webviewOptions: { retainContextWhenHidden: true },
        }));
        context.subscriptions.push({ dispose: () => tutorialView.stop() });
    }
    const uriHandler = {
        async handleUri(uri) {
            if (uri.path === "/tutorial" && tutorialView) {
                tutorialView.secure = new URLSearchParams(uri.query).get("secure") === "1";
                tutorialView.active = true;
                tutorialView.startupDeadline = Date.now() + 15000;
                await vscode.commands.executeCommand("rti.medtechTutorial.focus");
                return;
            }
            if (uri.path === "/close") {
                const title = new URLSearchParams(uri.query).get("title");
                if (title) {
                    const panel = appPanels.get(title);
                    if (panel) {
                        panel.closedByLauncher = true;
                        panel.dispose();
                    }
                } else {
                    tutorialView?.stop();
                    for (const panel of demoPanels) {
                        panel.closedByLauncher = true;
                        panel.dispose();
                    }
                    demoPanels.clear();
                    appColumns.clear();
                }
                if (!demoPanels.size) {
                    demoGridCreated = false;
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
            if (cloudWorkspace) {
                targetUrl = cloudTargetUrl(targetUrl);
            }
            if (APP_VIEW_COLUMNS[title]) {
                await createDemoGrid();
            }
            const existingPanel = appPanels.get(title);
            if (existingPanel) {
                if (closeToken) existingPanel.closeToken = closeToken;
                existingPanel.reveal();
                existingPanel.webview.html = webviewHtml(targetUrl, title);
                return;
            }
            if (APP_VIEW_COLUMNS[title] && appColumns.has(title)) {
                const tabs = new Map([...appPanels].map(([name, panel]) => [name, {
                    url: panel.targetUrl, token: panel.closeToken,
                }]));
                tabs.set(title, { url: targetUrl, token: closeToken });
                const disposing = [...appPanels.values()];
                for (const panel of disposing) {
                    panel.closedByLauncher = true;
                    panel.dispose();
                }
                await Promise.all(disposing.map((panel) => panel.disposed));
                appPanels.clear();
                await vscode.commands.executeCommand("workbench.action.editorLayoutTwoByTwoGrid");
                for (const name of Object.keys(APP_VIEW_COLUMNS)) {
                    const tab = tabs.get(name);
                    if (tab) {
                        createAppPanel(name, tab.url, tab.token);
                    }
                }
                await vscode.commands.executeCommand("vscode.setEditorLayout", {
                    orientation: 0,
                    groups: [
                        { groups: [{}, {}] },
                        { groups: [{}, {}] },
                    ],
                });
                for (const [name, column] of Object.entries(APP_VIEW_COLUMNS).reverse()) {
                    const panel = appPanels.get(name);
                    if (panel && panel.viewColumn !== column) {
                        panel.reveal(column);
                    }
                }
                await vscode.commands.executeCommand("workbench.action.evenEditorWidths");
            } else {
                createAppPanel(title, targetUrl, closeToken);
            }
        }
    };
    context.subscriptions.push(vscode.window.registerUriHandler(uriHandler));
    if (cloudWorkspace) {
        const requests = path.join(tabStateDir, "requests");
        fs.mkdirSync(requests, { recursive: true });
        const owner = path.join(tabStateDir, "owner");
        const claim = () => fs.writeFileSync(owner, String(process.pid));
        tutorialView.claim = claim;
        claim();
        context.subscriptions.push(vscode.window.onDidChangeWindowState(state => {
            if (state.focused) claim();
        }));
        let busy = false;
        const timer = setInterval(async () => {
            if (busy || fs.readFileSync(owner, "utf8") !== String(process.pid)) return;
            busy = true;
            try {
                for (const name of fs.readdirSync(requests).filter(name => name.endsWith(".json")).sort()) {
                    const file = path.join(requests, name);
                    const request = JSON.parse(fs.readFileSync(file, "utf8"));
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
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${targetUrl.origin}; style-src 'unsafe-inline';">
<title>${escapeHtml(title)}</title>
<style>html, body, iframe { border: 0; height: 100%; margin: 0; padding: 0; width: 100%; }</style>
</head>
<body><iframe src="${safeUrl}" title="${escapeHtml(title)}"></iframe></body>
</html>`;
}

function deactivate() {
    for (const title of appPanels.keys()) {
        fs.rmSync(tabStatePath(title), { force: true });
    }
}

module.exports = { activate, deactivate, cloudTargetUrl };