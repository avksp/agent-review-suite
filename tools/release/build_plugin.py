"""Build guidance assets from an explicit public allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_TREES = ("docs", "skills", "adapters", "profiles", "schemas", ".codex-plugin", ".claude-plugin", ".agents")
PUBLIC_FILES = ("README.md", "INSTALL_FOR_AGENTS.md", "LICENSE", "NOTICE", "plugin.json")


def members(root: Path) -> list[Path]:
    paths = [root / name for name in PUBLIC_FILES]
    for name in PUBLIC_TREES:
        paths.extend(p for p in (root / name).rglob("*") if p.is_file())
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"unsafe public asset: {path}")
    return sorted(paths)


def build(root: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = []
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in members(root):
            raw = path.read_bytes()
            name = path.relative_to(root).as_posix()
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, raw)
            inventory.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return {"archive": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "members": inventory}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(ROOT, args.output)
    receipt = args.output.with_suffix(".inventory.json")
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"archive": str(args.output), "members": len(report["members"]), "receipt": str(receipt)}))
