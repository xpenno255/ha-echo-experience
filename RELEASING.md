# Version and release tracking

Starting with 0.4.1, the Checks workflow publishes a GitHub Release automatically
after a push to main passes the Python and frontend checks. The tag is the
integration manifest version prefixed with `v`, for example `v0.4.1`, and points
to the exact commit that passed those checks. Release notes come from that
version's section of `CHANGELOG.md`.

## Every new integration version

1. Make the change and add meaningful regression coverage where needed.
2. Increase `custom_components/echo_experience/manifest.json` to the next stable
   `major.minor.patch` version. Use a patch for fixes and a minor for new features.
3. Add one matching `## <version> - <description>` section to `CHANGELOG.md` with
   user-visible changes and any migration requirements.
4. Run the Python and frontend checks. Commit the intended files and push to main
   or merge a reviewed pull request.
5. Confirm both the Checks and release jobs succeed, then verify the GitHub tag
   and release. Record deployment separately after following the existing backup,
   config-validation and device-idle checks.

The release contains GitHub's source archives. It is a versioned source snapshot,
not an automatic Home Assistant deployment or a promise of HACS update delivery.
Local credentials, audit captures and backups remain excluded from Git.

Documentation or tooling changes may keep the same integration version. The
workflow leaves an existing release unchanged; it never retags a published
version. If an existing tag without a release points elsewhere, publishing fails
so the mismatch can be reviewed. A failed publishing job can be rerun after its
cause is fixed. Pull requests run validation but cannot publish releases.

## Local release-note validation

```sh
python scripts/prepare_release.py --output-dir /tmp/echo-release
```

Invalid versions, missing or duplicate changelog sections and empty notes stop the
workflow before publication. Historical versions before 0.4.1 are not backfilled;
their commits and changelog remain available in Git.
