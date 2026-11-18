# ADR 0001 · Keep the core caller-neutral

[Русский](../ru/architecture/adr-0001-boundaries.md)

Use a standalone, versioned request and report boundary. The caller owns
dispatch, budgets, retries, lifecycle records and acceptance. A caller MAY
use its own workflow tool through that tool's supported interfaces.

For example, a shell script and a workflow tool can send the same bytes to the
ARS validator. Each caller applies its own rules to the result. A failed review
and a failure to reach a host require different decisions. The caller MUST
reconcile an unknown outcome before retrying.

A future format bridge SHOULD map exact fields for a concrete consumer.
The portable contract stays independent of host-specific state and policies.
