# Disc Checker 1.4.4 Release Notes

## Highlights

- Fixed the issue where checking disk health could finish with no final report.
- Improved CrystalDiskInfo output collection reliability while keeping UAC flow unchanged.

## What changed in 1.4.4

- Added dual output capture:
  - `DiskInfo.txt` file output, and
  - `/CopyExit` clipboard text output.
- Cleared stale `DiskInfo.txt` before each run to avoid reusing old data.
- Added build-time exclusions so local runtime artifacts are never packed into releases.

## Validation scope

This version was tested on **only two computers**.

## Included assets

- `discChecker-1.4.4.nvda-addon`
- `SHA256SUMS.txt`
