<p align="center"><img src="docs/assets/agent-review-suite-banner.svg" alt="Agent Review Suite" width="100%"></p>

# Agent Review Suite

[![Apache-2.0 license](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
![Python target](https://img.shields.io/badge/python_target-3.11--3.15-blue.svg)

[Русский](README.ru.md) · [Documentation](docs/README.md) · [Roadmap](docs/roadmap.md)

Agent Review Suite (ARS) provides technical and product review guidance and
a standalone validator for versioned review documents. The caller assigns
reviewers and controls source freshness, execution, budgets, and acceptance.

Version **0.1.0** provides three schemas, a pure Python
API, and bounded file and stdin validation on eligible macOS and Linux systems.
On Windows, callers use the Python API with bytes. The project defines 15
hosted CI jobs across three operating systems. The 12 host projections
remain unqualified.

## Validate a local report

Install from the checkout with `python -m pip install -e .`. Stage the report
and protected caller expectations as two distinct files.

```sh
python -B -m agent_review_suite validate --kind report --input report.json \
  --root /absolute/local/staging --expectations expected.json
```

Exit 0 confirms that the format and trusted bindings match. The caller still
evaluates execution state, findings, and eligibility for acceptance.
See [input requirements and exit codes](docs/reference/validation.md) and
[request and report formats](docs/reference/request-report.md).

ARS has no model client or required ALK dependency. A caller can use its own
review and acceptance workflow. Private plans, source snapshots, and execution
evidence stay outside public archives.

Read [installation](docs/guides/install.md), [skills](docs/guides/skills.md),
[first validation](docs/tutorials/first-validation.md),
[architecture](docs/architecture/c0-c4.md), [security](SECURITY.md),
[contributing](CONTRIBUTING.md), and [release delivery](docs/guides/releasing.md).
