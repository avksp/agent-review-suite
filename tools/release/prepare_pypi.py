"""Stage a wheel and sdist from the successful main CI for the release commit."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

_PROJECT = "agent_review_suite"
_MAX_BYTES = 16 * 1024 * 1024
_MATRIX = {
    f"Python {version} / {runner}": (runner, version)
    for runner in ("ubuntu-latest", "macos-26-intel", "windows-latest")
    for version in ("3.11", "3.12", "3.13", "3.14", "3.15")
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, timeout=30).strip()


def _api(path: str) -> dict:
    return json.loads(subprocess.check_output(["gh", "api", path], timeout=30))


def _version() -> str:
    source = Path("src/agent_review_suite/_version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$', source, re.MULTILINE)
    if match is None:
        raise ValueError("Expected a stable package version in _version.py")
    return match[1]


def _check_ref(commit: str, version: str) -> None:
    if re.fullmatch(r"[a-f0-9]{40}", commit) is None or _git("rev-parse", "HEAD") != commit:
        raise ValueError("Checked out commit differs from the workflow source")
    _git("merge-base", "--is-ancestor", commit, "refs/remotes/origin/main")
    if os.environ["GITHUB_EVENT_NAME"] == "release":
        tag = f"refs/tags/v{version}"
        if os.environ["GITHUB_REF"] != tag or _git("rev-parse", "--verify", f"{tag}^{{commit}}") != commit:
            raise ValueError("Release tag, version and source commit must match")


def _check_run(run: dict, commit: str, workflow: str = "ci.yml") -> None:
    expected = {
        "head_sha": commit,
        "head_branch": "main",
        "event": "push",
        "path": f".github/workflows/{workflow}",
        "status": "completed",
        "conclusion": "success",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError(f"The latest {workflow} push run for the release commit must pass")


def _check_jobs(jobs: list[dict], commit: str) -> None:
    if len(jobs) != len(_MATRIX) or {job["name"] for job in jobs} != set(_MATRIX):
        raise ValueError("CI job inventory differs from the required matrix")
    if any(job["head_sha"] != commit or job["status"] != "completed" or job["conclusion"] != "success"
           for job in jobs):
        raise ValueError("Every matrix job must pass on the release commit")


def _successful_push(prefix: str, workflow: str, commit: str) -> int:
    runs = _api(f"{prefix}/workflows/{workflow}/runs?branch=main&event=push&head_sha={commit}&per_page=1")
    if not runs["workflow_runs"]:
        raise ValueError(f"Run {workflow} on main for the release commit before publishing")
    run = runs["workflow_runs"][0]
    _check_run(run, commit, workflow)
    return run["id"]


def _check_codeql(jobs: list[dict], commit: str) -> None:
    if len(jobs) != 1:
        raise ValueError("Expected one CodeQL job for the release commit")
    job = jobs[0]
    if (
        job["name"] != "CodeQL / Python"
        or job["status"] != "completed"
        or job["conclusion"] != "success"
        or job["head_sha"] != commit
        or not any(step["name"] == "Analyze Python" and step["conclusion"] == "success" for step in job["steps"])
    ):
        raise ValueError("CodeQL analysis must pass on the release commit")


def _artifact(artifacts: list[dict], run_id: int, commit: str) -> dict:
    names = {f"ars-{runner}-{version}-{commit}" for runner, version in _MATRIX.values()}
    if len(artifacts) != len(names) or {entry["name"] for entry in artifacts} != names:
        raise ValueError("CI must provide one artifact for each matrix job")
    entry, = [row for row in artifacts if row["name"] == f"ars-ubuntu-latest-3.12-{commit}"]
    origin = entry["workflow_run"]
    if (entry["expired"] or not 0 < entry["size_in_bytes"] <= _MAX_BYTES
            or origin["id"] != run_id or origin["head_branch"] != "main" or origin["head_sha"] != commit
            or re.fullmatch(r"sha256:[a-f0-9]{64}", entry.get("digest") or "") is None):
        raise ValueError("The CI artifact is unavailable or lacks the required source binding")
    return entry


def _stage(archive: Path, artifact: dict, version: str, output: Path) -> dict[str, str]:
    if archive.stat().st_size != artifact["size_in_bytes"]:
        raise ValueError("CI archive size differs from its GitHub record")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if f"sha256:{digest}" != artifact["digest"]:
        raise ValueError("CI archive digest differs from its GitHub record")

    wheel = f"{_PROJECT}-{version}-py3-none-any.whl"
    sdist = f"{_PROJECT}-{version}.tar.gz"
    with zipfile.ZipFile(archive) as package:
        members = package.namelist()
        distributions = [name for name in members if name.endswith((".whl", ".tar.gz"))]
        if sorted(distributions) != sorted([wheel, sdist]):
            raise ValueError("CI must provide exactly the wheel and sdist for the release version")
        payloads = {}
        for name in (wheel, sdist):
            entry = package.getinfo(name)
            if not 0 < entry.file_size <= _MAX_BYTES:
                raise ValueError("CI distribution exceeds the size limit")
            payloads[name] = package.read(entry)

    output.mkdir()
    for name, data in payloads.items():
        (output / name).write_bytes(data)
    return {
        "version": version,
        "wheel_sha256": hashlib.sha256(payloads[wheel]).hexdigest(),
        "sdist_sha256": hashlib.sha256(payloads[sdist]).hexdigest(),
    }


def main() -> None:
    commit = os.environ["GITHUB_SHA"]
    version = _version()
    _check_ref(commit, version)
    repository = os.environ["GITHUB_REPOSITORY"]
    prefix = f"repos/{repository}/actions"
    codeql_id = _successful_push(prefix, "codeql.yml", commit)
    _check_codeql(_api(f"{prefix}/runs/{codeql_id}/jobs?filter=latest&per_page=100")["jobs"], commit)
    run_id = _successful_push(prefix, "ci.yml", commit)
    _check_jobs(_api(f"{prefix}/runs/{run_id}/jobs?filter=latest&per_page=100")["jobs"], commit)
    artifact = _artifact(_api(f"{prefix}/runs/{run_id}/artifacts?per_page=100")["artifacts"], run_id, commit)

    with tempfile.TemporaryDirectory() as scratch:
        archive = Path(scratch) / "ci.zip"
        with archive.open("wb") as stream:
            subprocess.run(
                ["gh", "api", "--allow-escape-sequences", f"{prefix}/artifacts/{artifact['id']}/zip"],
                stdout=stream, check=True, timeout=90,
            )
        outputs = _stage(archive, artifact, version, Path("pypi-files"))

    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        for name, value in outputs.items():
            stream.write(f"{name}={value}\n")
    print(f"Qualified {commit} with CI run {run_id}, artifact {artifact['id']} ({artifact['digest']})")
    print(f"Qualified Python CodeQL run {codeql_id} on {commit}")
    print(json.dumps(outputs, sort_keys=True))


if __name__ == "__main__":
    main()
