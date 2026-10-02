const assert = require("node:assert/strict");
const vscode = require("vscode");

const titles = ["ArmController", "Orchestrator", "Arm", "PatientMonitor"];
const ports = [8091, 8090, 8092, 8093];

async function waitFor(predicate) {
    for (let attempt = 0; attempt < 100; attempt++) {
        if (predicate()) return;
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("Timed out waiting for editor tabs");
}

function positions() {
    return Object.fromEntries(vscode.window.tabGroups.all.flatMap((group) =>
        group.tabs.filter((tab) => titles.includes(tab.label))
            .map((tab) => [tab.label, group.viewColumn])));
}

async function verify(label, expected = titles) {
    const layout = await vscode.commands.executeCommand("vscode.getEditorLayout");
    const actual = positions();
    console.log("GRID CHECK", label, JSON.stringify(layout), JSON.stringify(actual));
    assert.equal(layout.orientation, 1);
    assert.equal(layout.groups.length, 2);
    assert.deepEqual(layout.groups.map((group) => group.groups?.length), [2, 2]);
    assert.ok(layout.groups.every((group) => group.size > 100
        && group.groups.every((child) => child.size > 100)), "Grid cells must remain visible");
    assert.deepEqual(Object.keys(actual).sort(), [...expected].sort());
    assert.deepEqual(expected.map((name) => actual[name]), expected.map((name) => titles.indexOf(name) + 1));
}

async function open(title) {
    const query = new URLSearchParams({ title, url: `http://localhost:${ports[titles.indexOf(title)]}/` });
    await vscode.env.openExternal(vscode.Uri.parse(`vscode://rti.medtech-web-tabs/open?${query}`));
    await waitFor(() => positions()[title] !== undefined);
}

async function close(title) {
    const tab = vscode.window.tabGroups.all.flatMap((group) => group.tabs)
        .find((candidate) => candidate.label === title);
    assert.ok(tab, `Missing tab ${title}`);
    assert.equal(await vscode.window.tabGroups.close(tab), true);
    await waitFor(() => positions()[title] === undefined);
}

function* permutations(items) {
    if (!items.length) {
        yield [];
    } else {
        for (const item of items) {
            for (const rest of permutations(items.filter((candidate) => candidate !== item))) {
                yield [item, ...rest];
            }
        }
    }
}

async function run() {
    for (const title of titles) await open(title);
    await verify("initial");
    for (const title of ["Arm", "Orchestrator", "ArmController", "PatientMonitor", "Arm", "PatientMonitor", "ArmController", "Orchestrator"]) {
        await close(title);
        await open(title);
        await verify(`restored ${title}`);
    }
    for (const pair of [["Arm", "Orchestrator"], ["PatientMonitor", "ArmController"], ["Arm", "PatientMonitor"]]) {
        for (const title of pair) await close(title);
        const restored = new Set();
        for (const title of [...pair].reverse()) {
            await open(title);
            restored.add(title);
            await verify(`partially restored ${pair.join("+")}`, titles.filter((name) =>
                !pair.includes(name) || restored.has(name)));
        }
        await verify(`restored ${pair.join("+")}`);
    }
    for (const missing of titles) {
        const closed = titles.filter((title) => title !== missing);
        for (const title of closed) await close(title);
        const restored = new Set();
        for (const title of [...closed].reverse()) {
            await open(title);
            restored.add(title);
            await verify(`triple restore ${missing}/${title}`, [missing, ...restored]);
        }
    }
    await close("Arm");
    await close("Orchestrator");
    await Promise.all([open("Arm"), open("Orchestrator")]);
    await new Promise((resolve) => setTimeout(resolve, 100));
    await verify("simultaneous restore");
    for (const order of permutations(titles)) {
        for (const title of titles) await close(title);
        const restored = [];
        for (const title of order) {
            await open(title);
            restored.push(title);
            await verify(`restored from empty/${order.join("+")}/${title}`, restored);
        }
    }
    await vscode.env.openExternal(vscode.Uri.parse("vscode://rti.medtech-web-tabs/close"));
}

module.exports = { run };