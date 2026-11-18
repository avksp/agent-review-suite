"""Combine local intake with the caller-neutral validation API."""

from __future__ import annotations

import time

from agent_review_suite.bounded_io import open_local_files, read_stdin
from agent_review_suite.contracts import ValidationError, validate_bytes

_READ_SECONDS = 2.0


def validate_inputs(
    kind: str, input_path: str, root: str, expectations_path: str, *, stdin_descriptor: int
) -> dict[str, object]:
    """Validate two bounded, separately named inputs under one read deadline."""
    deadline = time.monotonic() + _READ_SECONDS
    with open_local_files(root, deadline) as files:
        expected = files.read(expectations_path)
        if input_path == "-":
            document = read_stdin(stdin_descriptor, deadline)
        else:
            document = files.read(input_path)
        if document.identity == expected.identity:
            raise ValidationError()
        files.verify_root()
    if time.monotonic() >= deadline:
        raise ValidationError()
    return validate_bytes(kind, document.data, expected.data)
