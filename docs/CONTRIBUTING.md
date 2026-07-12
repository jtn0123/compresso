# Contributing to Compresso

The following is a set of guidelines for contributing to the project,
definitely not rules. Use your best judgment, and feel free to suggest changes.

#### Table Of Contents

[How Can I Contribute?](#how-can-i-contribute)
  * [Reporting Bugs](#reporting-bugs)
  * [Suggesting New Features](#suggesting-new-features)
  * [Opening Pull Requests](#opening-pull-requests)

## How Can I Contribute?

### Reporting Bugs

When you are creating a bug report, please include as many details as
possible. Have a look at the [issue template](ISSUE_TEMPLATE.md) for ideas.

> **Note:** If you find a **Closed** issue that seems like it is the same thing
> that you're experiencing, open a new issue and include a link to the original
> issue in the body of your new one.


### Suggesting New Features

You are welcome to submit ideas for new features and enhancements, just include
as many details as possible, including potential implementation options.


### Developing

See [Development Environment Guide](./DEVELOPING.md) for details on setting up a local 
development environment.


### Opening Pull Requests

Code contributions are very welcome. Contributors retain copyright in their work and,
by submitting it, agree to license the contribution under GPL-3.0-only. GPL section 11
addresses patents and does not transfer copyright. Any copyright assignment would require
a separate written agreement. See [Licensing](./LICENSING.md).

Open pull requests against `master` for release-bound work or `staging` for pre-release validation work. If you are unsure, use `master` unless a maintainer asks for `staging`.

New Python files should contain a short SPDX header with the contributor's own name:

```
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) {{YEAR}} {{YOUR_NAME}}
```

Do not replace or remove existing file-level license or copyright notices. Only submissions
that conform to this will be merged into the mainline project. This ensures
that Compresso as a project is free to grow while preserving prior grants and attribution.
of the project's owner.
