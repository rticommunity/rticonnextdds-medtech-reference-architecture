const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const os = require("os");
const http = require("http");
const { spawn } = require("child_process");

const PORTS = { ArmController: 8091, Orchestrator: 8090, Arm: 8092, PatientMonitor: 8093 };
const DEVICE_NAMES = { ARM: "Arm", ARM_CONTROLLER: "ArmController", PATIENT_MONITOR: "PatientMonitor", PATIENT_SENSOR: "PatientSensor" };

function escape(value) {
    return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
}

function tutorialHtml(tutorial) {
    const paragraph = value => value ? `<p>${escape(value)}</p>` : "";
    const list = values => values?.length ? `<ul>${values.map(value => `<li>${escape(value)}</li>`).join("")}</ul>` : "";
    const steps = tutorial.steps.map((step, index) => {
        const files = (step.openFiles || []).map((file, fileIndex) =>
            `<button data-action="file" data-step="${index}" data-index="${fileIndex}">Open ${escape(path.basename(file))}</button>`).join("");
        const terminals = (step.terminals || []).map((terminal, terminalIndex) =>
            `<pre>${escape((terminal.commands || []).join("\n"))}</pre><button data-action="terminal" data-step="${index}" data-index="${terminalIndex}">Run ${escape(terminal.name || "Commands")}</button>`).join("");
        return `<details ${index === 0 ? "open" : ""}><summary>${step.number}. ${escape(step.title)}</summary>
${(step.body || []).map(paragraph).join("")}${files}${terminals}
${step.background ? "<h3>Background</h3>" + list(step.background) : ""}
${step.whatWellBuild ? "<h3>What We'll Build</h3>" + paragraph(step.whatWellBuild.description) + list(step.whatWellBuild.items) : ""}
${list(step.highlights)}${paragraph(step.highlight)}${paragraph(step.note)}${paragraph(step.expectedResult)}
${step.tryThis ? "<h3>Try This</h3>" + list(step.tryThis) : ""}${list(step.actions)}
${paragraph(step.cloudEvalNote)}${paragraph(step.keyTakeaway)}
${list((step.links || []).map(link => `${link.label}: ${link.description}`))}${paragraph(step.callToAction)}</details>`;
    }).join("");
    return `<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-medtech-tutorial';">
<style>
body { padding: 10px 14px; color: var(--vscode-foreground); background: var(--vscode-sideBar-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); }
h2 { font-size: 16px; margin: 4px 0 12px; } h3 { font-size: 13px; margin: 14px 0 6px; }
p, li { line-height: 1.5; overflow-wrap: anywhere; } ul { padding-left: 20px; }
details { border-bottom: 1px solid var(--vscode-panel-border); padding: 12px 0; }
summary { font-weight: 600; line-height: 1.4; cursor: pointer; }
button { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: 0; border-radius: 2px; padding: 7px 8px; margin: 3px 0; cursor: pointer; font: inherit; max-width: 100%; overflow-wrap: anywhere; }
button:hover { background: var(--vscode-button-hoverBackground); } button:disabled { opacity: .45; cursor: default; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
nav { display: flex; justify-content: space-between; margin-top: 12px; }
</style></head><body><h2>${escape(tutorial.title)}</h2>
${steps}<nav><button id="previous">Previous</button><button id="next">Next</button></nav>
<script nonce="medtech-tutorial">
const api = acquireVsCodeApi();
const steps = [...document.querySelectorAll('details')];
let current = api.getState()?.step || 0;
function select(index) {
    current = Math.max(0, Math.min(steps.length - 1, index));
    steps.forEach((step, position) => { step.open = position === current; });
    api.setState({step: current});
    document.getElementById('previous').disabled = current === 0;
    document.getElementById('next').disabled = current === steps.length - 1;
}
steps.forEach((step, index) => step.querySelector('summary').addEventListener('click', event => { event.preventDefault(); select(index); }));
document.getElementById('previous').onclick = () => select(current - 1);
document.getElementById('next').onclick = () => select(current + 1);
document.querySelectorAll('[data-action]').forEach(button => button.onclick = () => {
    api.postMessage({action: button.dataset.action, step: Number(button.dataset.step), index: Number(button.dataset.index), name: button.dataset.name});
});
select(current);
</script></body></html>`;
}

