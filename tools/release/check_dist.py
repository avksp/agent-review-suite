"""Validate packaged assets without extracting archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tarfile
import unicodedata
import zipfile
from collections.abc import Callable
from pathlib import Path

PRIVATE = {
    ".agent-lifecycle-authority", ".alk", ".env", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".venv", "__pycache__", "build", "dist", "events.jsonl", "htmlcov", "tasks", "work",
}
REQUIRED_ASSETS = (
    "README.ru.md",
    ".claude-plugin/marketplace.json",
    "adapters/qwen-code/projection.json",
    "docs/reference/request-report.md",
    "docs/reference/validation.md",
    "docs/ru/reference/request-report.md",
    "docs/ru/reference/validation.md",
    "docs/tutorials/first-validation.md",
    "docs/ru/tutorials/first-validation.md",
    "schemas/review-expectations.v1.schema.json",
    "schemas/review-report.v1.schema.json",
    "schemas/review-request.v1.schema.json",
    "skills/ars-review-security/SKILL.md",
)
FIXTURES = ("expectations.json", "report.json", "request.json")
SDIST_HELPERS = (
    "tools/check_repository.py",
    "tools/release/build_plugin.py",
    "tools/release/check_dist.py",
    "tools/release/smoke_install.py",
)
_MAX_MEMBER_BYTES = 16_777_216


def unsafe(name: str) -> bool:
    body = name.removesuffix("/")
    parts = body.casefold().split("/")
    forbidden_release = any(part == "release" and (index == 0 or parts[index - 1] != "tools")
                            for index, part in enumerate(parts))
    return (
        any(part in {"", ".", ".."} or part in PRIVATE or part.startswith(".env.")
            or part.endswith((".", " ")) for part in parts)
        or any(character in body for character in "\\:\0\r\n")
        or forbidden_release
    )


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value.casefold())


def contains_label(raw: bytes, labels: tuple[str, ...]) -> bool:
    text = _normalized(raw.decode("utf-8", errors="replace"))
    return any(_normalized(label) in text for label in labels)


def _layout(path: Path) -> tuple[str, str]:
    if path.suffix == ".whl":
        distribution, version, _ = path.name.split("-", 2)
        return "wheel", f"{distribution}-{version}.data/data/share/agent-review-suite/"
    if path.name.endswith(".tar.gz"):
        return "sdist", f"{path.name.removesuffix('.tar.gz')}/"
    return "plugin", ""


def _check_members(
    rows: list[tuple[str, bool, int, bool]],
    read: Callable[[str], bytes],
    path: Path,
    private_labels: tuple[str, ...],
) -> dict[str, object]:
    kind, prefix = _layout(path)
    names = [name for name, _, _, _ in rows]
    canonical = [_normalized(name.removesuffix("/")) for name in names]
    errors = [name for name, _, _, acceptable in rows if unsafe(name) or not acceptable]
    errors.extend(f"private label in member name: {name}" for name in names
                  if private_labels and contains_label(name.encode("utf-8"), private_labels))
    if len(canonical) != len(set(canonical)):
        errors.append("duplicate or aliased members")
    payload_names = {name for name, is_file, _, acceptable in rows if is_file and acceptable and not unsafe(name)}
    if kind == "sdist" and any(not name.startswith(prefix) and name != prefix.rstrip("/") for name in names):
        errors.append("member outside expected sdist root")

    required = {prefix + name: name for name in REQUIRED_ASSETS}
    fixture_paths = {prefix + f"tests/fixtures/{name}" for name in FIXTURES} if kind == "sdist" else set()
    required.update({name: name.removeprefix(prefix) for name in fixture_paths})
    if kind == "sdist":
        required.update({prefix + name: name for name in SDIST_HELPERS})
    for name in sorted(set(required) - payload_names):
        errors.append(f"missing {name}")
    for name in sorted(payload_names):
        if name.rsplit("/", 1)[-1].casefold() in FIXTURES and name not in fixture_paths:
            errors.append(f"unexpected synthetic fixture {name}")

    hashes: dict[str, str] = {}
    checked: set[str] = set()
    for name, _, size, _ in rows:
        if name not in payload_names or name in checked or (not private_labels and name not in required):
            continue
        checked.add(name)
        if size > _MAX_MEMBER_BYTES:
            errors.append(f"content-scan limit: {name}")
            continue
        raw = read(name)
        if len(raw) != size:
            errors.append(f"content size mismatch: {name}")
            continue
        if private_labels and contains_label(raw, private_labels):
            errors.append(f"private label: {name}")
        if name in required:
            hashes[required[name]] = hashlib.sha256(raw).hexdigest()
    return {
        "path": str(path), "kind": kind, "members": len(names), "errors": errors,
        "requiredAssetSHA256": hashes, "status": "FAIL" if errors else "PASS",
    }


def inspect(path: Path, private_labels: tuple[str, ...] = ()) -> dict[str, object]:
    """Check paths, member types, mandatory assets and optional private labels."""
    if path.suffix in {".whl", ".zip"}:
        with zipfile.ZipFile(path) as archive:
            rows = []
            for item in archive.infolist():
                kind = stat.S_IFMT(item.external_attr >> 16)
                directory = item.is_dir()
                accepted = item.orig_filename == item.filename and kind in {0, stat.S_IFDIR if directory else stat.S_IFREG}
                rows.append((item.filename, not directory, item.file_size, accepted))
            return _check_members(rows, archive.read, path, private_labels)

    with tarfile.open(path, "r:gz") as archive:

        def read(name: str) -> bytes:
            stream = archive.extractfile(name)
            if stream is None:
                raise ValueError("required member is unavailable")
            with stream:
                return stream.read(_MAX_MEMBER_BYTES + 1)

        rows = [(item.name, item.isfile(), item.size, item.isfile() or item.isdir())
                for item in archive.getmembers()]
        return _check_members(rows, read, path, private_labels)


def _shared_schema_errors(reports: list[dict[str, object]]) -> list[str]:
    if {row["kind"] for row in reports} != {"wheel", "sdist", "plugin"}:
        return []
    schemas = [name for name in REQUIRED_ASSETS if name.startswith("schemas/")]
    errors = []
    for schema in schemas:
        observed = {assets.get(schema) for row in reports
                    if isinstance(assets := row.get("requiredAssetSHA256"), dict)}
        if len(observed) != 1 or None in observed:
            errors.append(f"schema bytes differ across distributions: {schema}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--private-labels", type=Path, help="unshipped bounded JSON list")
    mode.add_argument("--public-ci", action="store_true", help="structural checks without private inputs")
    parser.add_argument("archives", type=Path, nargs="+")
    args = parser.parse_args()
    labels = ()
    if args.private_labels:
        try:
            if args.private_labels.stat().st_size > 65536:
                raise ValueError()
            data = json.loads(args.private_labels.read_bytes())
            if not isinstance(data, list) or not 1 <= len(data) <= 128 or not all(
                isinstance(item, str) and 0 < len(item) <= 200 for item in data
            ):
                raise ValueError()
        except (OSError, ValueError):
            parser.error("expected an available nonempty bounded private label list")
        labels = tuple(data)
    reports = [inspect(path, labels) for path in args.archives]
    shared = _shared_schema_errors(reports)
    print(json.dumps({"archives": reports, "sharedErrors": shared,
                      "screening": "PUBLIC_CI_STRUCTURAL_ONLY" if args.public_ci else "PRIVATE_LABELS"}, indent=2))
    raise SystemExit(bool(shared) or any(row["errors"] for row in reports))
