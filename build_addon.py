from __future__ import annotations

import argparse
import pathlib
import zipfile


def _read_manifest_value(manifest_text: str, key: str) -> str:
	prefix = f"{key} ="
	for raw_line in manifest_text.splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#"):
			continue
		if line.startswith(prefix):
			return line[len(prefix) :].strip().strip('"')
	raise ValueError(f"Missing '{key}' in manifest.ini")


def build(addon_dir: pathlib.Path, output_dir: pathlib.Path) -> pathlib.Path:
	manifest_path = addon_dir / "manifest.ini"
	if not manifest_path.exists():
		raise FileNotFoundError(f"manifest not found: {manifest_path}")

	manifest_text = manifest_path.read_text(encoding="utf-8")
	name = _read_manifest_value(manifest_text, "name")
	version = _read_manifest_value(manifest_text, "version")

	output_dir.mkdir(parents=True, exist_ok=True)
	addon_path = output_dir / f"{name}-{version}.nvda-addon"

	with zipfile.ZipFile(addon_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
		for file_path in sorted(addon_dir.rglob("*")):
			if not file_path.is_file():
				continue
			if file_path.suffix.lower() in {".pyc", ".pyo"}:
				continue
			rel_path = file_path.relative_to(addon_dir).as_posix()
			archive.write(file_path, rel_path)

	return addon_path


def main() -> int:
	parser = argparse.ArgumentParser(description="Build NVDA add-on package (.nvda-addon)")
	parser.add_argument("--addon-dir", default="addon", help="Path to add-on root directory")
	parser.add_argument("--output-dir", default="dist", help="Output directory")
	args = parser.parse_args()

	root = pathlib.Path(__file__).resolve().parent
	addon_dir = (root / args.addon_dir).resolve()
	output_dir = (root / args.output_dir).resolve()

	addon_file = build(addon_dir, output_dir)
	print(f"Built: {addon_file}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
