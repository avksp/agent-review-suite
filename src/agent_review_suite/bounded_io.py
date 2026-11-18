"""Read bounded inputs from a caller-controlled local staging directory."""

from __future__ import annotations

import os
import selectors
import stat
import sys
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

from agent_review_suite.contracts import MAX_DOCUMENT_BYTES, ValidationError

_READ_SIZE = 65_536


@dataclass(frozen=True)
class ReadInput:
    """Bytes and the identity of the descriptor that supplied them."""

    data: bytes
    identity: tuple[int, int]


@dataclass(frozen=True)
class _Directory:
    parent: int
    name: str
    descriptor: int
    identity: tuple[int, int]


def supports_local_intake() -> bool:
    """Check whether the descriptor-relative intake primitives are available."""
    return (
        sys.platform in {"darwin", "linux"}
        and all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
        and hasattr(os, "get_blocking")
        and hasattr(os, "set_blocking")
    )


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValidationError()
    return remaining


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _signature(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _components(name: str, forbidden: str = "\\:\0") -> list[str]:
    parts = name.split("/")
    if any(part in {"", ".", ".."} or any(char in part for char in forbidden) for part in parts):
        raise ValidationError()
    return parts


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK


def _walk_directories(
    stack: ExitStack, parent: int, names: list[str], deadline: float
) -> tuple[int, list[_Directory]]:
    chain: list[_Directory] = []
    for name in names:
        _remaining(deadline)
        descriptor = os.open(name, _directory_flags(), dir_fd=parent)
        stack.callback(os.close, descriptor)
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise ValidationError()
        chain.append(_Directory(parent, name, descriptor, _identity(opened)))
        parent = descriptor
    return parent, chain


def _verify_directories(chain: list[_Directory], deadline: float) -> None:
    for directory in chain:
        _remaining(deadline)
        named = os.stat(directory.name, dir_fd=directory.parent, follow_symlinks=False)
        opened = os.fstat(directory.descriptor)
        if not stat.S_ISDIR(named.st_mode) or _identity(named) != directory.identity:
            raise ValidationError()
        if not stat.S_ISDIR(opened.st_mode) or _identity(opened) != directory.identity:
            raise ValidationError()


def _regular(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 <= info.st_size <= MAX_DOCUMENT_BYTES:
        raise ValidationError()


def _append_read(buffer: bytearray, descriptor: int, deadline: float) -> bool:
    _remaining(deadline)
    chunk = os.read(descriptor, min(_READ_SIZE, MAX_DOCUMENT_BYTES + 1 - len(buffer)))
    _remaining(deadline)
    buffer.extend(chunk)
    if len(buffer) > MAX_DOCUMENT_BYTES:
        raise ValidationError()
    return bool(chunk)


def _read_regular(descriptor: int, initial: os.stat_result, offset: int, deadline: float) -> bytes:
    data = bytearray()
    while _append_read(data, descriptor, deadline):
        pass
    final = os.fstat(descriptor)
    _remaining(deadline)
    if _signature(initial) != _signature(final) or len(data) != initial.st_size - offset:
        raise ValidationError()
    return bytes(data)


class LocalFiles:
    """Reuse a pinned root for independently named files in one operation."""

    def __init__(self, descriptor: int, chain: list[_Directory], deadline: float) -> None:
        self._descriptor = descriptor
        self._chain = chain
        self._deadline = deadline
        self._read_identities: set[tuple[int, int]] = set()

    def verify_root(self) -> None:
        _verify_directories(self._chain, self._deadline)

    def read(self, path: str) -> ReadInput:
        """Refuse nonregular, linked, oversized, or observably changed inputs."""
        parts = _components(path)
        with ExitStack() as stack:
            parent, chain = _walk_directories(stack, self._descriptor, parts[:-1], self._deadline)
            name = parts[-1]
            _remaining(self._deadline)
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            _regular(before)
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            stack.callback(os.close, descriptor)
            initial = os.fstat(descriptor)
            _regular(initial)
            identity = _identity(initial)
            if _signature(before) != _signature(initial) or identity in self._read_identities:
                raise ValidationError()
            data = _read_regular(descriptor, initial, 0, self._deadline)
            final = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if _signature(final) != _signature(initial):
                raise ValidationError()
            _verify_directories(self._chain + chain, self._deadline)
            _remaining(self._deadline)
            self._read_identities.add(identity)
            return ReadInput(data, identity)


@contextmanager
def open_local_files(root: str, deadline: float) -> Iterator[LocalFiles]:
    """Pin the root without resolving untrusted links or dot components."""
    if not supports_local_intake() or not root.startswith("/"):
        raise ValidationError()
    parts = [] if root == "/" else _components(root[1:], forbidden="\0")
    try:
        with ExitStack() as stack:
            _remaining(deadline)
            anchor = os.open("/", _directory_flags())
            stack.callback(os.close, anchor)
            descriptor, chain = _walk_directories(stack, anchor, parts, deadline)
            yield LocalFiles(descriptor, chain, deadline)
    except OSError as exc:
        raise ValidationError() from exc


def _read_pipe(descriptor: int, deadline: float) -> bytes:
    data = bytearray()
    was_blocking = os.get_blocking(descriptor)
    if was_blocking:
        os.set_blocking(descriptor, False)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(descriptor, selectors.EVENT_READ)
            while selector.select(_remaining(deadline)):
                try:
                    if not _append_read(data, descriptor, deadline):
                        return bytes(data)
                except BlockingIOError:
                    continue
        raise ValidationError()
    finally:
        if was_blocking:
            os.set_blocking(descriptor, True)


def read_stdin(descriptor: int, deadline: float) -> ReadInput:
    """Read an exclusively owned pipe or regular descriptor to EOF."""
    if not supports_local_intake():
        raise ValidationError()
    try:
        _remaining(deadline)
        initial = os.fstat(descriptor)
        if stat.S_ISREG(initial.st_mode):
            _regular(initial)
            offset = os.lseek(descriptor, 0, os.SEEK_CUR)
            data = _read_regular(descriptor, initial, offset, deadline)
        elif stat.S_ISFIFO(initial.st_mode):
            data = _read_pipe(descriptor, deadline)
        else:
            raise ValidationError()
        return ReadInput(data, _identity(initial))
    except OSError as exc:
        raise ValidationError() from exc
