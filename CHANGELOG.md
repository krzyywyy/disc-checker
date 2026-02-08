# Changelog

All notable changes to this project are documented in this file.

## [1.4.2] - 2026-02-08

### Changed
- CrystalDiskInfo runtime check execution is now launched hidden in the background.
- UAC prompt remains enabled and unchanged.
- Updated package/version metadata and documentation references to 1.4.2.

## [1.4.1] - 2026-02-08

### Changed
- Replaced MIT license with a non-commercial project license.
- Explicitly allows modification and redistribution for non-commercial use.
- Explicitly disallows selling and other commercial use.
- Updated package/version metadata and documentation references to 1.4.1.

## [1.4.0] - 2026-02-08

### Added
- Complete GitHub publication structure: `LICENSE`, `.gitignore`, `CHANGELOG.md`, release notes.
- Expanded project documentation in English.
- Explicit validation disclaimer: tested on only two computers.

### Changed
- Full repository language and add-on user-facing text migrated to English.
- Report output now uses English labels and keeps CrystalDiskInfo field coverage.
- Add-on metadata updated for English release.
- CrystalDiskInfo Smart runtime folder cleaned to remove machine-specific generated history files.

### Fixed
- Removed accidental inclusion of local SMART history artifacts from development environment.

## [1.3.2] - 2026-02-08

### Changed
- Report logic changed to show all available CrystalDiskInfo fields per disk.
- Removed non-CDI synthetic fields from output.

## [1.3.1] - 2026-02-08

### Changed
- Added ordered property rendering from CrystalDiskInfo sections.

## [1.3.0] - 2026-02-08

### Changed
- Switched diagnostic engine from smartctl to bundled CrystalDiskInfo.
- Enforced UAC elevation flow for each check.

## [1.2.0] - 2026-02-08

### Changed
- smartctl-based implementation with bundled binaries and UAC flow.
