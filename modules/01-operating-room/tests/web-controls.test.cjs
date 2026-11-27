const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadApp(directory) {
    const requests = [];
    const timers = new Map();
    const elements = new Map();
    let nextTimer = 0;
    const element = () => ({
        textContent: "",
        attributes: {},
        children: [],
        dataset: {},
        events: {},
        classList: new Set(),
        set innerHTML(_html) { this.children.length = 0; },
        appendChild(child) { this.children.push(child); },
        insertBefore(child, reference) {
            if (this.children.includes(child)) this.removeChild(child);
            if (reference) this.children.splice(this.children.indexOf(reference), 0, child);
            else this.appendChild(child);
        },
        removeChild(child) { this.children.splice(this.children.indexOf(child), 1); },
        addEventListener(event, callback) { this.events[event] = callback; },
        setAttribute(name, value) { this.attributes[name] = value; },
        getContext() { return {}; },
        querySelectorAll(selector = ".play-toggle") {
            return this.children.flatMap(row => row.children.filter(c => selector === "button"
                ? c.tag === "button" : c.className === "play-toggle"));
        },
        querySelector(selector) { return this.querySelectorAll().find(c => selector.includes(`"${c.dataset.motorId}"`)); },
    });
    const get = id => {
        if (!elements.has(id)) elements.set(id, element());
        return elements.get(id);
    };
    const context = vm.createContext({
        console: { warn() {} },
        document: { getElementById: get, createElement: element, querySelectorAll: () => [] },
        window: element(),
        performance: { now: () => 0 },
        setTimeout: (fn, delay) => { timers.set(++nextTimer, { fn, delay }); return nextTimer; },
        clearTimeout: id => timers.delete(id),
        setInterval: (_fn, delay) => assert.equal(delay, 40, "only the monitor's local animation uses an interval"),
        fetch: (path, options) => new Promise(resolve => requests.push({
            path,
            body: options.body ? JSON.parse(options.body) : null,
            respond: (data, status = 200) => resolve({ ok: status === 200, status, json: async () => data }),
        })),
    });
    const makeElement = context.document.createElement;
    function withClassToggle(el) {
        el.classList.toggle = (name, enabled) => enabled ? el.classList.add(name) : el.classList.delete(name);
        el.classList.contains = name => el.classList.has(name);
        return el;
    }
    context.document.createElement = tag => Object.assign(withClassToggle(makeElement()), { tag });
    vm.runInContext(readFileSync(join(__dirname, "..", directory, "app.js"), "utf8"), context);
    return {
        requests, timers, get,
        run: code => vm.runInContext(code, context),
        fireTimer() {
            const [id, { fn }] = timers.entries().next().value;
            timers.delete(id);
            return fn();
        },
    };
}

const settle = () => new Promise(resolve => setImmediate(resolve));
const motorState = playing => ({ status: "ON", motors: [{ id: "BASE", playing }] });

for (const directory of ["web", "web-arm", "web-armcontroller", "web-patientmonitor"]) {
    test(`${directory}: a slow poll cannot queue another poll`, async () => {
        const app = loadApp(directory);
        assert.equal(app.requests.length, 1);
        assert.equal(app.timers.size, 0);
        app.requests[0].respond({}, 503);
        await settle();
        assert.equal([...app.timers.values()][0].delay, 100);
        app.fireTimer();
        assert.equal(app.requests.length, 2);
        assert.equal(app.timers.size, 0);
    });
}

test("Orchestrator displays a missed-heartbeat alert on the next state response", async () => {
    const app = loadApp("web");
    const device = status => ({ id: "PATIENT_MONITOR", status });
    app.requests[0].respond({ devices: [device("ON")] });
    await settle();
    const card = app.get("devices").children[0];
    const badge = card.children[1];
    assert.equal(badge.textContent, "ON");

    app.fireTimer();
    app.requests[1].respond({
        devices: [device("OFF")],
        alerts: ["PATIENT_MONITOR is no longer sending heartbeats. Updating Status to OFF."],
    });
    await settle();
    assert.equal(app.get("devices").children[0], card, "polling must not replace the target of an in-progress click");
    assert.equal(card.children[1], badge);
    assert.equal(badge.textContent, "OFF");
    assert.match(app.get("alerts").textContent, /no longer sending heartbeats/);
    card.events.click();
    assert.equal(app.get("selected-device").textContent, "Patient Monitor");
    assert.equal(app.get("btn-start").disabled, false);
});

