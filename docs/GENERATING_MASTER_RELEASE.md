# Releasing to Master

Releases are fully automated via [semantic-release](https://github.com/semantic-release/semantic-release).
When commits land on `master`, the release workflow determines whether a new version is needed
based on [Conventional Commits](https://www.conventionalcommits.org/) prefixes.

## How it works

1. **Push/merge to `master`** triggers `.github/workflows/release.yml`.
2. **semantic-release** analyzes commit messages since the last tag:
   - `fix:` → patch bump (0.4.0 → 0.4.1)
   - `feat:` → minor bump (0.4.0 → 0.5.0)
   - `feat!:` or `BREAKING CHANGE:` → major bump (0.4.0 → 1.0.0)
3. If a release is warranted:
   - `CHANGELOG.md` and `VERSION` are updated and committed.
   - A git tag and GitHub Release are created.
4. The new tag triggers the existing **Build All Packages CI** workflow, which handles
   PyPI and Docker publishing.

## Commit message format

All commits to `master` should follow Conventional Commits:

```
<type>(<optional scope>): <description>

[optional body]

[optional footer(s)]
```

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`.

## Manual steps

None required for normal releases. If you need to force a specific version or skip a
release, consult the [semantic-release documentation](https://semantic-release.gitbook.io/).
