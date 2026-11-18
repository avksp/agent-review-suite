# Contributing

Start with an issue or bounded proposal describing the problem, constraints,
alternatives (including no change), acceptance and evidence. Significant work
uses the ALK S2 lifecycle. Read AGENTS.md and docs/guides/testing.md.

Create a venv, install `requirements-dev.txt`, install the project editable, then
run `python tools/check_repository.py`, `python -m unittest discover -s tests -v`
and Ruff. Do not commit .alk, tasks, work, tokens or raw private model output.
Keep changes small; reuse successful checks only for identical relevant inputs.
Public claims need actual qualification. Security reporting is in SECURITY.md.
