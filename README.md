# Disc Checker (NVDA Add-on)

Disc Checker is an NVDA add-on that reads disk health information using a bundled CrystalDiskInfo runtime.

The add-on runs in the background, requests elevation (UAC) for every check, and presents results in a single accessible report.

## Status

- Current version: `1.4.1`
- Package: `dist/discChecker-1.4.1.nvda-addon`
- Platform: Windows (NVDA add-on)
- Diagnostic engine: bundled CrystalDiskInfo (`DiskInfo64.exe`)

## Important Testing Note

This project has been tested on **only two computers** so far.  
Coverage is limited, and behavior can vary between controllers, USB bridges, RAID modes, and firmware implementations.

## Features

- No separate external installation required for end users.
- Bundled CrystalDiskInfo runtime inside the add-on package.
- UAC elevation prompt on each run (by design, no fallback path).
- Per-disk report with:
  - Health percentage
  - Temperature
  - All detected key/value fields from CrystalDiskInfo disk sections
- NVDA integration:
  - Tools menu entry: `Check disk health`
  - Keyboard shortcut: `NVDA+Shift+D`

## Installation (End User)

1. Download the latest `.nvda-addon` from GitHub Releases.
2. Open the file with NVDA and confirm installation.
3. Restart NVDA when prompted.

## Usage

1. Trigger the add-on from:
   - `NVDA menu > Tools > Check disk health`, or
   - `NVDA+Shift+D`
2. Accept the UAC prompt.
3. Wait for spoken summary and browseable full report.

## Build From Source

### Prerequisites

- Windows
- Python 3.10+ (recommended: 3.11+)

### Build command

```powershell
python .\build_addon.py
```

The generated package is written to `dist/`.

## Repository Layout

- `addon/manifest.ini` - NVDA add-on manifest.
- `addon/globalPlugins/diskHealthChecker.py` - main add-on logic.
- `addon/bin/crystaldiskinfo/` - bundled CrystalDiskInfo runtime and resources.
- `addon/doc/en/readme.html` - bundled add-on documentation (English).
- `addon/doc/pl/readme.html` - bundled add-on documentation (currently English content for consistency).
- `build_addon.py` - `.nvda-addon` build script.
- `CHANGELOG.md` - version history.

## Privacy and Data Handling

- The add-on does not upload telemetry.
- CrystalDiskInfo may create local SMART history files inside the bundled `Smart` directory at runtime.
- Reports include disk model and serial data when available; treat exported reports as sensitive.

## Limitations

- Requires UAC acceptance each run.
- Depends on what CrystalDiskInfo can detect on a specific hardware/storage stack.
- Non-standard controllers and encrypted/virtualized layers may expose incomplete attributes.

## Third-Party Components

- CrystalDiskInfo binaries and resource files are redistributed in `addon/bin/crystaldiskinfo/`.
- Upstream third-party license files are preserved in `addon/bin/crystaldiskinfo/License/`.

## License

- Project code: Disc Checker Non-Commercial License 1.0 (see `LICENSE`).
- Modifications are allowed.
- Commercial use and selling are not allowed.
- Bundled third-party components remain under their respective licenses.
