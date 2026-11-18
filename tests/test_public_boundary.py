"""Regressions for exact consumer assets and private-content leaks."""

import importlib.util
import io
import json
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layout(checker, archive_name):
    if archive_name.endswith(".whl"):
        return "agent_review_suite-0.1.0.data/data/share/agent-review-suite/", checker.REQUIRED_ASSETS
    if archive_name.endswith(".tar.gz"):
        return "agent_review_suite-0.1.0/", (
            *checker.REQUIRED_ASSETS, *checker.SDIST_HELPERS, *(f"tests/fixtures/{name}" for name in checker.FIXTURES)
        )
    return "", checker.REQUIRED_ASSETS


def synthetic_archive(checker, path, *, omit=None, extras=()):
    prefix, required = layout(checker, path.name)
    names = [prefix + name for name in required if name != omit] + list(extras)
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "w:gz") as archive:
            for name in names:
                item = tarfile.TarInfo(name)
                item.size = 6
                archive.addfile(item, io.BytesIO(b"public"))
    else:
        with zipfile.ZipFile(path, "w") as archive:
            for name in names:
                archive.writestr(name, "public")


class PublicBoundaryTests(unittest.TestCase):
    def test_current_repository_contract(self):
        checker = load("ars_repo_check", "tools/check_repository.py")
        self.assertEqual(checker.check(), [])
        import agent_review_suite
        origin = Path(agent_review_suite.__file__).resolve()
        self.assertTrue(origin.is_relative_to(ROOT / "src"), origin)
        print(f"Source import: {origin}")

    def test_workflow_pin_syntax_and_seeded_private_source(self):
        checker = load("ars_workflow_check", "tools/check_repository.py")
        workflow = ROOT / ".github/workflows/ci.yml"
        if not workflow.is_file():
            self.skipTest("the sdist omits the hosted CI workflow")
        text = workflow.read_text()
        self.assertEqual(checker.action_reference_errors(text), [])
        spaced = text.replace("actions/checkout@", "actions/checkout @", 1)
        self.assertNotEqual(spaced, text)
        self.assertIn("invalid pinned action reference", checker.action_reference_errors(spaced)[0])
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "checkout"
            shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns(
                ".git", ".alk", ".venv", ".ruff_cache", ".mypy_cache", "*.egg-info",
                "__pycache__", "build", "dist", "tasks", "work", "events.jsonl",
            ))
            label = "private-marker-for-seeded-ci-test"
            private_file = Path(directory) / "labels.json"
            private_file.write_text(json.dumps([label]))
            target = copied / ".github/workflows/ci.yml"
            with target.open("a") as handle:
                handle.write(f"\n# {label}\n")
            argv = [sys.executable, "-B", str(copied / "tools/check_repository.py"), "--private-labels"]
            result = subprocess.run([*argv, str(private_file)], capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"private label in public asset: .github", result.stdout)
            for payload in (Path(directory) / "missing.json", Path(directory) / "empty.json"):
                if payload.name == "empty.json":
                    payload.write_text("[]")
                outcome = subprocess.run([*argv, str(payload)], capture_output=True, timeout=15)
                self.assertNotEqual(outcome.returncode, 0)
                self.assertIn(b"nonempty bounded private label list", outcome.stderr)

    def test_required_assets_and_fixture_placement(self):
        checker = load("ars_release_layout", "tools/release/check_dist.py")
        for archive_name in (
            "agent_review_suite-0.1.0-py3-none-any.whl",
            "agent_review_suite-0.1.0.tar.gz",
            "agent-review-suite-plugin.zip",
        ):
            with self.subTest(archive=archive_name), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / archive_name
                _, required = layout(checker, archive_name)
                synthetic_archive(checker, archive)
                self.assertEqual(checker.inspect(archive)["errors"], [])
                for member in required:
                    if member.startswith(("schemas/", "docs/", "tests/fixtures/", "tools/")):
                        synthetic_archive(checker, archive, omit=member)
                        self.assertTrue(any(item.endswith(member) for item in checker.inspect(archive)["errors"]))
                synthetic_archive(checker, archive, extras=("unexpected/request.json",))
                self.assertTrue(checker.inspect(archive)["errors"])

    def test_unlabeled_prohibited_members_and_types(self):
        checker = load("ars_dist_check", "tools/release/check_dist.py")
        invalid = (
            "../secret", "/root/key", "x/.alk/review.json", "x/tasks/plan.json",
            "x\\.env", "x/.ENV.local", "x/release/plan.json", "x/.ruff_cache/data",
            "bad//alias", "bad/./alias", "bad/trailing. ", "x/events.jsonl",
        )
        for name in invalid:
            with self.subTest(name=name):
                self.assertTrue(checker.unsafe(name))
        self.assertFalse(checker.unsafe("agent_review_suite-0.1.0/tools/release/check_dist.py"))
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "plugin.zip"
            slash_names = tuple(name for name in invalid if "\\" not in name)
            synthetic_archive(checker, plugin, extras=slash_names)
            errors = checker.inspect(plugin)["errors"]
            for name in slash_names:
                self.assertIn(name, errors)

            # Write the raw member name despite ZipInfo's platform separator conversion.
            raw_name = "assets\\alias.txt"
            node = zipfile.ZipInfo("assets/alias.txt")
            node.filename = raw_name
            with zipfile.ZipFile(plugin, "a") as archive:
                archive.writestr(node, b"x")
            with zipfile.ZipFile(plugin) as archive:
                member = archive.infolist()[-1]
                self.assertEqual(member.orig_filename, raw_name)
            self.assertIn(member.filename, checker.inspect(plugin)["errors"])
            synthetic_archive(checker, plugin, extras=("README.RU.md",))
            self.assertIn("duplicate or aliased members", checker.inspect(plugin)["errors"])
            synthetic_archive(checker, plugin)
            with zipfile.ZipFile(plugin, "a") as archive:
                node = zipfile.ZipInfo("extra-device")
                node.external_attr = (stat.S_IFCHR | 0o600) << 16
                archive.writestr(node, b"")
            self.assertIn("extra-device", checker.inspect(plugin)["errors"])
            sdist = Path(directory) / "agent_review_suite-0.1.0.tar.gz"
            with tarfile.open(sdist, "w:gz") as archive:
                member = tarfile.TarInfo("agent_review_suite-0.1.0/linked")
                member.type = tarfile.LNKTYPE
                member.linkname = "outside"
                archive.addfile(member)
            self.assertIn(member.name, checker.inspect(sdist)["errors"])

    def test_private_label_scan_includes_public_document_and_archive(self):
        checker = load("ars_label_check", "tools/check_repository.py")
        archive_check = load("ars_archive_label_check", "tools/release/check_dist.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs/example.md").write_text("private-example-label")
            self.assertEqual(checker.private_label_errors(root, ()), [])
            self.assertEqual(len(checker.private_label_errors(root, ("private-example-label",))), 1)
            destination = root / "plugin.zip"
            synthetic_archive(archive_check, destination)
            with zipfile.ZipFile(destination, "a") as archive:
                archive.writestr("docs/example.md", "private-example-label")
            self.assertEqual(archive_check.inspect(destination)["errors"], [])
            self.assertEqual(archive_check.inspect(destination, ("private-example-label",))["errors"],
                             ["private label: docs/example.md"])

    def test_qualification_requires_explicit_mode_and_available_labels(self):
        archive_check = load("ars_required_scan_mode", "tools/release/check_dist.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / "plugin.zip"
            synthetic_archive(archive_check, plugin)
            missing = root / "missing.json"
            unreadable = root / "directory"
            unreadable.mkdir()
            malformed = root / "bad.json"
            malformed.write_text("not JSON")
            empty = root / "empty.json"
            empty.write_text("[]")
            values = root / "labels.json"
            values.write_text(json.dumps(["not-present-" + "in-public-assets"]))
            for script, extra in (("tools/check_repository.py", []), ("tools/release/check_dist.py", [str(plugin)])):
                base = [sys.executable, "-B", str(ROOT / script), *extra]
                for label_args in ([], *(["--private-labels", str(path)] for path in (missing, unreadable, malformed, empty))):
                    with self.subTest(script=script, label_args=label_args):
                        result = subprocess.run([*base, *label_args], capture_output=True, timeout=15)
                        self.assertNotEqual(result.returncode, 0)
                for mode in (["--private-labels", str(values)], ["--public-ci"]):
                    result = subprocess.run([*base, *mode], capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_private_label_paths_mixed_bytes_and_unicode_aliases(self):
        source_check = load("ars_mixed_source", "tools/check_repository.py")
        checker = load("ars_mixed_archives", "tools/release/check_dist.py")
        label = "seeded-route-label"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / f"{label}.md").write_bytes(b"public")
            (docs / "mixed.bin").write_bytes(b"\xff" + label.encode())
            self.assertEqual(len(source_check.private_label_errors(root, (label,))), 2)
            for archive_name in (
                "agent_review_suite-0.1.0-py3-none-any.whl",
                "agent_review_suite-0.1.0.tar.gz",
                "agent-review-suite-plugin.zip",
            ):
                with self.subTest(archive=archive_name):
                    archive = root / archive_name
                    prefix, _ = layout(checker, archive_name)
                    composed = prefix + "docs/café.txt"
                    decomposed = prefix + "docs/cafe\u0301.txt"
                    path_label = prefix + f"docs/{label}.txt"
                    mixed = prefix + "docs/mixed.bin"
                    synthetic_archive(checker, archive, extras=(composed, decomposed, path_label))
                    payload = b"\xff" + label.encode()
                    if archive_name.endswith(".tar.gz"):
                        copy = root / "recreated.tar.gz"
                        with tarfile.open(archive, "r:gz") as old, tarfile.open(copy, "w:gz") as temporary:
                            for item in old.getmembers():
                                temporary.addfile(item, old.extractfile(item))
                            info = tarfile.TarInfo(mixed)
                            info.size = len(payload)
                            temporary.addfile(info, io.BytesIO(payload))
                        copy.replace(archive)
                    else:
                        with zipfile.ZipFile(archive, "a") as package:
                            package.writestr(mixed, payload)
                    errors = checker.inspect(archive, (label,))["errors"]
                    self.assertIn("duplicate or aliased members", errors)
                    self.assertIn(f"private label in member name: {path_label}", errors)
                    self.assertIn(f"private label: {mixed}", errors)

    def test_plugin_inventory_includes_schemas_and_excludes_private_files(self):
        builder = load("ars_plugin_build", "tools/release/build_plugin.py")
        paths = [p.relative_to(ROOT).as_posix() for p in builder.members(ROOT)]
        self.assertIn("schemas/review-request.v1.schema.json", paths)
        self.assertIn("schemas/review-report.v1.schema.json", paths)
        self.assertIn("schemas/review-expectations.v1.schema.json", paths)
        self.assertFalse(any(name.startswith((".alk/", "tasks/", "work/", "tests/")) for name in paths))

    def test_plugin_refuses_asset_symlink(self):
        if sys.platform == "win32":
            self.skipTest("symbolic link creation requires Windows privilege")
        builder = load("ars_plugin_links", "tools/release/build_plugin.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in builder.PUBLIC_FILES:
                (root / name).write_text("public")
            (root / "docs").mkdir()
            (root / "docs/outside").symlink_to(root / "README.md")
            with self.assertRaises(ValueError):
                builder.members(root)
