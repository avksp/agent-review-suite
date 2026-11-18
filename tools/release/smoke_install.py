"""Install the supplied wheel outside the checkout and exercise its entry points."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def smoke(wheel: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    scratch = Path(tempfile.gettempdir()).resolve()
    if os.name == "posix" and scratch.is_relative_to(ROOT):
        scratch = Path("/tmp").resolve()
    if scratch.is_relative_to(ROOT):
        raise ValueError("wheel smoke environment must be outside the checkout")

    with tempfile.TemporaryDirectory(prefix="ars-wheel-smoke-", dir=scratch) as directory:
        root = Path(directory).resolve()
        venv.create(root / "venv", with_pip=True)
        python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", str(wheel.resolve())],
            cwd=root, env=environment, check=True, timeout=120,
        )
        for name in ("request.json", "report.json", "expectations.json"):
            shutil.copyfile(ROOT / "tests/fixtures" / name, root / name)

        code = """
from importlib.metadata import version
from pathlib import Path
import sys
import agent_review_suite as ars
from agent_review_suite.contracts import validate_bytes

prefix = Path(sys.prefix).resolve()
assert Path(ars.__file__).resolve().is_relative_to(prefix)
assert ars.__version__ == version('agent-review-suite') == '0.1.0'
share = prefix / 'share/agent-review-suite'
for name in ('INSTALL_FOR_AGENTS.md', 'schemas/review-request.v1.schema.json','schemas/review-report.v1.schema.json',
             'schemas/review-expectations.v1.schema.json',
             'docs/tutorials/first-validation.md','docs/ru/tutorials/first-validation.md',
             'docs/reference/validation.md','docs/ru/reference/validation.md',
             'skills/ars-review-security/SKILL.md','.codex-plugin/plugin.json'):
    assert (share / name).is_file(), name
assert not (share / 'tests').exists()
assert not (prefix / 'tests').exists()
result = validate_bytes('report', Path('report.json').read_bytes(), Path('expectations.json').read_bytes())
assert result['executionStatus'] == 'COMPLETE'
print('clean-wheel-import-assets-and-pure-api: PASS', Path(ars.__file__).resolve())
"""
        subprocess.run([str(python), "-I", "-B", "-c", code], cwd=root, env=environment, check=True, timeout=30)
        cli = subprocess.run(
            [str(python), "-I", "-B", "-m", "agent_review_suite", "validate", "--kind", "report",
             "--input", "report.json", "--root", str(root), "--expectations", "expectations.json"],
            cwd=root, env=environment, capture_output=True, timeout=30,
        )
        expected = 2 if os.name == "nt" else 0
        if cli.returncode != expected or (expected == 0 and cli.stdout != b'{"status":"VALID"}\n'):
            raise RuntimeError(f"installed CLI returned {cli.returncode}; expected {expected}")
        print(f"clean-wheel-module-validation: PASS (exit {expected})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    smoke(parser.parse_args().wheel)
