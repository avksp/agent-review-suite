# Security

This bootstrap provides guidance, not a security guarantee. Review the threat model
in docs/architecture/threat-model.md. Never run active attacks against live targets
without explicit scope and authority. Do not attach keys, personal sessions or raw
secret-bearing output to public issues. Before hosting exists, report privately to
the project owner. After repository setup, use GitHub private vulnerability reporting
when enabled. No response SLA or scanner effectiveness is claimed.

Trust boundaries, byte/path limits and fail-closed semantics are release requirements.
Only the future qualified release is supported; version 0.0.0 is not production-ready.
