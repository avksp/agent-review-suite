"""Check release source, public claims, and private asset boundaries."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TREES = ("src", "schemas", "profiles", "adapters", "skills", "docs", "tools", "tests", ".github", ".agents", ".codex-plugin", ".claude-plugin")
HOSTS = {
    "claude", "codex", "cursor", "gemini-cli", "goose", "grok-build",
    "hermes", "kimi-code", "opencode", "openinterpreter", "pi", "qwen-code",
}


def private_label_errors(root: Path, labels: tuple[str, ...]) -> list[str]:
    """Labels are private caller input, never bundled project assignments."""
    if not labels:
        return []
    if (root / ".git").exists():
        raw = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root, timeout=20,
        )
        paths = [root / name for name in sorted(set(raw.decode("utf-8").split("\0"))) if name]
    else:
        paths = [p for p in root.iterdir() if p.is_file() and p.name != "events.jsonl"]
        for tree in PUBLIC_TREES:
            paths.extend(p for p in (root / tree).rglob("*") if p.is_file())
    normalized_labels = tuple(unicodedata.normalize("NFC", label.casefold()) for label in labels)
    errors = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        linked = path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root))
        if linked or not path.is_file():
            errors.append(f"unsafe public asset: {relative}")
            continue
        if path.stat().st_size > 16_777_216:
            errors.append(f"content-scan limit: {relative}")
            continue
        name = unicodedata.normalize("NFC", relative.casefold())
        text = unicodedata.normalize("NFC", path.read_bytes().decode("utf-8", errors="replace").casefold())
        if any(label in name or label in text for label in normalized_labels):
            errors.append(f"private label in public asset: {relative}")
    return errors


def load_private_labels(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    if path.stat().st_size > 65536:
        raise ValueError("private label input exceeds 65536 bytes")
    data = json.loads(path.read_bytes())
    if not isinstance(data, list) or not 1 <= len(data) <= 128:
        raise ValueError("expected 1 to 128 private labels")
    if not all(isinstance(item, str) and 0 < len(item) <= 200 for item in data):
        raise ValueError("private labels must be nonempty bounded strings")
    return tuple(data)


def action_reference_errors(workflow: str) -> list[str]:
    errors: list[str] = []
    references = 0
    for number, line in enumerate(workflow.splitlines(), 1):
        match = re.fullmatch(r"\s*(?:-\s+)?uses:\s*(.*)", line)
        if match is None:
            continue
        references += 1
        reference = match[1].split(" #", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[a-f0-9]{40}", reference) is None:
            errors.append(f"invalid pinned action reference at line {number}")
    if references != 3:
        errors.append("CI must define three pinned action references")
    return errors


def check(root: Path = ROOT, private_labels: tuple[str, ...] = ()) -> list[str]:
    errors: list[str] = []
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = re.search(r'__version__ = "([^"]+)"', (root / "src/agent_review_suite/_version.py").read_text(encoding="utf-8"))
    assert version is not None
    for name in ["plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"]:
        if json.loads((root / name).read_text(encoding="utf-8"))["version"] != version[1]:
            errors.append(f"version drift: {name}")
    if config["project"]["dependencies"] or "scripts" in config["project"]:
        errors.append("standalone module must not declare runtime dependencies or console scripts")
    if {p.parent.name for p in (root / "adapters").glob("*/projection.json")} != HOSTS:
        errors.append("host inventory differs from the declared 12-host target")
    for path in (root / "adapters").glob("*/projection.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "UNQUALIFIED" or data.get("enforcementClaimed") is not False:
            errors.append(f"unsupported host qualification claim: {path.relative_to(root)}")
    markdown = list((root / "docs").rglob("*.md")) + list((root / "skills").rglob("*.md"))
    markdown += list(root.glob("*.md"))
    for path in markdown:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding="utf-8")):
            if target.startswith(("http:", "https:", "#", "mailto:")):
                continue
            target = target.split("#")[0]
            destination = (path.parent / target).resolve()
            if not destination.is_relative_to(root) or not destination.exists():
                errors.append(f"broken local link: {path.relative_to(root)} -> {target}")
    for path in (root / "docs").rglob("*.md"):
        rel = path.relative_to(root / "docs")
        if rel.parts[0] != "ru" and not (root / "docs/ru" / rel).is_file():
            errors.append(f"missing Russian counterpart: {rel}")
    for path in (root / "skills").glob("*/SKILL.md"):
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---\nname: " + path.parent.name + "\ndescription: "):
            errors.append(f"invalid skill metadata: {path.parent.name}")
        if len(content.splitlines()) > 120:
            errors.append(f"skill entrypoint too large: {path.parent.name}")
        agent = path.parent / "agents/openai.yaml"
        if "$" + path.parent.name not in agent.read_text(encoding="utf-8"):
            errors.append(f"missing explicit skill name: {agent}")
    ci = root / ".github/workflows/ci.yml"
    if ci.is_file():
        errors.extend(action_reference_errors(ci.read_text(encoding="utf-8")))
    elif (root / ".git").exists():
        errors.append("active CI workflow is missing")
    errors.extend(private_label_errors(root, private_labels))
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--private-labels", type=Path, help="unshipped JSON list supplied by the project owner")
    mode.add_argument("--public-ci", action="store_true", help="structural checks without private inputs")
    try:
        options = parser.parse_args()
        labels = load_private_labels(options.private_labels)
    except (OSError, ValueError):
        parser.error("expected an available nonempty bounded private label list")
    failures = check(private_labels=labels)
    print(json.dumps({"status": "FAIL" if failures else "PASS", "errors": failures,
                      "screening": "PUBLIC_CI_STRUCTURAL_ONLY" if options.public_ci else "PRIVATE_LABELS"}, indent=2))
    raise SystemExit(bool(failures))
