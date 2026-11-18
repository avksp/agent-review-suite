# Threat model

[Русский](../ru/architecture/threat-model.md)

A review packet can contain untrusted text. Examples include source files,
target instructions, logs, scanner output and earlier reviewer answers.
The caller MUST treat this material as data. Reading it MUST NOT grant
permissions or trigger commands, plugin setup, or network calls.

The caller SHOULD give reviewers a bounded packet with read-only access.
If a review needs an active check, the caller MUST first authorize its tools
and run it in isolation with a sanitized environment, disabled external network
and explicit resource limits. Record a gap when evidence
is missing. For example, if a reviewer cannot run a test, record that gap in
the report and keep any static finding tied to the evidence available.

Stage CLI inputs under a controlled local root. Protect expectations and
record the exact bytes used for hashing. Validate reviewer output before
rendering it. Protect source data when sending it to a host. A matched hash
identifies bytes. The caller must establish evidence origin, freshness and
reviewer independence separately. Report unknown usage as `null`.

See [bounded input requirements](../reference/validation.md) and
[contract obligations](../reference/request-report.md).
