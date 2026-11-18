# Validate your first report

[Русский](../ru/tutorials/first-validation.md)

Work from a source checkout. [Install ARS](../guides/install.md) in a virtual
environment. From the checkout root, run this Python example. It uses the
synthetic fixtures under `tests/fixtures`.

The first check uses a report and separate trusted expectations. Then the
example changes one coverage ID in the report and keeps the expectations.

```python
import json
from pathlib import Path

from agent_review_suite.contracts import ValidationError, validate_bytes

fixtures = Path("tests/fixtures")
expected = (fixtures / "expectations.json").read_bytes()
report = (fixtures / "report.json").read_bytes()

result = validate_bytes("report", report, expected)
print(result["executionStatus"])

changed = json.loads(report)
changed["coverage"][0]["id"] = "another-check"
try:
    validate_bytes("report", json.dumps(changed).encode("utf-8"), expected)
except ValidationError as error:
    print(error.kind)
```

```text
COMPLETE
binding-mismatch
```

`COMPLETE` is the report's execution state. When the coverage ID changes,
the report still has valid fields. The trusted comparison refuses it.
In production, the caller MUST create and protect its own expectations.
See [v1 contracts](../reference/request-report.md).