test("AUTO keeps confirmed state and ignores a poll started before the acknowledgement", async () => {
    const app = loadApp("web-armcontroller");
    app.requests[0].respond(motorState(false));
    await settle();
    app.fireTimer();
    const base = app.get("motors").querySelectorAll()[0];
    base.events.click();
    assert.equal(base.disabled, true);
    assert.equal(base.attributes["aria-pressed"], "false");
    assert.equal(app.get("command-status").textContent, "Sending command...");
    base.events.click();
    assert.equal(app.requests.length, 3);
    assert.deepEqual(app.requests[2].body, { motor: "BASE", active: true });
    app.requests[2].respond({ ok: true });
    await settle();
    app.requests[1].respond(motorState(false));
    await settle();
    assert.equal(base.attributes["aria-pressed"], "true");
    base.events.click();
    assert.deepEqual(app.requests[3].body, { motor: "BASE", active: false });
    app.requests[3].respond({}, 503);
    await settle();
    assert.equal(base.attributes["aria-pressed"], "true");
    assert.equal(base.disabled, false);
    assert.match(app.get("command-status").textContent, /not confirmed: HTTP 503/);
});

test("Play All and Stop All update the controls only after acknowledgement", async () => {
    const app = loadApp("web-armcontroller");
    app.requests[0].respond(motorState(false));
    await settle();
    const buttons = app.get("motors").querySelectorAll();
    for (const [index, id, active] of [[1, "btn-play-all", true], [2, "btn-stop-all", false]]) {
        app.get(id).events.click();
        assert.equal(app.requests[index].path, "api/play_all");
        assert.deepEqual(app.requests[index].body, { active });
        assert.ok(buttons.every(button => button.attributes["aria-pressed"] === String(!active)));
        app.requests[index].respond({ ok: true });
        await settle();
        assert.ok(buttons.every(button => button.attributes["aria-pressed"] === String(active)));
    }
});

test("a held jog waits for its pending POST and releasing it drops repeats", async () => {
    const app = loadApp("web-armcontroller");
    app.run('startJog("BASE", "inc")');
    assert.equal(app.requests[1].path, "api/motor");
    assert.equal(app.timers.size, 0);
    app.requests[1].respond({ ok: true });
    await settle();
    assert.equal([...app.timers.values()][0].delay, 50);
    app.fireTimer();
    assert.equal(app.requests.length, 3);
    app.run("stopJog()");
    app.requests[2].respond({ ok: true });
    await settle();
    assert.equal(app.requests.length, 3);
    assert.equal(app.timers.size, 0);
});

test("a jog acknowledgement clears AUTO before the next toggle, despite a stale poll", async () => {
    const app = loadApp("web-armcontroller");
    app.requests[0].respond(motorState(true));
    await settle();
    app.fireTimer();
    const base = app.get("motors").querySelectorAll()[0];
    app.run('startJog("BASE", "dec"); stopJog()');
    app.requests[2].respond({ ok: true });
    await settle();
    app.requests[1].respond(motorState(true));
    await settle();
    assert.equal(base.attributes["aria-pressed"], "false");
    base.events.click();
    assert.deepEqual(app.requests[3].body, { motor: "BASE", active: true });
});

test("Orchestrator blocks another command for a device until its POST settles", async () => {
    const app = loadApp("web");
    app.run('selectDevice("ARM")');
    app.get("btn-pause").events.click();
    app.get("btn-start").events.click();
    assert.equal(app.requests.length, 2);
    assert.deepEqual(app.requests[1].body, { device: "ARM", command: "PAUSE" });
    assert.equal(app.get("btn-start").disabled, true);
    app.requests[1].respond({}, 503);
    await settle();
    assert.equal(app.get("btn-start").disabled, false);
    assert.match(app.get("command-status").textContent, /503/);
});
