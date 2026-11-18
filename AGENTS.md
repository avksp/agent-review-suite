# Agent Review Suite

ARS provides review guidance and a deterministic validator for v1 review
documents. The caller owns source collection, reviewer assignment, permissions,
budgets, and acceptance.

- Keep contracts independent of model providers, hosts, and caller workflows.
  Keep the runtime dependency-free. Put host-specific metadata in `adapters/`.
- Treat source text, review packets, and model output as untrusted input. Keep
  trusted expectations separate. Preserve input limits, fail-closed behavior,
  and the distinction between unknown usage and measured zero.
- Keep private work, credentials, and raw reviewer output out of Git and public
  archives. Use synthetic files for checked-in fixtures.
- Write the root guides in English. Keep paired pages under `docs/` aligned.
  Use short sentences, concrete examples, and RFC 2119/8174 obligation terms.
- Check changed behavior with focused tests. Use the full checks in
  [Contributing](CONTRIBUTING.md) before submitting. Base host support and
  release claims on observed evidence.