function deviceRunning(port) {
    return new Promise(resolve => {
        const request = http.get(`http://127.0.0.1:${port}/api/state`, response => {
            response.resume();
            resolve(true);
        });
        request.setTimeout(500, () => request.destroy());
        request.on("error", error => resolve(error.code === "ECONNREFUSED" ? false : null));
    });
}

function sensorRunning() {
    try {
        const record = JSON.parse(fs.readFileSync(path.join(os.tmpdir(), `medtech-web-tabs-${process.getuid()}`, "PatientSensor.process"), "utf8"));
        if (record.pid === null) return false;
        if (!Number.isSafeInteger(record.pid) || record.pid <= 0) return null;
        process.kill(record.pid, 0);
        return true;
    } catch (error) {
        return error.code === "ESRCH" ? false : null;
    }
}

class TutorialView {
    constructor(context) {
        this.context = context;
        this.children = new Map();
        this.secure = false;
        this.active = false;
        this.startupDeadline = 0;
        this.seenDevices = new Set();
        this.pendingRestores = new Map();
        this.checkingDevices = new Set();
        this.ownedChildren = new Set();
    }

    resolveWebviewView(view) {
        this.claim?.();
        this.context.subscriptions.push(view.onDidChangeVisibility(() => {
            if (view.visible) this.claim?.();
        }));
        const candidates = (vscode.workspace.workspaceFolders || []).flatMap(folder => [
            folder.uri.fsPath, path.dirname(folder.uri.fsPath),
        ]);
        this.root = candidates.find(root => fs.existsSync(path.join(root, "tutorial", "digital-or-tutorial.json")));
        if (!this.root) {
            view.webview.html = "<p>No Digital Operating Room tutorial in this workspace.</p>";
            return;
        }
        this.tutorial = JSON.parse(fs.readFileSync(path.join(this.root, "tutorial", "digital-or-tutorial.json"), "utf8"));
        view.webview.options = { enableScripts: true };
        view.webview.html = tutorialHtml(this.tutorial);
        this.context.subscriptions.push(view.webview.onDidReceiveMessage(message => this.handleMessage(message)));
        let updating = false;
        const update = async () => {
            if (updating) return;
            updating = true;
            try {
                const states = await Promise.all(Object.entries(PORTS).map(async ([name, port]) => {
                    if (!this.active) return [name, true];
                    const running = await deviceRunning(port);
                    if (running === true) {
                        this.seenDevices.add(name);
                        if (!this.checkingDevices.has(name)) this.pendingRestores.delete(name);
                    }
                    return [name, this.restorePending(name) ? true : running];
                }));
                await view.webview.postMessage({ type: "health", devices: Object.fromEntries(states) });
            } finally {
                updating = false;
            }
        };
        const timer = setInterval(() => update().catch(() => {}), 250);
        view.onDidDispose(() => clearInterval(timer));
        this.context.subscriptions.push({ dispose: () => clearInterval(timer) });
        update().catch(() => {});
    }

    restorePending(name) {
        return Date.now() < (this.pendingRestores.get(name) || 0)
            || (!this.seenDevices.has(name) && Date.now() < this.startupDeadline);
    }

