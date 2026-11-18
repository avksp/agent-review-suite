# Проверьте первый отчёт

[English](../../tutorials/first-validation.md)

Работайте из локальной копии исходников. [Установите ARS](../guides/install.md)
в виртуальное окружение. Запустите этот пример Python из корня проекта.
Он использует синтетические примеры из `tests/fixtures`.

Сначала пример проверяет отчёт по отдельным доверенным привязкам.
Затем он меняет один ID покрытия в отчёте и сохраняет привязки.

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

`COMPLETE` означает состояние выполнения в отчёте. При изменении ID
покрытия структура отчёта остаётся корректной. Проверка доверенных привязок
отклоняет отчёт. В рабочей системе вызывающая сторона обязана (MUST) создавать
и защищать свои привязки. См. [контракты v1](../reference/request-report.md).
