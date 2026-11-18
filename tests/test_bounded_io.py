"""Exercise local descriptor intake on the actual platform primitives."""

from __future__ import annotations

import os
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_review_suite import bounded_io
from agent_review_suite.bounded_io import open_local_files, read_stdin, supports_local_intake
from agent_review_suite.contracts import MAX_DOCUMENT_BYTES, ValidationError


@unittest.skipUnless(supports_local_intake(), "descriptor-relative local intake is unavailable")
class FileIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def read(self, path, root=None):
        with open_local_files(str(root or self.root), time.monotonic() + 2) as files:
            return files.read(path)

    def test_exact_size_and_first_rejected_size(self):
        nested = self.root / "nested"
        nested.mkdir()
        path = nested / "input"
        data = b"x" * MAX_DOCUMENT_BYTES
        path.write_bytes(data)
        read = self.read("nested/input")
        self.assertEqual(read.data, data)
        self.assertEqual(read.identity, (path.stat().st_dev, path.stat().st_ino))
        path.write_bytes(data + b"x")
        with self.assertRaises(ValidationError):
            self.read("nested/input")

    def test_refuses_path_aliases_and_linked_ancestors(self):
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "actual").write_bytes(b"{}")
        (self.root / "dir-link").symlink_to("nested", target_is_directory=True)
        (self.root / "leaf-link").symlink_to("nested/actual")
        for path in (
            "/nested/actual", "../nested/actual", "nested/../nested/actual",
            "nested//actual", "nested/./actual", "nested/", "", "nested\\actual",
            "nested:actual", "nested/\0", "dir-link/actual", "leaf-link",
        ):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                self.read(path)
        for root in (self.root / "dir-link", Path("relative")):
            with self.subTest(root=root), self.assertRaises(ValidationError):
                self.read("actual", root)

    def test_refuses_hard_links_named_pipes_and_directories(self):
        path = self.root / "input"
        path.write_bytes(b"{}")
        os.link(path, self.root / "hard")
        os.mkfifo(self.root / "named-pipe")
        (self.root / "directory").mkdir()
        for name in ("input", "hard", "named-pipe", "directory"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.read(name)

    def test_repeated_identity_refused_within_one_root_operation(self):
        (self.root / "input").write_bytes(b"file")
        with open_local_files(str(self.root), time.monotonic() + 2) as files:
            self.assertEqual(files.read("input").data, b"file")
            with self.assertRaises(ValidationError):
                files.read("input")

    def test_absolute_root_can_contain_colon_or_backslash(self):
        for name in ("with:colon", "with\\backslash"):
            with self.subTest(name=name):
                root = self.root / name
                root.mkdir()
                (root / "input").write_bytes(b"file")
                self.assertEqual(self.read("input", root).data, b"file")

    def test_refuses_real_device(self):
        with self.assertRaises(ValidationError):
            self.read("null", Path("/dev"))

    def test_detects_leaf_replacement_after_open(self):
        path = self.root / "input"
        path.write_bytes(b"old")
        replacement = self.root / "replacement"
        replacement.write_bytes(b"new")
        read = os.read

        def replace_after_read(fd, count):
            data = read(fd, count)
            if data and replacement.exists():
                replacement.replace(path)
            return data

        with patch.object(bounded_io.os, "read", side_effect=replace_after_read), self.assertRaises(ValidationError):
            self.read("input")
        self.assertEqual(path.read_bytes(), b"new")

    def test_detects_changed_file_and_moved_parent(self):
        folder = self.root / "folder"
        folder.mkdir()
        path = folder / "input"
        path.write_bytes(b"first")
        real_read = os.read

        def grow_file(fd, count):
            chunk = real_read(fd, count)
            if chunk and path.stat().st_size == 5:
                with path.open("ab") as handle:
                    handle.write(b"second")
            return chunk

        with patch.object(bounded_io.os, "read", side_effect=grow_file), self.assertRaises(ValidationError):
            self.read("folder/input")
        moved = self.root / "moved"

        def replace_parent(fd, count):
            chunk = real_read(fd, count)
            if not moved.exists():
                folder.rename(moved)
                folder.mkdir()
            return chunk

        with patch.object(bounded_io.os, "read", side_effect=replace_parent), self.assertRaises(ValidationError):
            self.read("folder/input")


@unittest.skipUnless(supports_local_intake(), "descriptor-relative local intake is unavailable")
class StdinIntakeTests(unittest.TestCase):
    def open_pipe(self):
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        return reader, writer

    def test_regular_descriptor_reads_from_current_offset(self):
        with tempfile.NamedTemporaryFile() as source:
            source.write(b"prefix{}")
            source.flush()
            os.lseek(source.fileno(), 6, os.SEEK_SET)
            read = read_stdin(source.fileno(), time.monotonic() + 1)
        self.assertEqual(read.data, b"{}")

    def test_multiple_pipe_reads_eof_and_mode_restoration(self):
        for initial_mode in (True, False):
            with self.subTest(initial_mode=initial_mode):
                reader, writer = self.open_pipe()
                os.set_blocking(reader, initial_mode)
                os.write(writer, b"abcdef")
                os.close(writer)
                with patch.object(bounded_io, "_READ_SIZE", 2):
                    data = read_stdin(reader, time.monotonic() + 1).data
                self.assertEqual(data, b"abcdef")
                self.assertEqual(os.get_blocking(reader), initial_mode)

    def test_pipe_uses_one_inclusive_byte_cap(self):
        for data, accepted in ((b"123456", True), (b"1234567", False)):
            with self.subTest(data=data), patch.object(bounded_io, "MAX_DOCUMENT_BYTES", 6):
                reader, writer = self.open_pipe()
                os.write(writer, data)
                os.close(writer)
                if accepted:
                    self.assertEqual(read_stdin(reader, time.monotonic() + 1).data, data)
                else:
                    with self.assertRaises(ValidationError):
                        read_stdin(reader, time.monotonic() + 1)
                self.assertTrue(os.get_blocking(reader))

    def test_waits_for_eof_after_valid_bytes_and_restores_mode(self):
        reader, writer = self.open_pipe()
        self.addCleanup(os.close, writer)
        os.write(writer, b"{}")
        before = time.monotonic()
        with self.assertRaises(ValidationError):
            read_stdin(reader, before + 0.025)
        self.assertGreaterEqual(time.monotonic() - before, 0.02)
        self.assertTrue(os.get_blocking(reader))

    def test_restores_pipe_mode_after_read_error(self):
        reader, writer = self.open_pipe()
        self.addCleanup(os.close, writer)
        os.write(writer, b"{}")
        with patch.object(bounded_io.os, "read", side_effect=OSError("read failed")), self.assertRaises(ValidationError):
            read_stdin(reader, time.monotonic() + 1)
        self.assertTrue(os.get_blocking(reader))

    def test_socket_and_device_descriptors_are_refused(self):
        left, right = socket.socketpair()
        with left, right, self.assertRaises(ValidationError):
            read_stdin(left.fileno(), time.monotonic() + 1)
        with open(os.devnull, "rb") as device, self.assertRaises(ValidationError):
            read_stdin(device.fileno(), time.monotonic() + 1)
