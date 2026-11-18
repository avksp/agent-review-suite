# Validation strategy

[Русский](../ru/guides/testing.md)

Install the pinned development requirements, then run the source suite from
the checkout with `src` on `PYTHONPATH`.

```sh
PYTHONPATH=src python -B -m unittest discover -s tests -v
```

The suite checks contract limits, trusted joins, intake refusals, exit
codes, and archive boundaries. For example, it expects exit 3 for a foreign
coverage ID and exit 2 when the same input also duplicates a coverage row.
Run Ruff and mypy before building wheel, sdist, and plugin ZIP. Inspect the
archive contents and run the installed validator in a clean wheel environment.

Record OS, interpreter, exact source, and artifacts for every claimed run.
Distinguish local tests from the 15 hosted CI cells. Preserve failed attempts
and retain unknown usage as null. Report savings only for equivalent work.