    async restoreDevice(name, waitForExit = false) {
        if (!Object.hasOwn(PORTS, name) && name !== "PatientSensor") return "unknown";
        if (!this.active) return "inactive";
        if (this.checkingDevices.has(name)) return "starting";
        if (Date.now() < (this.pendingRestores.get(name) || 0)) {
            if (name !== "PatientSensor" || sensorRunning() !== true) return "starting";
            this.pendingRestores.delete(name);
        }
        if (!this.root) {
            const candidates = (vscode.workspace?.workspaceFolders || []).flatMap(folder => [folder.uri.fsPath, path.dirname(folder.uri.fsPath)]);
            this.root = candidates.find(root => fs.existsSync(path.join(root, "tutorial", "run_digital_or.sh")));
        }
        if (!this.root) return "inactive";
        this.claim?.();
        this.pendingRestores.set(name, Date.now() + 15000);
        this.checkingDevices.add(name);
        let running;
        try {
            running = name === "PatientSensor" ? sensorRunning() : await deviceRunning(PORTS[name]);
            if (waitForExit && running !== false) {
                const deadline = Date.now() + 2000;
                do {
                    await new Promise(resolve => setTimeout(resolve, 50));
                    running = name === "PatientSensor" ? sensorRunning() : await deviceRunning(PORTS[name]);
                } while (running !== false && this.active && Date.now() < deadline);
            }
        } catch (error) {
            this.pendingRestores.delete(name);
            throw error;
        } finally {
            this.checkingDevices.delete(name);
        }
        if (running !== false || !this.active) {
            this.pendingRestores.delete(name);
            if (running === true) this.seenDevices.add(name);
            return !this.active ? "inactive" : running === true ? "running" : "unknown";
        }
        if (name !== "PatientSensor" && !this.seenDevices.has(name) && Date.now() < this.startupDeadline) {
            this.pendingRestores.delete(name);
            return "starting";
        }
        const args = [path.join(this.root, "tutorial", "run_digital_or.sh"), "--launch-only", name, "--vscode"];
        if (this.secure) args.push("--secure");
        let child;
        try {
            child = spawn("bash", args, {
                cwd: this.root, env: { ...process.env, MEDTECH_CLOUD: fs.existsSync("/app/code-server") ? "1" : "0" },
                stdio: "ignore", detached: true,
            });
        } catch (error) {
            this.pendingRestores.delete(name);
            throw error;
        }
        this.children.set(name, child);
        this.ownedChildren.add(child);
        child.on("exit", () => {
            this.ownedChildren.delete(child);
            if (this.children.get(name) === child) {
                this.children.delete(name);
                this.pendingRestores.delete(name);
            }
        });
        child.on("error", error => {
            this.ownedChildren.delete(child);
            if (this.children.get(name) === child) {
                this.children.delete(name);
                this.pendingRestores.delete(name);
            }
            vscode.window.showErrorMessage(`Unable to start ${name}: ${error.message}`);
        });
        return "starting";
    }

    async handleMessage(message) {
        if (message.action === "restore") return this.restoreDevice(message.name);
        const step = this.tutorial.steps[message.step];
        if (!step) return;
        if (message.action === "file") {
            const file = step.openFiles?.[message.index];
            if (!file) return;
            const repo = path.join(this.root, "medtech-reference-architecture");
            const target = path.resolve(repo, file);
            if (!target.startsWith(repo + path.sep)) return;
            await vscode.window.showTextDocument(vscode.Uri.file(target), { preview: true });
        } else if (message.action === "terminal") {
            const spec = step.terminals?.[message.index];
            if (!spec) return;
            const terminal = vscode.window.createTerminal({ name: spec.name, cwd: path.join(this.root, "medtech-reference-architecture") });
            terminal.show();
            terminal.sendText(spec.commands.join(" && "));
        }
    }

    stop() {
        this.active = false;
        this.seenDevices.clear();
        this.pendingRestores.clear();
        for (const child of this.ownedChildren) {
            if (child.exitCode === null) {
                try {
                    process.kill(-child.pid, "SIGTERM");
                } catch (error) {
                    if (error.code !== "ESRCH") throw error;
                }
            }
        }
    }
}

module.exports = { TutorialView, tutorialHtml, deviceRunning, sensorRunning, DEVICE_NAMES };