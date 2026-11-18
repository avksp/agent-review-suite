# Installation

[Русский](../ru/guides/install.md)

Use Python 3.11 through 3.15. Create and activate a virtual environment.
Run `python -m pip install -e .` from the source checkout, or install the
supplied wheel with `python -m pip install /path/to/agent_review_suite-0.1.0-py3-none-any.whl`.
Import `agent_review_suite` and inspect `__version__` to check the installation.

Use the [bounded CLI](../reference/validation.md) on eligible Linux or macOS.
On Windows, call the [Python bytes API](../reference/request-report.md).
For a version published on PyPI, install the exact version. For example:

```sh
python -m pip install agent-review-suite==0.1.0
```
