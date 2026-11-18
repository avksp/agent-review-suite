# Caller integration

[Русский](../ru/reference/integration.md)

1. Save the source and pack bytes. Assign IDs, scope, and coverage in a v1 request.
2. Save the exact request bytes. Hash them with SHA-256.
3. Create trusted expectations from the caller's source, request, and policy.
   The caller MUST protect them separately from the request and report writers.
4. Give the request and review packet to each authorized reviewer.
5. Validate the report and trusted expectations. Keep the exact report and
   its source bindings.
6. Check the findings and apply the caller's acceptance rules.

For example, if the caller changes the request's whitespace, its digest changes.
An older report still has the prior digest and fails the trusted binding check
against the new expectations.

The caller owns permissions, reviewer independence, budget and acceptance.
It MAY use its own workflow tool. ARS provides validation. The caller
separately decides whether a finding is reliable and whether work is accepted.

See [schemas and obligation terms](request-report.md),
[bounded input](validation.md), and [adapter policy](adapters.md).
