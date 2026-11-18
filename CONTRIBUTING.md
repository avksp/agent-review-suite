# Contributing

ARS keeps review contracts and validation in the Python core. Host projections
describe how a host can load guidance. The caller controls reviewers, permissions,
and acceptance.

- Keep the runtime dependency-free. Preserve the v1 contracts and add tests for
  changes to validation behavior.
- Use synthetic inputs in `tests/fixtures/`. Keep credentials, private plans,
  and raw review output out of source and distributions.
- Support host claims with evidence from the stated host and version. Keep
  paired documentation pages consistent.
- Describe the problem, proposed change, and checks in the pull request. Report
  vulnerabilities through the [security policy](SECURITY.md).

## Commit messages

Use a short English subject in the form `type(scope): action`. Scope is optional.
Use `feat` for a capability, `fix` for a correction, `docs` for documentation,
`test` for test coverage, and `chore(release)` for release work.

```text
fix(validation): reject a repeated coverage ID
docs(install): explain isolated installation
test(packaging): cover schema assets
```

Keep related changes together. Mark a breaking change with `!` in the subject
or a `BREAKING CHANGE:` footer.

## Check a change

Create and activate a virtual environment. From the repository root, run the
same checks that CI uses.

```sh
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation -e .
python -B tools/check_repository.py --public-ci
python -B -m ruff check .
python -B -m mypy
python -B -m unittest discover -s tests -v
```

For packaging changes, build and inspect the wheel, source distribution, and
plugin ZIP. Record the exact source and results. See [testing](docs/guides/testing.md)
and [release preparation](docs/guides/releasing.md).
