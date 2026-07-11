# Releasing to Master

Releases are automated from Conventional Commits, but publication is intentionally
separated from candidate preparation. The public tag, package registries, Docker
`latest`, and GitHub Release are updated only after the exact versioned candidate
commit passes every release gate.

## Gated release sequence

1. A push or merge to `master` starts `.github/workflows/release.yml`.
2. The locked semantic-release analyzer determines whether the commits since the
   last tag require a release:
   - `fix:` produces a patch release.
   - `feat:` produces a minor release.
   - `feat!:` or `BREAKING CHANGE:` produces a major release.
3. If no release is required, the workflow exits without changing the repository
   or any registry.
4. If a release is required, the workflow writes `VERSION` and `CHANGELOG.md`,
   commits them on an isolated `release-candidate/<run-id>` branch, and records the
   candidate commit SHA. No public tag or mutable package tag is created yet.
5. The Python, frontend, integration, package, amd64/arm64 Docker, runtime smoke,
   vulnerability scan, signing, and SBOM gates all check out that exact candidate
   SHA. The package build also verifies that `VERSION`, wheel metadata, and sdist
   metadata agree.
6. Publication stops if `master` moved while the candidate was being validated.
   A later release run will prepare a new candidate from the new head.
7. After every gate succeeds, the workflow fast-forwards `master` to the validated
   candidate, creates the version tag and a draft GitHub Release, publishes any
   configured external packages, moves the validated Docker version/`latest`
   manifests, and then makes the GitHub Release public.
8. The GitHub Release includes the wheel, sdist, amd64/arm64 SBOMs, and
   `SHA256SUMS` so the released artifact set can be checked independently.

Direct `master` package CI remains a validation lane. It is not allowed to publish
PyPI or move Docker `latest`/version tags. This prevents a pre-release commit from
being packaged under the previous version while a separate workflow publishes the
next GitHub Release.

## Release integrity invariants

Every public release must satisfy all of these conditions:

- The version tag points at the same commit stored on `master`.
- `VERSION`, wheel metadata, sdist metadata, Docker tags, and GitHub Release name
  contain the same version.
- The exact candidate SHA passed Python, frontend, integration, package, Docker,
  runtime smoke, security scan, signing, and SBOM generation.
- `latest` is moved only from the two temporary architecture images produced for
  that candidate SHA.
- A release failure leaves the GitHub Release in draft state rather than presenting
  a partially published artifact set as complete.

The contract is enforced by `scripts/verify-release-integrity.py`, locked release
tooling under `.github/release/`, and workflow regression tests in
`tests/unit/test_release_workflows.py`.

## Optional publishing credentials

External publishing uses these repository secrets:

- `PYPI_TOKEN` for PyPI packages.
- `DOCKER_USERNAME` and `DOCKER_PASSWORD` for Docker Hub images.

When those secrets are absent, their corresponding publish steps are skipped.
GitHub Releases, GHCR images, package builds, tests, scans, signatures, and SBOMs
remain part of the release path.

## Recovery

- If candidate validation fails, fix the underlying problem and merge normally.
  The isolated candidate is not a public release and public tags remain unchanged.
- If `master` moves during validation, do not force-push the candidate. Let the new
  `master` run create and validate a fresh candidate.
- If publication fails after the draft release is created, keep the release draft,
  inspect the failed registry step, and do not manually move `latest` unless all
  artifact versions and digests have been reverified.
- Never retag an existing public version. Publish a new corrective patch version.
