## [1.10.6](https://github.com/jtn0123/compresso/compare/v1.10.5...v1.10.6) (2026-03-31)


### Bug Fixes

* add missing lang and title attributes for SonarCloud reliability ([7c2a895](https://github.com/jtn0123/compresso/commit/7c2a8950eb848f160da5cde26c2dafdd07346e84))
* exclude frontend from SonarCloud analysis ([ae5b338](https://github.com/jtn0123/compresso/commit/ae5b338fe009a823f6ad397abc6e544a08301b8f))
* exclude frontend from SonarCloud coverage/duplication analysis ([2b314bc](https://github.com/jtn0123/compresso/commit/2b314bc251c39f4fa36d2bd5879ba960b7af88f1))
* sanitize v-html content to resolve SonarCloud security hotspots ([e2face5](https://github.com/jtn0123/compresso/commit/e2face54565f05fe557684b4d51df3f5f038d82c))

## [1.10.5](https://github.com/jtn0123/compresso/compare/v1.10.4...v1.10.5) (2026-03-31)


### Bug Fixes

* override cov-fail-under for CI shards ([f9dd9b1](https://github.com/jtn0123/compresso/commit/f9dd9b17af49e48400bad86a645c975b6cf809f8))
* update npm dependencies to resolve security vulnerabilities ([a2bc41e](https://github.com/jtn0123/compresso/commit/a2bc41e2ecb0863e052c418f3baf43cc35fb24b9))
* update npm in Docker base image to resolve picomatch CVE-2026-33671 ([32f2d5b](https://github.com/jtn0123/compresso/commit/32f2d5b30adde72f39089a55dececd03cb5ff55f))


### Reverts

* remove frontend formatting from this PR ([667b869](https://github.com/jtn0123/compresso/commit/667b869bab4a547c74e0449e644b26382165f291))

## [1.10.4](https://github.com/jtn0123/compresso/compare/v1.10.3...v1.10.4) (2026-03-30)


### Bug Fixes

* align sonar-project.properties with actual artifact availability ([f80611e](https://github.com/jtn0123/compresso/commit/f80611e4307d176823eeac7950267045d216e035))
* override cov-fail-under for integration tests ([8d5124f](https://github.com/jtn0123/compresso/commit/8d5124fcb9228a363a5b04fe93c7dc37060e7eff))
* update package-lock.json for @vitest/coverage-v8 ([ad42a2c](https://github.com/jtn0123/compresso/commit/ad42a2cc8ba1bc8370f67e9bb4a1ef0620f912f7))

## [1.10.3](https://github.com/jtn0123/compresso/compare/v1.10.2...v1.10.3) (2026-03-29)


### Bug Fixes

* address CodeRabbit and CodeQL review comments ([534c491](https://github.com/jtn0123/compresso/commit/534c4913246c0db3245b7748f46646178a4c3295))
* resolve SonarCloud security rating on new code ([fae7c79](https://github.com/jtn0123/compresso/commit/fae7c790ac29dff3acfb4ab75a25da59999a11a1))
* resolve SonarCloud security vulns, bugs, and async I/O issues ([814948c](https://github.com/jtn0123/compresso/commit/814948ca2483b3c4e20d609e8391ad5b99f6eb01))

## [1.10.2](https://github.com/jtn0123/compresso/compare/v1.10.1...v1.10.2) (2026-03-29)


### Bug Fixes

* add noqa for IntegrityError re-export in tasks.py ([7bfe289](https://github.com/jtn0123/compresso/commit/7bfe2892e722656fdfb78b05765a9674b708ba38))

## [1.10.1](https://github.com/jtn0123/compresso/compare/v1.10.0...v1.10.1) (2026-03-29)


### Bug Fixes

* resolve 5 SonarCloud blockers + 11 critical wildcard imports ([#64](https://github.com/jtn0123/compresso/issues/64)) ([3af8786](https://github.com/jtn0123/compresso/commit/3af87864fb8e82e352d7d98ff52820238c4a4b32))

# [1.10.0](https://github.com/jtn0123/compresso/compare/v1.9.0...v1.10.0) (2026-03-29)


### Features

* custom exception hierarchy + ORM model tests (JTN-9 + JTN-12) ([#59](https://github.com/jtn0123/compresso/issues/59)) ([ebd6812](https://github.com/jtn0123/compresso/commit/ebd68123201f141ca247c93c327a049873dc9970))

# [1.9.0](https://github.com/jtn0123/compresso/compare/v1.8.2...v1.9.0) (2026-03-29)


### Features

* add security headers to all HTTP handlers (JTN-6) ([#58](https://github.com/jtn0123/compresso/issues/58)) ([e9dba66](https://github.com/jtn0123/compresso/commit/e9dba6635c2b93984e0289803246015414afc9db))

## [1.8.2](https://github.com/jtn0123/compresso/compare/v1.8.1...v1.8.2) (2026-03-28)


### Bug Fixes

* address 13 issues from comprehensive code review ([#55](https://github.com/jtn0123/compresso/issues/55)) ([38d1eb0](https://github.com/jtn0123/compresso/commit/38d1eb005abdb7267b27f3af6158e68b4667f410))

## [1.8.1](https://github.com/jtn0123/compresso/compare/v1.8.0...v1.8.1) (2026-03-28)


### Bug Fixes

* address security, stability, and logic bugs found during code review ([247347b](https://github.com/jtn0123/compresso/commit/247347b2f16e15703e7d394c5fc0e7fa82fe5ff2))
* security, stability, and logic bugs from code review ([#54](https://github.com/jtn0123/compresso/issues/54)) ([1f22275](https://github.com/jtn0123/compresso/commit/1f222756f449043bc2d919a08688ee66373191b2))

# [1.8.0](https://github.com/jtn0123/compresso/compare/v1.7.1...v1.8.0) (2026-03-27)


### Bug Fixes

* **lint:** disable import-untyped mypy error for missing type stubs ([28c54fe](https://github.com/jtn0123/compresso/commit/28c54fe199d2ba1ad463f654d2a291fa6c14d852))
* **lint:** resolve ruff S110 and E402 violations in db_migrate.py ([e915ff8](https://github.com/jtn0123/compresso/commit/e915ff8e125c64a2b4e7f736f53a102c413ac0a3))
* **security:** add path validation to filebrowser and pending APIs ([1509b33](https://github.com/jtn0123/compresso/commit/1509b3363d5deb49287622c3e66ab86562db2bc8))
* **security:** harden plugin handlers against reflected XSS ([fc431e5](https://github.com/jtn0123/compresso/commit/fc431e587189aefb2fec0898211ab89426abbf8a))
* **security:** mitigate reflected XSS in plugin request handlers ([7806d45](https://github.com/jtn0123/compresso/commit/7806d45b7a366d65cfee71b03734a04a709126c3))
* **security:** use tornado.escape.json_encode for XSS-safe JSON output ([b74265f](https://github.com/jtn0123/compresso/commit/b74265f7a47a36bd308b7bf50ea75b441c358c52))
* suppress mypy method-assign, fully sanitize plugin handler inputs ([037d4b4](https://github.com/jtn0123/compresso/commit/037d4b44f639e4940ef89dd4c104ec1d13d24000))


### Features

* **lint:** enable bugbear (B) rules and fix 33 violations ([3baa094](https://github.com/jtn0123/compresso/commit/3baa094ec68a238ccbd3dd89662a42a5c5b7c262))
* **lint:** enable complexity (C90) and line length (E501) enforcement ([0c63878](https://github.com/jtn0123/compresso/commit/0c63878721bdbc42885003e988071b6bc1b9e5ba))
* **lint:** enable isort, pyupgrade, PIE rules and auto-fix 1046 violations ([03a7ce7](https://github.com/jtn0123/compresso/commit/03a7ce7887b6a218f0d8c3e5217f467b6e572918))
* **lint:** enable security (S/bandit) rules with test ignores ([eaf3382](https://github.com/jtn0123/compresso/commit/eaf3382933191368e2d3fe3630d52c8c7a53ca38))
* **lint:** enable SIM (simplify) and T20 (no-print) rules, fix 175 violations ([830424b](https://github.com/jtn0123/compresso/commit/830424b959fcb3b5518566bbb9fd359d9bdb4f76))
* **lint:** enforce ruff format in CI, sync pre-commit versions ([d21ab41](https://github.com/jtn0123/compresso/commit/d21ab418db4256ae4d09fbcc632e86fc215bd211))
* **lint:** make mypy type checking blocking in CI ([a8b19e6](https://github.com/jtn0123/compresso/commit/a8b19e64f3553c344a53ff688954b57bc8e0d442))
* **ui:** Modern UI redesign with palette switching and dense layout ([#53](https://github.com/jtn0123/compresso/issues/53)) ([ea1b655](https://github.com/jtn0123/compresso/commit/ea1b655c97ac129e43047e96a0040ee692dbb70a))
* **ui:** modern UI redesign with palette switching, icon-rail sidebar, and dense layout ([e89ecfd](https://github.com/jtn0123/compresso/commit/e89ecfd4f0898ab3b1dc9edd6f01669b39562f55))

## [1.7.1](https://github.com/jtn0123/compresso/compare/v1.7.0...v1.7.1) (2026-03-26)


### Bug Fixes

* add autoprefixer as explicit devDependency for @quasar/app-webpack v4 ([bc622ff](https://github.com/jtn0123/compresso/commit/bc622ff1df11953098612ee68fb6c39115f16c7c))
* migrate to @quasar/app-webpack v4 project structure ([d2bc549](https://github.com/jtn0123/compresso/commit/d2bc549ce44623e00458c3a2d647694a6f131cf6))

# [1.7.0](https://github.com/jtn0123/compresso/compare/v1.6.0...v1.7.0) (2026-03-26)


### Bug Fixes

* add shell: bash to pytest step for Windows CI compatibility ([297c76f](https://github.com/jtn0123/compresso/commit/297c76f1da3a83c98d0f2fe5b0a6c4637a07022f))
* improve metadata DB fixture for Windows SqliteQueueDatabase timing ([3a7575d](https://github.com/jtn0123/compresso/commit/3a7575d2a57f151666080572127914bdd7dd2938))
* resolve all pre-existing Windows test failures ([6757ebf](https://github.com/jtn0123/compresso/commit/6757ebf7385ddb5d336be5b902e49a608d7640bd))
* resolve remaining Windows path assertion failures ([ab3d1f4](https://github.com/jtn0123/compresso/commit/ab3d1f4d413147b403b4a5473a6d6861565aa0f5))


### Features

* multi-platform support — macOS/Windows/Linux paths, GPU backends, FFmpeg validation, CI matrix ([0727dab](https://github.com/jtn0123/compresso/commit/0727dab9febb64b23a427b03377fc5bab5db23ff))

# [1.6.0](https://github.com/jtn0123/compresso/compare/v1.5.0...v1.6.0) (2026-03-26)


### Bug Fixes

* address all remaining CodeRabbit review comments ([62f8d82](https://github.com/jtn0123/compresso/commit/62f8d82453d5d2aa225a491c5758ab0b54697989))
* address remaining CodeQL alerts — XSS sanitization and URL check ([0656aa6](https://github.com/jtn0123/compresso/commit/0656aa6717bbb41bbe8a5eaae7356dda9008747d))
* resolve CI failures — upgrade requests for CVE, fix CodeQL security alerts ([447bb10](https://github.com/jtn0123/compresso/commit/447bb10a94d05dd2c9017b6426a1c52ff7e31947))
* resolve CI lint errors and address CodeRabbit review feedback ([36cd63d](https://github.com/jtn0123/compresso/commit/36cd63d13a01304f6f96dd8ddcbb9eb811ce0806))


### Features

* comprehensive polish pass — GPU dashboard, ETA, notifications, and quality improvements ([f60653a](https://github.com/jtn0123/compresso/commit/f60653a0cae73ab9ee247b45613f267520046832))

# [1.5.0](https://github.com/jtn0123/compresso/compare/v1.4.0...v1.5.0) (2026-03-25)


### Features

* task retry, keyboard shortcuts, staging cleanup, onboarding wizard ([#41](https://github.com/jtn0123/compresso/issues/41)) ([84a9f1a](https://github.com/jtn0123/compresso/commit/84a9f1a5c358f364d4757fa374176a9702443176))

# [1.4.0](https://github.com/jtn0123/compresso/compare/v1.3.1...v1.4.0) (2026-03-24)


### Bug Fixes

* mock compute_quality_scores in staging tests to prevent side effects ([7e63b3f](https://github.com/jtn0123/compresso/commit/7e63b3f5acaa115d8e198613e20e0370b5ebbe3b))


### Features

* toast notifications, postprocessor rollback, and VMAF/SSIM quality scores ([be389b8](https://github.com/jtn0123/compresso/commit/be389b8f28a9e7b1f3e5fcc546adc4e97f72f6b3)), closes [hi#impact](https://github.com/hi/issues/impact)

## [1.3.1](https://github.com/jtn0123/compresso/compare/v1.3.0...v1.3.1) (2026-03-24)


### Bug Fixes

* replace silent except-pass with diagnostic logging ([413fe3d](https://github.com/jtn0123/compresso/commit/413fe3d8d1e8c6e1f710a1da087b2104766d6649))

# [1.3.0](https://github.com/jtn0123/compresso/compare/v1.2.3...v1.3.0) (2026-03-24)


### Features

* encoding speed analytics, new codecs & UI polish ([#34](https://github.com/jtn0123/compresso/issues/34)) ([3bd4602](https://github.com/jtn0123/compresso/commit/3bd460273240770bad04d36a2206f1868494984f))

## [1.2.3](https://github.com/jtn0123/compresso/compare/v1.2.2...v1.2.3) (2026-03-21)


### Bug Fixes

* application polish pass — security, bugs, UX, and documentation ([#32](https://github.com/jtn0123/compresso/issues/32)) ([bfe2172](https://github.com/jtn0123/compresso/commit/bfe2172e2b1106df7fc88d579a2b7e4c891bdab4))

## [1.2.2](https://github.com/jtn0123/compresso/compare/v1.2.1...v1.2.2) (2026-03-21)


### Bug Fixes

* patch minimatch and tar CVEs in Docker base image ([a2c52bb](https://github.com/jtn0123/compresso/commit/a2c52bb0fd4a70e54501a45454798f7b89256254))

## [1.2.1](https://github.com/jtn0123/compresso/compare/v1.2.0...v1.2.1) (2026-03-21)


### Performance Improvements

* CI speedup with test sharding, native multi-arch Docker, and base image ([3734b30](https://github.com/jtn0123/compresso/commit/3734b309589efb3ea542fc7840a14212541da622))

# [1.2.0](https://github.com/jtn0123/compresso/compare/v1.1.0...v1.2.0) (2026-03-19)


### Features

* add clear logs button to Application Logs dialog ([568ca26](https://github.com/jtn0123/compresso/commit/568ca261bb096df79186af644f5879030bb78b1b))

# [1.1.0](https://github.com/jtn0123/compresso/compare/v1.0.0...v1.1.0) (2026-03-19)


### Features

* new Compresso visual identity ([e51bded](https://github.com/jtn0123/compresso/commit/e51bded6c5bdf04e47a3d9deccd48339689fdf96)), closes [#1a6b4a](https://github.com/jtn0123/compresso/issues/1a6b4a) [#22916a](https://github.com/jtn0123/compresso/issues/22916a) [#e8a525](https://github.com/jtn0123/compresso/issues/e8a525) [#7c5cbf](https://github.com/jtn0123/compresso/issues/7c5cbf) [#13291f](https://github.com/jtn0123/compresso/issues/13291f) [#1a3d2d](https://github.com/jtn0123/compresso/issues/1a3d2d)

# 1.0.0 (2026-03-19)


### Bug Fixes

* address bugs in foreman and filetest modules ([da88248](https://github.com/jtn0123/compresso/commit/da882483db80c3e4552138f64b9bb9dc16536c22))
* **deploy:** add Docker HEALTHCHECK, fix metadata URL and Node version ([5af89dc](https://github.com/jtn0123/compresso/commit/5af89dcc323dd7bfcead7080a5863a6aa93e55f9))
* **deps:** pin all dependencies to exact versions ([1d49416](https://github.com/jtn0123/compresso/commit/1d49416f3b117ec5d0f0b7a76f07a87159746b30))
* **deps:** pin loose dependencies ([37bc028](https://github.com/jtn0123/compresso/commit/37bc0285574b2fe6222b8008f04a7f2a77a3ca17))
* **test:** fix pytest discovery and add coverage tracking ([2f68b7b](https://github.com/jtn0123/compresso/commit/2f68b7b69205dd541865322aed8f089f84c77fbf))


### Features

* add approval workflow for reviewing transcodes before replacing originals ([df3a6de](https://github.com/jtn0123/compresso/commit/df3a6de09a594f6be99ddf3f6b5b20f85a01a535))
* rebrand Unmanic → Compresso ([0013ac3](https://github.com/jtn0123/compresso/commit/0013ac3aa0c9f43f51eb396cbf1244985b1ea56e))

# 1.0.0 (2026-03-19)


### Bug Fixes

* address bugs in foreman and filetest modules ([da88248](https://github.com/jtn0123/compresso/commit/da882483db80c3e4552138f64b9bb9dc16536c22))
* **deploy:** add Docker HEALTHCHECK, fix metadata URL and Node version ([5af89dc](https://github.com/jtn0123/compresso/commit/5af89dcc323dd7bfcead7080a5863a6aa93e55f9))
* **deps:** pin all dependencies to exact versions ([1d49416](https://github.com/jtn0123/compresso/commit/1d49416f3b117ec5d0f0b7a76f07a87159746b30))
* **deps:** pin loose dependencies ([37bc028](https://github.com/jtn0123/compresso/commit/37bc0285574b2fe6222b8008f04a7f2a77a3ca17))
* **test:** fix pytest discovery and add coverage tracking ([2f68b7b](https://github.com/jtn0123/compresso/commit/2f68b7b69205dd541865322aed8f089f84c77fbf))

# Changelog

All notable changes to this project will be documented in this file.

This changelog is automatically generated by [semantic-release](https://github.com/semantic-release/semantic-release).
For releases prior to automated versioning, entries were written manually.

## [0.4.0](https://github.com/jtn0123/compresso/releases/tag/0.4.0) — Fork Baseline

This release represents the fork's divergence from upstream Compresso, consolidating all
enhancements made to the `jtn0123/compresso` fork.

### Features

- **Compression analytics**: distribution analytics APIs and per-container tracking
- **Quality metrics**: VMAF/SSIM quality metrics integrated into the preview engine
- **A/B preview engine**: side-by-side comparison of original vs processed media
- **File info API**: ffprobe utilities and file information endpoint
- **Health check system**: application health monitoring endpoint
- **Paywalls removed**: all premium gates removed from the fork

### Bug Fixes

- Fix `NameError` bug, path traversal issue, and resource leaks
- Fix `datetime` deprecation warnings in `json_log_formatter` usage
- Fix test infrastructure and re-enable skipped integration tests

### Improvements

- Modernized deployment tooling with startup hardening and confidence checks
- Vendored frontend build into release pipeline
- Expanded test coverage (postprocessor tests, backend fixes)
- Updated frontend submodule to point at fork with new UI features
- Adopted Node 24 and refactored packaging data
- Documentation polish: fork identity, canonical compose, operator onboarding
