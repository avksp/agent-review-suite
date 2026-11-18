---
name: ars-review-implementation
description: Review implemented changes and evidence against explicit acceptance criteria.
---

# ars-review-implementation

Read [the review boundary](references/boundary.md) before this role.

Compare the exact changed source with the supplied accepted requirements and evidence. Check ownership, relevant dependencies, negative cases and real test results. Do not treat a passing schema as semantic proof. For repairs, identify proven affected roles; uncertain impact remains a full-scope review requirement. Do not grant native acceptance.

This is guidance-only bootstrap content; caller permissions and acceptance remain authoritative.

Use the ARS v1 validator when the caller supplies review bytes and separate
protected expectations. A matching format and binding leaves semantic review
and acceptance with the caller.
