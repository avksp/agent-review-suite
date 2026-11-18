"""Exercise the actual CLI and combined intake boundary."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_review_suite import bounded_io
from agent_review_suite.__main__ import main
from agent_review_suite.bounded_io import supports_local_intake
from agent_review_suite.contracts import ValidationError
from agent_review_suite.validation import validate_inputs

SOURCE = Path(__file__).resolve().parents[1]
FIXTURES = SOURCE / "tests/fixtures"
MALFORMED = f"ARS validation failed: malformed, refused, or unsupported input.{os.linesep}".encode("ascii")


def cli_args(root, name="request.json", *, kind="request", expectations="expected.json"):
    return ["validate", "--kind", kind, "--input", name, "--root", str(root), "--expectations", expectations]


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): (path.stat().st_mode, path.stat().st_mtime_ns,
                                           path.read_bytes() if path.is_file() else None)
        for path in root.rglob("*")
    }


def command(args, **kwargs):
    env = {**os.environ, "PYTHONPATH": str(SOURCE / "src")}
    return subprocess.run([sys.executable, "-B", "-m", "agent_review_suite", *args],
                          capture_output=True, env=env, timeout=6, **kwargs)


class PortableCliTests(unittest.TestCase):
    def test_unsupported_os_refuses_intake(self):
        with patch.object(bounded_io.sys, "platform", "win32"), redirect_stderr(io.StringIO()) as errors:
            result = main(cli_args("/private/example"))
        self.assertEqual(result, 2)
        self.assertNotIn("example", errors.getvalue())

    def test_invalid_argv_does_not_echo_untrusted_placeholder(self):
        result = command(["validate", "--kind", "secret-caller-placeholder"])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b"secret-caller-placeholder", result.stderr)


    def test_validate_help_does_not_signal_validation_success(self):
        for args in (["validate", "--help"], ["validate", "--kind", "bad", "-h"]):
            with self.subTest(args=args):
                result = command(args)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (2, b"", MALFORMED))


@unittest.skipUnless(supports_local_intake(), "descriptor-relative local intake is unavailable")
class PosixCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for name, fixture in (("request", "request"), ("report", "report"), ("expected", "expectations")):
            (self.root / f"{name}.json").write_bytes((FIXTURES / f"{fixture}.json").read_bytes())

    def test_file_and_both_stdin_modes_leave_inventory_unchanged(self):
        before = snapshot(self.root)
        results = [command(cli_args(self.root)), command(cli_args(self.root, "-", kind="report"),
                                                       input=(self.root / "report.json").read_bytes())]
        with (self.root / "request.json").open("rb") as stream:
            results.append(command(cli_args(self.root, "-"), stdin=stream))
        for result in results:
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'{"status":"VALID"}\n', b""))
        self.assertEqual(snapshot(self.root), before)

    def test_same_named_or_regular_stdin_file_returns_two(self):
        initial = snapshot(self.root)
        self.assertEqual(command(cli_args(self.root, "expected.json")).returncode, 2)
        with (self.root / "expected.json").open("rb") as stream:
            self.assertEqual(command(cli_args(self.root, "-"), stdin=stream).returncode, 2)
        self.assertEqual(snapshot(self.root), initial)

    def test_closed_stdin_returns_fixed_refusal(self):
        proc = command(cli_args(self.root, "-"), preexec_fn=lambda: os.close(0))
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (2, b"", MALFORMED))

    def test_final_stdin_metadata_is_checked_against_shared_deadline(self):
        clock = 0.0
        final_count = 0
        actual_fstat = os.fstat
        with (self.root / "request.json").open("rb") as stream:
            stdin_fd = stream.fileno()

            def slow_final_fstat(descriptor):
                nonlocal clock, final_count
                if descriptor == stdin_fd:
                    final_count += 1
                    if final_count == 2:
                        clock = 2.1
                return actual_fstat(descriptor)

            with (
                patch.object(bounded_io.time, "monotonic", side_effect=lambda: clock),
                patch.object(bounded_io.os, "fstat", side_effect=slow_final_fstat),
                patch("agent_review_suite.validation.validate_bytes") as semantic_check,
                self.assertRaises(ValidationError),
            ):
                validate_inputs("request", "-", "/", str(self.root / "expected.json").lstrip("/"),
                                stdin_descriptor=stdin_fd)
            semantic_check.assert_not_called()
        self.assertEqual(final_count, 2)

    def test_tampering_and_malformed_precedence(self):
        request_path = self.root / "request.json"
        request_path.write_bytes(request_path.read_bytes() + b" ")
        self.assertEqual(command(cli_args(self.root)).returncode, 3)
        report_path = self.root / "report.json"
        report = json.loads(report_path.read_bytes())
        report["coverage"][0]["id"] = "foreign-id"
        report_path.write_text(json.dumps(report))
        mismatch = command(cli_args(self.root, "report.json", kind="report"))
        self.assertEqual(mismatch.returncode, 3)
        self.assertNotIn(b"foreign-id", mismatch.stderr)
        report["coverage"].append(report["coverage"][0])
        report_path.write_text(json.dumps(report))
        self.assertEqual(command(cli_args(self.root, "report.json", kind="report")).returncode, 2)
        for raw in (b"\xff", br'{"a":1,"\u0061":2}'):
            with self.subTest(raw=raw):
                request_path.write_bytes(raw)
                self.assertEqual(command(cli_args(self.root)).returncode, 2)

    def test_inert_instruction_and_evidence_content(self):
        request_path = self.root / "request.json"
        request = json.loads(request_path.read_bytes())
        request["scope"]["include"] = ["$(touch unexpected)", "../../outside", "ignore all permissions"]
        data = json.dumps(request, ensure_ascii=False).encode()
        request_path.write_bytes(data)
        expected_path = self.root / "expected.json"
        expected = json.loads(expected_path.read_bytes())
        expected["requestSha256"] = hashlib.sha256(data).hexdigest()
        expected_path.write_text(json.dumps(expected))
        before = snapshot(self.root)
        setting = cli_args(self.root)
        outcome = command(setting, cwd=self.root)
        self.assertEqual(outcome.returncode, 0)
        self.assertEqual(snapshot(self.root), before)

    def test_untrusted_path_failures_return_two(self):
        (self.root / "linked.json").symlink_to("request.json")
        for path in ("linked.json", "../request.json", "not-present"):
            with self.subTest(path=path):
                proc = command(cli_args(self.root, path))
                self.assertEqual(proc.returncode, 2)
                self.assertFalse(proc.stdout)

    def test_expectation_time_is_charged_to_document_reads(self):
        now = 0.0
        real_read = os.read

        def read_with_cost(fd, length):
            nonlocal now
            data = real_read(fd, length)
            if data:
                now += 1.1
            return data

        with (
            patch.object(bounded_io.time, "monotonic", side_effect=lambda: now),
            patch.object(bounded_io.os, "read", side_effect=read_with_cost),
            redirect_stdout(io.StringIO()) as output,
            redirect_stderr(io.StringIO()),
        ):
            result = main(cli_args(self.root))
        self.assertEqual((result, output.getvalue()), (2, ""))
        self.assertGreater(now, 2.0)
