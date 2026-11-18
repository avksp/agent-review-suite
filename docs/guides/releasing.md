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

## Publish to PyPI

Set the PyPI Trusted Publisher to repository `avksp/agent-review-suite`,
workflow `publish.yml`, and environment `pypi`.
See [Trusted Publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

1. On GitHub, wait for all 15 CI jobs on the release commit in `main`.
2. Run **Publish to PyPI** manually on `main` to check the candidate. The run
   saves the wheel and source archive from that CI run. Check the file names
   and hashes. Use `python -m twine check --strict` for a metadata check.
3. The release owner MUST authorize publication. Create a stable GitHub Release
   with a protected tag that matches the package version and points to the checked
   commit. For example, use `v0.1.0` for version `0.1.0`.
4. Publishing the GitHub Release starts the upload. The workflow checks the
   tag, commit, CI result, and SHA-256. It uploads the same wheel and source
   archive through the `pypi` environment. Distribute the plugin ZIP separately.
5. Verify the files on PyPI and install the published version in a clean
   environment. Record the result.

If the CI artifacts expire, rerun all jobs for the release commit first.
