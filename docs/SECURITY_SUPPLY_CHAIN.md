# Supply-Chain Security

This fork hardens its published artifacts with static analysis, keyless image
signing, and Software Bill of Materials (SBOM) generation. All of this runs in
GitHub Actions; nothing additional is required from operators who simply pull
the published images.

## Static analysis (CodeQL)

`.github/workflows/codeql.yml` runs GitHub CodeQL over the `python` and
`javascript-typescript` sources on every push and pull request to `master`, and
on a weekly schedule. Results appear in the repository's **Security > Code
scanning** dashboard. Vendored/generated frontend output and test fixtures are
excluded from analysis.

## Signed container images (cosign, keyless)

Release container images are signed with [cosign](https://docs.sigstore.dev/)
using **keyless** signing (Sigstore OIDC + the public Rekor transparency log).
There is no long-lived signing key: the signing identity is the GitHub Actions
workflow itself.

Each architecture image is signed **by digest** (not by a mutable tag) on the
publish path only (pushes to a branch or tag — pull-request builds are not
signed because forks have no OIDC token).

### Verifying an image

Install cosign, then verify against the workflow identity. Replace the image
reference with the tag or digest you pulled:

```bash
cosign verify \
  --certificate-identity-regexp \
    "https://github.com/jtn0123/compresso/.github/workflows/.+@refs/(heads|tags)/.+" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/jtn0123/compresso:latest
```

A successful verification prints the certificate subject (the signing workflow)
and the Rekor transparency-log entry. If verification fails, do not trust the
image.

> Note: signatures are produced per-architecture digest. When verifying a
> multi-arch tag, cosign resolves and checks the platform-specific image.

## Software Bill of Materials (SBOM)

For each published image, an SPDX-JSON SBOM is generated with
[`anchore/sbom-action`](https://github.com/anchore/sbom-action) and uploaded as
a workflow artifact (`sbom-amd64-<sha>` / `sbom-arm64-<sha>`) on the build run.
Download it from the **Actions** run summary to inspect the exact OS and
language dependencies baked into the image.
