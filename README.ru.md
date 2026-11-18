<p align="center"><img src="docs/assets/agent-review-suite-banner.svg" alt="Agent Review Suite" width="100%"></p>

# Agent Review Suite

[![Лицензия Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
![Целевые версии Python](https://img.shields.io/badge/python_target-3.11--3.15-blue.svg)

[English](README.md) · [Документация](docs/ru/README.md) · [Дорожная карта](docs/ru/roadmap.md)

Agent Review Suite (ARS) даёт рекомендации для технического и продуктового
ревью и самостоятельный валидатор версионированных документов. Вызывающая
сторона назначает ревьюверов и отвечает за актуальность исходников, запуск,
бюджет и приёмку.

Версия **0.1.0** включает три схемы, чистый Python
API и ограниченную проверку файлов и stdin на подходящих системах macOS и Linux.
На Windows вызывающая сторона передаёт байты в Python API. Проект определяет
15 заданий CI для трёх операционных систем. Все 12 вариантов интеграции
с хостами остаются неквалифицированными.

## Проверка локального отчёта

Установите пакет из рабочего дерева командой `python -m pip install -e .`.
Подготовьте отчёт и защищённые ожидаемые привязки в двух разных файлах.

```sh
python -B -m agent_review_suite validate --kind report --input report.json \
  --root /absolute/local/staging --expectations expected.json
```

Код 0 подтверждает соответствие формату и доверенным привязкам. Вызывающая
сторона отдельно оценивает состояние выполнения, замечания и возможность
приёмки. См. [условия ввода и коды возврата](docs/ru/reference/validation.md)
и [форматы запроса и отчёта](docs/ru/reference/request-report.md).

У ARS нет клиента моделей или обязательной зависимости от ALK. Вызывающая
сторона использует собственный порядок ревью и приёмки. Частные планы, снимки
исходников и доказательства выполнения остаются за пределами публичных архивов.

См. [установку](docs/ru/guides/install.md), [skills](docs/ru/guides/skills.md),
[первую проверку](docs/ru/tutorials/first-validation.md),
[архитектуру](docs/ru/architecture/c0-c4.md), [безопасность](SECURITY.ru.md),
[участие](CONTRIBUTING.ru.md) и [поставку](docs/ru/guides/releasing.md).
