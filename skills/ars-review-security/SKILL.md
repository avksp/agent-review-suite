---
name: ars-review-security
description: Assess reachable application and agent security risks in supplied material.
---

# ars-review-security

Read [the review boundary](references/boundary.md) before this role.

Map attacker input to trust boundary and effect. Assess existing controls before calling a defect. Include prompt/data/tool boundaries, permissions, source/evidence integrity, secrets, supply chain and resource exhaustion when applicable. Do not assume web/API/RAG/DB surfaces. Propose only safe scoped validation; do not execute offensive examples. Coverage gaps remain explicit.

This is guidance-only bootstrap content; caller permissions and acceptance remain authoritative.

Use the ARS v1 validator when the caller supplies review bytes and separate
protected expectations. A matching format and binding leaves semantic review
and acceptance with the caller.
