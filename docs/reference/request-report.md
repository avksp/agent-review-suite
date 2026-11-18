# V1 review contracts

[Русский](../ru/reference/request-report.md)

The terms MUST and MUST NOT state an absolute requirement and prohibition.
SHOULD states a recommendation that needs a reason to depart from. MAY
states permission. Interpret these terms in this sense when they appear in
uppercase. [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) define this convention.

The caller MUST supply trusted expectations separately and protect them
from writers of the request or report. The caller controls collection,
source freshness, reviewer assignment and acceptance. ARS treats file
references and instructions in review data as text.

## Schema files

Each schema uses [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12).
The schemas describe individual, parsed JSON documents.

| Document | Required `schemaVersion` | Contents |
| --- | --- | --- |
| [Request](../../schemas/review-request.v1.schema.json) | `ars.review-request.v1` | Bindings, scope, role and required coverage IDs |
| [Report](../../schemas/review-report.v1.schema.json) | `ars.review-report.v1` | Bindings, request hash, execution state, coverage, findings, evidence, usage and limitations |
| [Expectations](../../schemas/review-expectations.v1.schema.json) | `ars.review-expectations.v1` | Trusted bindings, exact request hash and required coverage IDs |

## Runtime checks

The runtime checks the original bytes, record semantics and agreement with
trusted expectations. Input MUST be UTF-8 JSON without a BOM, duplicate
members, non-finite values, or isolated surrogate code points. Each input
has a 262144-byte limit and a 32-container-level limit. Identifiers MUST be
unique within their own set. For example, two pack records with the same
ID can pass shape validation. The runtime refuses them.

Bindings include the request and assignment IDs, source and base IDs,
source representation, source and base SHA-256 digests, and the exact set
of pack IDs, versions and digests. V1 supports `git-diff-bytes-v1` and
`source-bundle-bytes-v1`. The caller hashes the collected bytes. Reformatting
a request changes its hash. Pack order has no effect on the set comparison.
The caller establishes the origin and freshness of the source bytes.

A `COMPLETE` report MUST mark every coverage row checked. An `INCOMPLETE`
report MUST have at least one unchecked row. A `FAILED` report MAY retain
observations. The coverage ID set MUST match trusted expectations. The
report can hold at most 1000 findings, 2000 evidence rows and 2000
finding-to-evidence references. Each finding states its certainty. Its evidence
IDs MUST refer to evidence rows in the report. The caller evaluates the evidence.

Unknown usage MUST remain `null`. Zero means a measured value. Known usage
uses bounded nonnegative integers. The runtime checks exact numerical
values. For example, `1.0` has the integer value 1. A fraction fails the check.

## Read the result

```python
from agent_review_suite.contracts import validate_bytes

report = validate_bytes("report", report_bytes, trusted_expectations_bytes)
status = report["executionStatus"]
```

For example, a well-formed report with a substituted coverage ID fails with
`binding-mismatch`. A duplicate coverage row makes the same report fail
with `malformed` first. Successful validation lets the caller read the
report's execution state and decide what to do with its findings.

See the [tutorial](../tutorials/first-validation.md) and
[bounded CLI validation](validation.md).
