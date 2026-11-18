"""Exercise the v1 wire limits, structural checks and trusted joins."""

from __future__ import annotations

import hashlib
import json
import unittest
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator, validators

from agent_review_suite.contracts import (
    MAX_DEPTH,
    MAX_DOCUMENT_BYTES,
    MAX_EVIDENCE,
    MAX_FINDINGS,
    MAX_TEXT_LENGTH,
    MAX_USAGE,
    ValidationError,
    decode_json,
    validate_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"


def encode(document):
    return json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def fixture(name):
    return (FIXTURES / f"{name}.json").read_bytes()


def initial(name):
    return json.loads(fixture(name))


def evidence_row(index):
    return {"id": f"E{index}", "sha256": "0" * 64, "description": ""}


def finding_row(index, refs=None):
    return {
        "id": f"F{index}",
        "severity": "MEDIUM",
        "certainty": "STATIC",
        "summary": "",
        "minimumFix": "",
        "verification": "",
        "evidenceIds": [] if refs is None else refs,
    }


class ContractTests(unittest.TestCase):
    def assert_refused(self, kind, raw, code="malformed", expected=None):
        if expected is None:
            expected = fixture("expectations")
        with self.assertRaises(ValidationError) as error:
            validate_bytes(kind, raw, expected)
        self.assertEqual(error.exception.kind, code)

    def test_minimal_fixtures_and_execution_states(self):
        request = validate_bytes("request", fixture("request"), fixture("expectations"))
        self.assertEqual(request, initial("request"))

        report = initial("report")
        for state, status in (
            ("COMPLETE", "CHECKED"),
            ("INCOMPLETE", "NOT_CHECKED"),
            ("FAILED", "NOT_CHECKED"),
        ):
            with self.subTest(state=state):
                report["executionStatus"] = state
                report["coverage"][0]["status"] = status
                report["usage"]["inputTokens"] = 0
                accepted = validate_bytes("report", encode(report), fixture("expectations"))
                self.assertEqual(accepted["executionStatus"], state)
                self.assertEqual(accepted["usage"]["inputTokens"], 0)
                self.assertIsNone(accepted["usage"]["outputTokens"])

    def test_exact_request_digest_uses_received_bytes(self):
        raw = fixture("request")
        changed = raw + b" "
        self.assert_refused("request", changed, "binding-mismatch")
        expected = initial("expectations")
        expected["requestSha256"] = hashlib.sha256(changed).hexdigest()
        self.assertEqual(validate_bytes("request", changed, encode(expected)), json.loads(raw))

    def test_foreign_ids_and_tampered_source_domains(self):
        for key in ("requestId", "assignmentId"):
            with self.subTest(key=key):
                report = initial("report")
                report[key] = "foreign"
                self.assert_refused("report", encode(report), "binding-mismatch")
        for key, replacement in (
            ("id", "stale-source"),
            ("baseId", "stale-base"),
            ("representation", "source-bundle-bytes-v1"),
            ("sha256", "a" * 64),
            ("baseSha256", "b" * 64),
        ):
            with self.subTest(key=key):
                report = initial("report")
                report["source"][key] = replacement
                self.assert_refused("report", encode(report), "binding-mismatch")
        report = initial("report")
        report["requestSha256"] = "f" * 64
        self.assert_refused("report", encode(report), "binding-mismatch")

    def test_pack_set_and_malformed_pack(self):
        first = {"id": "one", "version": "1", "sha256": "a" * 64}
        second = {"id": "two", "version": "2", "sha256": "b" * 64}
        expected = initial("expectations")
        expected["packs"] = [first, second]
        report = initial("report")
        report["packs"] = [second, first]
        self.assertEqual(validate_bytes("report", encode(report), encode(expected))["packs"], [second, first])
        for packs in ([first], [first, second, {"id": "three", "version": "1", "sha256": "c" * 64}],
                      [first, {**second, "version": "3"}], [first, {**second, "sha256": "d" * 64}]):
            with self.subTest(packs=packs):
                report["packs"] = packs
                self.assert_refused("report", encode(report), "binding-mismatch", encode(expected))
        report["packs"] = [first, {**second, "id": first["id"]}]
        self.assert_refused("report", encode(report), expected=encode(expected))

    def test_coverage_join_and_internal_precedence(self):
        report = initial("report")
        for ids in ([], ["substituted"], ["inspect-scope", "extra"]):
            with self.subTest(ids=ids):
                report["coverage"] = [{"id": item, "status": "CHECKED"} for item in ids]
                self.assert_refused("report", encode(report), "binding-mismatch")
        report["coverage"] = [{"id": "substituted", "status": "CHECKED"}] * 2
        self.assert_refused("report", encode(report))
        report["coverage"] = [{"id": "substituted", "status": "NOT_CHECKED"}]
        self.assert_refused("report", encode(report))
        report["coverage"][0]["status"] = "CHECKED"
        report["executionStatus"] = "INCOMPLETE"
        self.assert_refused("report", encode(report))
        request = initial("request")
        request["requiredCoverage"] = ["foreign"]
        raw = encode(request)
        expected = initial("expectations")
        expected["requestSha256"] = hashlib.sha256(raw).hexdigest()
        self.assert_refused("request", raw, "binding-mismatch", encode(expected))

    def test_closed_fields_and_version_at_every_boundary(self):
        for kind in ("request", "report"):
            for field in ("schemaVersion", "source", "requestId"):
                with self.subTest(kind=kind, field=field):
                    doc = initial(kind)
                    doc.pop(field)
                    self.assert_refused(kind, encode(doc))
            doc = initial(kind)
            doc["schemaVersion"] = f"ars.review-{kind}.v2"
            self.assert_refused(kind, encode(doc))
            doc = initial(kind)
            doc["source"]["authorized"] = True
            self.assert_refused(kind, encode(doc))
        expected = initial("expectations")
        expected["allow"] = True
        report = initial("report")
        report["requestId"] = "otherwise-mismatching"
        self.assert_refused("report", encode(report), expected=encode(expected))
        self.assert_refused("other", fixture("request"))

    def test_utf8_nesting_and_numeric_wire(self):
        cases = (
            b"\xff",
            b"\xef\xbb\xbf{}",
            b'{"x":1,"x":2}',
            br'{"a":1,"\u0061":2}',
            b'{"x":NaN}',
            b'{"x":Infinity}',
            b'{"x":-Infinity}',
            b'{"x":1e999}',
            br'{"x":"\ud800"}',
            br'{"\udfff":1}',
            b"{} {}",
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                decode_json(raw)
        self.assertEqual(decode_json(br'{"emoji":"\ud83d\ude42","quote":"\"[[["}'),
                         {"emoji": "🙂", "quote": '"[[['})
        exact = b"[" * MAX_DEPTH + b"0" + b"]" * MAX_DEPTH
        decode_json(exact)
        with self.assertRaises(ValidationError):
            decode_json(b"[" + exact + b"]")

    def test_byte_cap_per_frame(self):
        raw = fixture("request").ljust(MAX_DOCUMENT_BYTES, b" ")
        expected = initial("expectations")
        expected["requestSha256"] = hashlib.sha256(raw).hexdigest()
        packed = encode(expected).ljust(MAX_DOCUMENT_BYTES, b" ")
        self.assertEqual(validate_bytes("request", raw, packed), json.loads(raw))
        self.assert_refused("request", raw + b" ", expected=packed)
        self.assert_refused("request", raw, expected=packed + b" ")

    def test_findings_evidence_and_reference_inclusive_limits(self):
        report = initial("report")
        report["findings"] = [finding_row(i) for i in range(MAX_FINDINGS)]
        validate_bytes("report", encode(report), fixture("expectations"))
        report["findings"].append(finding_row(MAX_FINDINGS))
        self.assert_refused("report", encode(report))

        report = initial("report")
        report["evidence"] = [evidence_row(i) for i in range(MAX_EVIDENCE)]
        ids = [row["id"] for row in report["evidence"]]
        report["findings"] = [finding_row(0, ids[:1000]), finding_row(1, ids[1000:])]
        validate_bytes("report", encode(report), fixture("expectations"))
        report["findings"].append(finding_row(2, ids[:1]))
        self.assert_refused("report", encode(report))
        report["findings"] = []
        report["evidence"].append(evidence_row(MAX_EVIDENCE))
        self.assert_refused("report", encode(report))

    def test_evidence_references_and_ids_are_consistent(self):
        report = initial("report")
        report["evidence"] = [evidence_row(0)]
        for refs in (["unknown"], ["E0", "E0"]):
            with self.subTest(refs=refs):
                report["findings"] = [finding_row(0, refs)]
                self.assert_refused("report", encode(report))
        report["findings"] = [finding_row(0, ["E0"]), finding_row(0, ["E0"])]
        self.assert_refused("report", encode(report))
        report["findings"] = [finding_row(0, ["E0"])]
        report["evidence"].append(evidence_row(0))
        self.assert_refused("report", encode(report))

    def test_text_id_and_usage_boundaries(self):
        report = initial("report")
        report["limitations"] = ["я" * MAX_TEXT_LENGTH]
        report["findings"] = [finding_row(0)]
        report["findings"][0]["id"] = "x" * 128
        report["usage"]["elapsedMs"] = MAX_USAGE
        validate_bytes("report", encode(report), fixture("expectations"))
        for field, value in (
            ("limitations", ["x" * (MAX_TEXT_LENGTH + 1)]),
            ("findings", [{**finding_row(0), "id": "x" * 129}]),
            ("findings", [{**finding_row(0), "id": "F\n"}]),
            ("usage", {**report["usage"], "elapsedMs": MAX_USAGE + 1}),
            ("usage", {**report["usage"], "elapsedMs": -1}),
            ("usage", {**report["usage"], "elapsedMs": True}),
        ):
            with self.subTest(field=field, shape=type(value).__name__):
                self.assert_refused("report", encode({**report, field: value}))

    def test_usage_numbers_follow_exact_mathematical_integrality(self):
        schema = json.loads((ROOT / "schemas/review-report.v1.schema.json").read_bytes())
        standard = Draft202012Validator(schema)

        def is_integer(checker, value):
            if isinstance(value, Decimal):
                return value.is_finite() and value == value.to_integral_value()
            return Draft202012Validator.TYPE_CHECKER.is_type(value, "integer")

        exact_validator = validators.extend(
            Draft202012Validator,
            type_checker=Draft202012Validator.TYPE_CHECKER.redefine("integer", is_integer),
        )(schema)
        report = initial("report")
        report["usage"]["elapsedMs"] = "NUMBER"
        placeholder = encode(report)
        for lexical in (b"1", b"1.0", b"1e0", b"9007199254740991.0"):
            raw = placeholder.replace(b'"NUMBER"', lexical)
            with self.subTest(value=lexical):
                self.assertTrue(standard.is_valid(json.loads(raw)))
                self.assertTrue(exact_validator.is_valid(json.loads(raw, parse_float=Decimal)))
                checked = validate_bytes("report", raw, fixture("expectations"))
                self.assertIs(type(checked["usage"]["elapsedMs"]), int)
                self.assertEqual(checked["usage"]["elapsedMs"], int(Decimal(lexical.decode())))
        for lexical in (b"1.25", b"-1", b"9007199254740992", b"1.00000000000000000001"):
            raw = placeholder.replace(b'"NUMBER"', lexical)
            with self.subTest(value=lexical):
                self.assertFalse(exact_validator.is_valid(json.loads(raw, parse_float=Decimal)))
                self.assert_refused("report", raw)

    def test_usage_zero_stays_exact_with_arbitrarily_long_exponents(self):
        schema = json.loads((ROOT / "schemas/review-report.v1.schema.json").read_bytes())
        validator = Draft202012Validator(schema)
        report = initial("report")
        report["usage"]["elapsedMs"] = "NUMBER"
        placeholder = encode(report)
        for lexical in (b"0e999999999999999999999999", b"-0.00e-999999999999999999999999"):
            raw = placeholder.replace(b'"NUMBER"', lexical)
            with self.subTest(value=lexical):
                self.assertTrue(validator.is_valid(json.loads(raw)))
                normalized = validate_bytes("report", raw, fixture("expectations"))["usage"]["elapsedMs"]
                self.assertIs(type(normalized), int)
                self.assertEqual(normalized, 0)
        raw = placeholder.replace(b'"NUMBER"', b"1e-999999999999999999999999")
        self.assert_refused("report", raw)

    def test_published_schema_structure_matches_runtime(self):
        for kind in ("request", "report"):
            schema = json.loads((ROOT / f"schemas/review-{kind}.v1.schema.json").read_bytes())
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            good = initial(kind)
            self.assertTrue(validator.is_valid(good))
            validate_bytes(kind, fixture(kind), fixture("expectations"))
            variants = [
                {**good, "nativeAuthorize": True},
                {**good, "schemaVersion": f"ars.review-{kind}.v2"},
                {**good, "requestId": "line\n"},
                {**good, "source": {**good["source"], "sha256": "A" * 64}},
                {**good, "packs": [{"id": "x", "version": "1", "sha256": "0" * 64, "permission": True}]},
            ]
            for bad in variants:
                with self.subTest(kind=kind, fields=tuple(bad)):
                    self.assertFalse(validator.is_valid(bad))
                    self.assert_refused(kind, encode(bad))

    def test_expectations_schema_matches_runtime_shape(self):
        schema = json.loads((ROOT / "schemas/review-expectations.v1.schema.json").read_bytes())
        request_schema = json.loads((ROOT / "schemas/review-request.v1.schema.json").read_bytes())
        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["$defs"], request_schema["$defs"])
        validator = Draft202012Validator(schema)
        expected = initial("expectations")
        report = initial("report")
        for name, bindings in (
            ("fixture", {}),
            ("maximum equivalent IDs and pack text", {
                "requestId": "a" * 128,
                "packs": [{"id": "a-b", "version": "я" * MAX_TEXT_LENGTH, "sha256": "b" * 64}],
            }),
        ):
            with self.subTest(case=name):
                both = {**expected, **bindings}
                validator.validate(both)
                validate_bytes("report", encode({**report, **bindings}), encode(both))

        malformed = [(f"missing {key}", {k: v for k, v in expected.items() if k != key}) for key in expected]
        malformed.extend((key, {**expected, key: value}) for key, value in (
            ("permission", True),
            ("schemaVersion", "ars.review-expectations.v2"),
            ("assignmentId", 1),
            ("requestId", "a" * 129),
            ("source", {**expected["source"], "representation": "path"}),
            ("source", {**expected["source"], "path": "unused"}),
            ("source", {k: v for k, v in expected["source"].items() if k != "baseSha256"}),
            ("packs", {}),
            ("packs", [{"id": "pack", "sha256": "b" * 64}]),
            ("packs", [{"id": "pack", "version": "я" * (MAX_TEXT_LENGTH + 1), "sha256": "b" * 64}]),
            ("requestSha256", "A" * 64),
            ("requiredCoverage", []),
            ("requiredCoverage", ["inspect-scope", "inspect-scope"]),
        ))
        for name, bad in malformed:
            with self.subTest(case=name, value=type(bad.get(name)).__name__):
                self.assertFalse(validator.is_valid(bad))
                with self.assertRaises(ValidationError) as raised:
                    validate_bytes("report", fixture("report"), encode(bad))
                self.assertEqual(raised.exception.kind, "malformed")

        pack = {"id": "pack", "version": "1", "sha256": "b" * 64}
        for kind, divergence in (
            ("malformed", {"packs": [pack, {**pack, "version": "2"}]}),
            ("binding-mismatch", {"requestSha256": "a" * 64}),
        ):
            with self.subTest(runtime_only=kind):
                bad = {**expected, **divergence}
                validator.validate(bad)
                with self.assertRaises(ValidationError) as raised:
                    validate_bytes("report", fixture("report"), encode(bad))
                self.assertEqual(raised.exception.kind, kind)
