"""Verify the publish gate rejects missing CI proof and changed release bytes."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.release import prepare_pypi

_COMMIT = "a" * 40
_VERSION = "0.1.0"
_WHEEL = "agent_review_suite-0.1.0-py3-none-any.whl"
_SDIST = "agent_review_suite-0.1.0.tar.gz"


class PreparePypiTests(unittest.TestCase):
    def test_requires_successful_main_push_for_exact_commit(self):
        run = {
            "head_sha": _COMMIT, "head_branch": "main", "event": "push",
            "path": ".github/workflows/ci.yml", "status": "completed", "conclusion": "success",
        }
        prepare_pypi._check_run(run, _COMMIT)
        for update in ({"event": "pull_request"}, {"head_sha": "b" * 40}, {"conclusion": "failure"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                prepare_pypi._check_run(run | update, _COMMIT)

    def test_requires_all_matrix_jobs_on_same_commit(self):
        jobs = [{"name": name, "status": "completed", "conclusion": "success", "head_sha": _COMMIT}
                for name in prepare_pypi._MATRIX]
        prepare_pypi._check_jobs(jobs, _COMMIT)
        with self.assertRaises(ValueError):
            prepare_pypi._check_jobs(jobs[:-1], _COMMIT)
        jobs[0]["head_sha"] = "b" * 40
        with self.assertRaises(ValueError):
            prepare_pypi._check_jobs(jobs, _COMMIT)

    def test_only_matching_release_ref_can_qualify(self):
        env = {"GITHUB_EVENT_NAME": "release", "GITHUB_REF": "refs/tags/v0.1.1"}
        with patch.dict("os.environ", env), patch.object(prepare_pypi, "_git", return_value=_COMMIT):
            with self.assertRaisesRegex(ValueError, "Release tag"):
                prepare_pypi._check_ref(_COMMIT, _VERSION)

    def test_stages_only_qualified_wheel_and_sdist(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bundle = root / "matrix.zip"
            with zipfile.ZipFile(bundle, "w") as archive:
                archive.writestr(_WHEEL, b"synthetic wheel")
                archive.writestr(_SDIST, b"synthetic sdist")
                archive.writestr("agent-review-suite-plugin.zip", b"plugin")
            digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
            artifact = {"size_in_bytes": bundle.stat().st_size, "digest": f"sha256:{digest}"}
            output = root / "pypi-files"
            with self.assertRaisesRegex(ValueError, "digest differs"):
                prepare_pypi._stage(bundle, artifact | {"digest": "sha256:" + "0" * 64}, _VERSION, output)
            with self.assertRaisesRegex(ValueError, "release version"):
                prepare_pypi._stage(bundle, artifact, "0.1.1", output)
            self.assertFalse(output.exists())
            outputs = prepare_pypi._stage(bundle, artifact, _VERSION, output)
            self.assertEqual({path.name for path in output.iterdir()}, {_WHEEL, _SDIST})
            self.assertEqual((output / _WHEEL).read_bytes(), b"synthetic wheel")
            self.assertEqual((output / _SDIST).read_bytes(), b"synthetic sdist")
            self.assertEqual(outputs["wheel_sha256"], hashlib.sha256(b"synthetic wheel").hexdigest())
