# Prepare a release

[Русский](../ru/guides/releasing.md)

1. Build the wheel, source distribution (sdist) and plugin ZIP from one source
   tree. Record its Git commit and tree ID. Keep the archive hashes and member
   lists.
2. Screen public source and archives for private data. Each archive MUST contain
   the same three v1 schemas. Only the sdist can contain the synthetic fixtures.
3. Install the wheel in a clean environment. Run the installed API and CLI
   checks. Record local evidence for independent final audit and finalization.
4. Open a PR against the protected branch. Check that the proposed merge tree
   matches the audited tree. All 15 hosted CI jobs MUST pass on the proposed
   merge revision. Repeat the check if the base or head changes.

For example, compare the SHA-256 of the expectations schema in the wheel,
sdist and plugin ZIP. The three digests MUST match.

## Prepare PyPI

Check the wheel and sdist metadata with `python -m twine check --strict`.
Record the names and hashes of both files. Only the wheel and sdist belong
in the PyPI upload set. Keep the plugin ZIP separate.

For a new project, the owner can set up a pending Trusted Publisher for
the exact GitHub repository, workflow file and environment. A pending
publisher takes effect on first use. Confirm control of the project name
before publishing. [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)

The release owner MUST authorize publication before publisher activation or
upload. The template in `.github/workflow-templates` remains inactive and
needs a reviewed artifact handoff before use. After an authorized release,
verify GitHub and PyPI artifacts and a clean installation from PyPI. Record
the postpublication audit.
