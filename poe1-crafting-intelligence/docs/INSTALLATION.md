# Installation (Windows)

You need **Python** and **Git**. Node.js is not needed until the React frontend arrives in a later phase.

## 1. Install the tools (once)

1. **Python 3.12 or 3.13**: download it from https://www.python.org/downloads/windows/.
   In the installer, **tick "Add python.exe to PATH"** and then click *Install Now*.
2. **Git**: download it from https://git-scm.com/download/win and accept the defaults.
3. Open **PowerShell** (Start menu → type "PowerShell") and check both are installed:
   ```powershell
   python --version   # should print Python 3.12.x or 3.13.x
   git --version
   ```

## 2. Get the code

```powershell
cd $HOME\Documents
git clone https://github.com/lom-ali96/media-shelf-releases.git
cd media-shelf-releases
git checkout claude/poe1-crafting-intelligence-ulb959
cd poe1-crafting-intelligence
```

## 3. One-time setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This does three things:
- creates a private Python environment in `.venv\`;
- installs the dependencies;
- downloads the current game data (about 60 MB) into `data\snapshots\<version>\`.

## 4. Start the app

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Then open **http://127.0.0.1:8765** in your browser. Stop the app with **Ctrl+C** in the PowerShell window.

The app only listens on your own PC (127.0.0.1). To reach it from another device, see SECURITY.md first.

## 5. First steps in the app

1. **Settings → League:** type the league name exactly as poe.ninja shows it, for example `Covens` (poe.ninja's short name, not "Covens of Umbra"), and click Save.
2. **Settings → Fetch prices:** this loads currency, essence and fossil prices. If it fails, enter prices manually under *Manual price*.
3. **Mod Pool:** pick a base and see every rollable mod with its exact probability.
4. **Item Analyzer:** in game, hover an item and press **Ctrl+Alt+C**, then paste it here.
5. **Simulator:** for example *Chaos Orb* on a rare *Sapphire Ring* until `IncreasedLife:2`, meaning a tier 1 or 2 life roll.

## 6. Run the tests

```powershell
.\.venv\Scripts\python -m pytest -q backend
```

All tests should pass. Tests marked `realdata` run only when game data has been imported.

## 7. Update

```powershell
git pull
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1      # reinstalls deps, fetches newer game data if any
```

See UPDATE_GUIDE.md for what to do after a new PoE patch.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python` not found | Reinstall Python with "Add to PATH" ticked, then open a **new** PowerShell window |
| "running scripts is disabled" | Use the `powershell -ExecutionPolicy Bypass -File ...` form shown above |
| Port 8765 is in use | Run `$env:POECI_PORT=8766` before the start script |
| "No game data imported" | Run `.\.venv\Scripts\python -m poeci.knowledge.importer` |
| Fetching prices fails | Check your internet connection; poe.ninja can change without notice. Use manual prices meanwhile and report the error text |
