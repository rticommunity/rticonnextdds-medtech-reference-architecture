const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const os = require("os");
const http = require("http");
const { spawn } = require("child_process");

const PORTS = { ArmController: 8091, Orchestrator: 8090, Arm: 8092, PatientMonitor: 8093 };
const DEVICE_NAMES = { ARM: "Arm", ARM_CONTROLLER: "ArmController", PATIENT_MONITOR: "PatientMonitor", PATIENT_SENSOR: "PatientSensor" };

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

class DeviceLauncher {
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

    startMonitoring() {
        let updating = false;
        const timer = setInterval(async () => {
            if (updating) return;
            updating = true;
            try {
                await this.refreshHealth();
            } finally {
                updating = false;
            }
        }, 250);
        this.context.subscriptions.push({ dispose: () => clearInterval(timer) });
    }

    async refreshHealth() {
        const states = await Promise.all(Object.entries(PORTS).map(async ([name, port]) => {
            if (!this.active) return [name, true];
            const running = await deviceRunning(port);
            if (running === true) {
                this.seenDevices.add(name);
                if (!this.checkingDevices.has(name)) this.pendingRestores.delete(name);
            }
            return [name, this.restorePending(name) ? true : running];
        }));
        return Object.fromEntries(states);
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

module.exports = { DeviceLauncher, deviceRunning, sensorRunning, DEVICE_NAMES };