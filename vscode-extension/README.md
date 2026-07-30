# MedTech Web Tabs

This local VS Code extension receives the URLs emitted by `launch.py --vscode` and opens each Digital Operating Room UI in VS Code editor tabs.

## What it does

- Opens the four browser-based Digital Operating Room applications in a 2x2 editor grid:
	- Top-left: Arm Controller
	- Top-right: Surgical Arm Monitor
	- Bottom-left: Orchestrator
	- Bottom-right: Patient Monitor
- Closes only these MedTech web tabs when the launcher exits, including after `Ctrl+C`.
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

## Troubleshooting

- Tabs open in a browser: install the VSIX and reload VS Code; `--vscode` needs this extension to receive the launcher URI.
- Layout is stale: close the existing MedTech tabs, reload VS Code, and launch again.
- A webview is blank: confirm the launcher is still running and that the corresponding localhost port is available.