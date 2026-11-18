# Install for agents

Use this guide to install the ARS validator or load review skills in an agent
host. Start from a source checkout and use Python 3.11 through 3.15.

## Validator

From the repository root, create and use an isolated environment.

```sh
python -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -B -c "import agent_review_suite; print(agent_review_suite.__version__)"
```

In Windows PowerShell, use `.\.venv\Scripts\python.exe` in place of
`.venv/bin/python`.

## Check the installation

Run the [first validation tutorial](docs/tutorials/first-validation.md) from
the source checkout. The example prints `COMPLETE` for the supplied report
and `binding-mismatch` after a coverage ID changes.

On supported Linux and macOS systems, you can also check the CLI with the same
fixtures.

```sh
.venv/bin/python -B -m agent_review_suite validate --kind report \
  --root "$(pwd -P)/tests/fixtures" --input report.json --expectations expectations.json
```

This example returns exit code 0 and prints `{"status":"VALID"}`. On Windows,
use the [Python bytes API](docs/reference/request-report.md).

## Host plugins

Use the absolute path to your checkout where the commands show
`/path/to/agent-review-suite`.

### Codex

```sh
codex plugin marketplace add /path/to/agent-review-suite
codex plugin add agent-review-suite@agent-review-suite
```

### Claude Code

```sh
claude plugin marketplace add /path/to/agent-review-suite
claude plugin install agent-review-suite@agent-review-suite
```

### Other hosts

Use the host's documented project-local skill discovery. For example, give
the host the relevant `SKILL.md` and its references as a review packet.
See [skills and host use](docs/guides/skills.md).

## Status

The plugin provides review guidance. Host projections are `UNQUALIFIED`.
The caller grants permissions, assigns reviewers, and decides acceptance.
