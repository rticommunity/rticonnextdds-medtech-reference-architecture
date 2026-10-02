# MedTech Web Tabs

This VS Code extension receives the URLs emitted by `launch.py --vscode` and opens each Digital Operating Room UI in editor tabs. In code-server it also provides a native guided tutorial side panel.

## What it does

- Opens Arm Controller, Surgical Arm Monitor, Orchestrator, and Patient Monitor in a 2x2 editor grid.
- Closes only these MedTech web tabs when the launcher exits, including after `Ctrl+C`.
- Closing a device tab manually kills its launcher-owned process, stopping DDS heartbeats.
	Keep Orchestrator open to observe the disconnect; select the device and use **Start**
	to relaunch it and reopen its tab. Start also resumes paused devices. Patient Sensor
	can be restarted without a tab. Plain browser tabs (`--web`) do not have launcher recovery.
- Use **Digital Operating Room: Open Orchestrator** in the Command Palette if the
  Orchestrator itself was closed or stopped. The full demo must have been launched first.
- Accepts only HTTP(S) URLs hosted at `localhost`, `127.0.0.1`, or `::1`.

## Install or update

Run these commands from the repository root to build the extension archive:

```bash
cd medtech-reference-architecture/vscode-extension
npx --yes @vscode/vsce package --allow-missing-repository
```

1. Run **Extensions: Install from VSIX...** from the Command Palette.
2. Select `medtech-web-tabs-0.1.0.vsix` from this directory.
3. Reload the VS Code window when prompted.

Rebuild and reinstall the VSIX after changing `extension.js` or `package.json`.

## Run the demo

From the repository root:

```bash
python3 launch.py 01-operating-room --vscode
```

The launcher starts the web apps and opens the four tabs in the configured grid. Use `Ctrl+C` in that launcher terminal to stop the apps and close the MedTech tabs.

## Cloud IDE

Open the browser IDE at `http://127.0.0.1:8080/?folder=/config/workspace`, trust this
workspace, and run `./tutorial/launch_all.sh --cloud` from `/config/workspace` once.
The launcher installs this extension directly into `/config/extensions`. Reload the
browser IDE once after an initial installation or update if the Digital Operating
Room activity icon is missing, and select that icon before launching when multiple
IDE windows are open.

The ten-step tutorial lives in a native side panel; device frames use code-server's
`/proxy/<port>/` routes. Launcher requests are atomically queued in the container's
temporary directory, with a single focused extension host consuming them. No
desktop `vscode://` URI handler is needed. Device recovery is controlled by Orchestrator
Start, not the tutorial sidebar. After setup, `launch_all.sh` runs the demo in the
background and returns the terminal prompt. Use `./tutorial/stop_all.sh` to stop
it or `./tutorial/restart_all.sh` to restart it. Closing a terminal or separate
browser page does not stop the background demo.

## Troubleshooting

- Tabs open in a browser: install the VSIX and reload VS Code; `--vscode` needs this extension to receive the launcher URI.
- Layout is stale: close the existing MedTech tabs, reload VS Code, and launch again.
- A webview is blank: confirm the launcher is still running and that the corresponding localhost port is available.