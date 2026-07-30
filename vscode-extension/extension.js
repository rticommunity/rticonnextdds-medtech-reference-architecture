const vscode = require("vscode");

const LOCALHOST_NAMES = new Set(["localhost", "127.0.0.1", "::1"]);
const APP_VIEW_COLUMNS = {
    ArmController: vscode.ViewColumn.One,
    Arm: vscode.ViewColumn.Two,
    Orchestrator: vscode.ViewColumn.Three,
    PatientMonitor: vscode.ViewColumn.Four,
};

let demoGridCreated = false;
const demoPanels = new Set();

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

    await vscode.commands.executeCommand("workbench.action.editorLayoutTwoByTwoGrid");
    demoGridCreated = true;
}

function activate(context) {
    context.subscriptions.push(vscode.window.registerUriHandler({
        async handleUri(uri) {
            if (uri.path === "/close") {
                for (const panel of demoPanels) {
                    panel.dispose();
                }
                demoPanels.clear();
                demoGridCreated = false;
                return;
            }

            if (uri.path !== "/open") {
                return;
            }

            const parameters = new URLSearchParams(uri.query);
            const requestedUrl = parameters.get("url");
            const requestedTitle = parameters.get("title");
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
                await createDemoGrid();
            }
            const panel = vscode.window.createWebviewPanel(
                "rti.medtechWebTab",
                title,
                APP_VIEW_COLUMNS[title] || vscode.ViewColumn.Beside,
                { enableScripts: true, retainContextWhenHidden: true }
            );
            demoPanels.add(panel);
            panel.onDidDispose(() => demoPanels.delete(panel));
            const safeUrl = escapeHtml(targetUrl.toString());
            panel.webview.html = `<!DOCTYPE html>
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
    }));
}

function deactivate() {}

module.exports = { activate, deactivate };