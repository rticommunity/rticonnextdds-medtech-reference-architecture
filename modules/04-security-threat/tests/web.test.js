const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function browser() {
    const elements = new Map();
    const requests = [];
    const drawing = new Proxy({}, { get: () => () => {} });
    const createElement = () => ({
        textContent: "", children: [], hidden: false, value: "", dataset: {},
        classList: { toggle() {} },
        addEventListener(name, callback) { this[name] = callback; },
        append(child) { this.children.push(child); },
        getContext: () => drawing,
        width: 600, height: 500,
    });
    const element = id => {
        if (!elements.has(id)) elements.set(id, createElement());
        return elements.get(id);
    };
    const sandbox = {
        document: { getElementById: element, createElement, activeElement: null },
        setTimeout() {},
        fetch: async (url, options) => {
            requests.push({ url, options });
            return { ok: true, json: async () => ({ ...state }) };
        },
    };
    const state = {
        kind: "Threat Injector", status: "IDLE", mode: null, logs: [],
        modes: ["UNSECURE", "ROGUE CA", "FORGED PERMS", "EXPIRED CERT"],
        attacks: ["MOTOR INJECT", "CMD INJECT (PAUSE)", "CMD INJECT (SHUTDOWN)"],
        attack: "MOTOR INJECT", frequency: 5, attacking: false,
        angles: { BASE: 204, SHOULDER: 176, ELBOW: 156, WRIST: 165, HAND: 151 },
    };
    vm.runInNewContext(
        fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8"), sandbox,
    );
    return { sandbox, element, requests, state };
}

test("mode, frequency and launch controls send relative JSON requests", async () => {
    const { sandbox, element, requests, state } = browser();
    sandbox.render(state);
    await element("modes").children[0].click();
    await element("frequency").change({ target: { value: "12" } });
    await element("launch").click();
    await element("stop").click();
    const commands = requests.filter(request => request.options?.method === "POST");
    assert.ok(commands.every(request => request.url === "api/command"));
    assert.deepEqual(commands.map(request => JSON.parse(request.options.body)), [
        { action: "mode", mode: "UNSECURE" }, { action: "frequency", frequency: 12 },
        { action: "launch" }, { action: "stop" },
    ]);
});

test("running injection locks mode-dependent controls and displays failures", async () => {
    const { sandbox, element, state } = browser();
    sandbox.render({ ...state, mode: "UNSECURE", attacking: true });
    assert.equal(element("frequency").disabled, true);
    assert.equal(element("attack").disabled, true);
    assert.equal(element("launch").textContent, "Stop injection");
    sandbox.fetch = async () => ({
        ok: false, json: async () => ({ error: "Participant creation blocked" }),
    });
    await sandbox.command({ action: "mode", mode: "EXPIRED CERT" });
    assert.equal(element("error").hidden, false);
    assert.equal(element("error").textContent, "Participant creation blocked");
});

test("exfiltrator displays received values and clears them after data loss", () => {
    const { sandbox, element, state } = browser();
    const exfiltrator = {
        ...state, kind: "Threat Exfiltrator", sample: 1,
        vitals: { hr: 75, spo2: 98, etco2: 38, nibp_s: 120, nibp_d: 80, patient_id: "7" },
    };
    sandbox.render(exfiltrator);
    assert.equal(element("injector-controls").hidden, true);
    assert.equal(element("vitals").hidden, false);
    assert.equal(element("hr").textContent, "75");
    assert.equal(element("nibp").textContent, "120/80");
    sandbox.render({ ...exfiltrator, vitals: null });
    assert.equal(element("hr").textContent, "---");
    assert.equal(element("nibp").textContent, "---");
});
