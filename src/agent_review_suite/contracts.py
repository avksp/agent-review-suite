"""Decode and validate caller-neutral ARS v1 documents without I/O."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

MAX_DOCUMENT_BYTES = 262_144
MAX_DEPTH = 32
MAX_FINDINGS = 1_000
MAX_EVIDENCE = 2_000
MAX_TEXT_LENGTH = 4_096
MAX_USAGE = (1 << 53) - 1

FailureKind = Literal["malformed", "binding-mismatch"]
_IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{1,128}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SURROGATE = re.compile(r"[\ud800-\udfff]")
_SHARED = {"schemaVersion", "requestId", "assignmentId", "source", "packs"}
_REQUEST = _SHARED | {"scope", "role", "requiredCoverage"}
_EXPECTATIONS = _SHARED | {"requestSha256", "requiredCoverage"}
_REPORT = _SHARED | {"requestSha256", "executionStatus", "coverage", "findings", "evidence", "usage", "limitations"}
_REPRESENTATIONS = {"git-diff-bytes-v1", "source-bundle-bytes-v1"}
_COVERAGE_STATUSES = {"CHECKED", "NOT_CHECKED"}
_EXECUTION_STATUSES = {"COMPLETE", "INCOMPLETE", "FAILED"}
_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_CERTAINTIES = {"STATIC", "OBSERVED", "UNCONFIRMED"}
_USAGE_KEYS = {"inputTokens", "outputTokens", "invocations", "elapsedMs"}


class ValidationError(ValueError):
    """A malformed document or a disagreement with trusted expectations."""

    def __init__(self, kind: FailureKind = "malformed") -> None:
        self.kind = kind
        super().__init__(kind)


@dataclass(frozen=True)
class _Bindings:
    request_id: str
    assignment_id: str
    source: dict[str, object]
    packs: frozenset[tuple[str, str, str]]


def decode_json(data: bytes) -> object:
    """Read a bounded UTF-8 JSON frame with unambiguous keys and scalars."""
    if not isinstance(data, bytes) or len(data) > MAX_DOCUMENT_BYTES:
        raise ValidationError()
    try:
        text = data.decode("utf-8")
        _check_depth(text)
        value: object = json.loads(
            text,
            object_pairs_hook=_unique_members,
            parse_constant=_reject_constant,
            parse_float=_finite_number,
        )
    except (ValueError, RecursionError) as exc:
        raise ValidationError() from exc
    _check_unicode(value)
    return value


def _check_depth(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise ValidationError()
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ValidationError()


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError()
        result[key] = value
    return result


def _reject_constant(_value: str) -> float:
    raise ValidationError()


def _finite_number(value: str) -> Decimal:
    significand = re.split("[eE]", value, maxsplit=1)[0]
    if all(character in "-0." for character in significand):
        return Decimal(0)
    if not math.isfinite(float(value)):
        raise ValidationError()
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError() from exc


def _check_unicode(value: object) -> None:
    if isinstance(value, str):
        if _SURROGATE.search(value):
            raise ValidationError()
    elif isinstance(value, list):
        for item in value:
            _check_unicode(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_unicode(key)
            _check_unicode(item)


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValidationError()
    return cast("dict[str, object]", value)


def _array(value: object, maximum: int | None = None) -> list[object]:
    if not isinstance(value, list) or (maximum is not None and len(value) > maximum):
        raise ValidationError()
    return cast("list[object]", value)


def _text(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH:
        raise ValidationError()
    return value


def _id(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValidationError()
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValidationError()
    return value


def _choice(value: object, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValidationError()
    return value


def _insert_unique(seen: set[str], value: str) -> None:
    if value in seen:
        raise ValidationError()
    seen.add(value)


def _id_set(value: object, *, required: bool = False, maximum: int | None = None) -> set[str]:
    result: set[str] = set()
    for item in _array(value, maximum):
        _insert_unique(result, _id(item))
    if required and not result:
        raise ValidationError()
    return result


def _text_list(value: object) -> None:
    for item in _array(value):
        _text(item)


def _bindings(document: dict[str, object], version: str) -> _Bindings:
    if document["schemaVersion"] != version:
        raise ValidationError()
    source = _object(document["source"], {"id", "baseId", "representation", "sha256", "baseSha256"})
    _id(source["id"])
    _id(source["baseId"])
    _choice(source["representation"], _REPRESENTATIONS)
    _digest(source["sha256"])
    _digest(source["baseSha256"])
    pack_ids: set[str] = set()
    packs: set[tuple[str, str, str]] = set()
    for value in _array(document["packs"]):
        pack = _object(value, {"id", "version", "sha256"})
        pack_id = _id(pack["id"])
        _insert_unique(pack_ids, pack_id)
        packs.add((pack_id, _text(pack["version"]), _digest(pack["sha256"])))
    return _Bindings(_id(document["requestId"]), _id(document["assignmentId"]), source, frozenset(packs))


def _request_coverage(document: dict[str, object]) -> set[str]:
    scope = _object(document["scope"], {"include", "exclude"})
    _text_list(scope["include"])
    _text_list(scope["exclude"])
    _text(document["role"])
    return _id_set(document["requiredCoverage"], required=True)


def _report_coverage(document: dict[str, object]) -> set[str]:
    execution = _choice(document["executionStatus"], _EXECUTION_STATUSES)
    coverage: set[str] = set()
    unchecked = False
    for value in _array(document["coverage"]):
        row = _object(value, {"id", "status"})
        _insert_unique(coverage, _id(row["id"]))
        if _choice(row["status"], _COVERAGE_STATUSES) == "NOT_CHECKED":
            unchecked = True
    if (execution == "COMPLETE" and unchecked) or (execution == "INCOMPLETE" and not unchecked):
        raise ValidationError()
    return coverage


def _report_details(document: dict[str, object]) -> None:
    evidence: set[str] = set()
    for value in _array(document["evidence"], MAX_EVIDENCE):
        row = _object(value, {"id", "sha256", "description"})
        _insert_unique(evidence, _id(row["id"]))
        _digest(row["sha256"])
        _text(row["description"])
    finding_ids: set[str] = set()
    reference_count = 0
    for value in _array(document["findings"], MAX_FINDINGS):
        row = _object(value, {"id", "severity", "certainty", "summary", "minimumFix", "verification", "evidenceIds"})
        _insert_unique(finding_ids, _id(row["id"]))
        _choice(row["severity"], _SEVERITIES)
        _choice(row["certainty"], _CERTAINTIES)
        for field in ("summary", "minimumFix", "verification"):
            _text(row[field])
        references = _id_set(row["evidenceIds"], maximum=MAX_EVIDENCE)
        reference_count += len(references)
        if reference_count > MAX_EVIDENCE or not references <= evidence:
            raise ValidationError()
    usage = _object(document["usage"], _USAGE_KEYS)
    for field, value in usage.items():
        usage[field] = _usage_integer(value)
    _text_list(document["limitations"])


def _usage_integer(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is int and 0 <= value <= MAX_USAGE:
        return value
    if isinstance(value, Decimal) and 0 <= value <= MAX_USAGE and value == value.to_integral_value():
        return int(value)
    raise ValidationError()


def validate_bytes(kind: str, document: bytes, expectations: bytes) -> dict[str, object]:
    """Return a valid v1 document whose bindings match trusted expectations."""
    if kind == "request":
        parsed = _object(decode_json(document), _REQUEST)
        actual = _bindings(parsed, "ars.review-request.v1")
        coverage = _request_coverage(parsed)
        request_digest = hashlib.sha256(document).hexdigest()
    elif kind == "report":
        parsed = _object(decode_json(document), _REPORT)
        actual = _bindings(parsed, "ars.review-report.v1")
        coverage = _report_coverage(parsed)
        _report_details(parsed)
        request_digest = _digest(parsed["requestSha256"])
    else:
        raise ValidationError()

    expected = _object(decode_json(expectations), _EXPECTATIONS)
    trusted = _bindings(expected, "ars.review-expectations.v1")
    trusted_coverage = _id_set(expected["requiredCoverage"], required=True)
    trusted_digest = _digest(expected["requestSha256"])
    if actual != trusted or coverage != trusted_coverage or request_digest != trusted_digest:
        raise ValidationError("binding-mismatch")
    return parsed
