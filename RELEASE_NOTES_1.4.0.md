# Disc Checker 1.4.0 Release Notes

## Highlights

- Full English release of both add-on and repository.
- Accessibility-focused disk health reporting for NVDA users.
- Bundled CrystalDiskInfo runtime (no separate user installation).
- UAC elevation required on each run to maximize hardware access reliability.

## What changed in 1.4.0

- Translated all user-facing add-on strings to English.
- Updated repository and bundled docs to English.
- Cleaned bundled CrystalDiskInfo Smart folder to remove machine-generated history artifacts.
- Added publication-ready repository files:
  - `LICENSE`
  - `.gitignore`
  - `CHANGELOG.md`
  - this release notes file

## Included package

- `discChecker-1.4.0.nvda-addon`

## Validation scope

This version was tested on **only two computers**.

Because storage stacks differ significantly across systems, additional community validation is strongly recommended.

## Known limitations

- Requires UAC consent on every check.
- Results depend on what CrystalDiskInfo can read through the active controller/bridge stack.
