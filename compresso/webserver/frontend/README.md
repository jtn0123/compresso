# Compresso Web frontend

The frontend user interface for [Compresso](https://github.com/jtn0123/compresso),
vendored directly into the main repository (no submodules).

Built with Vue 3 + Quasar (Vite).

---

## Requirements

Node.js 24 is the supported build baseline (see the repository root `.nvmrc`);
Node 22 also works per the `engines` field in `package.json`.

## Install the dependencies

```bash
npm ci
```

## Development

### Start the app in development mode (hot-code reloading, error reporting, etc.)

```bash
npm run serve
```

### Lint the files

```bash
npm run lint
```

### Run tests

```bash
npm run test            # vitest unit tests
npm run test:e2e        # mocked Playwright journeys (builds first)
npm run test:e2e:live   # Playwright against a live backend
```

### Build the app for production

```bash
npm run build:publish
```

## License and Contribution

This project is licensed under GPL-3.0-only (see the `LICENSE` file in this
directory and at the repository root). Portions of this directory retain the
original author's earlier MIT permission notice, reproduced below; see the
root `THIRD_PARTY_NOTICES.md` and `LICENSES/` for details.

Copyright (C) Josh Sunnex - All Rights Reserved

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

This project contains libraries imported from external authors.
Please refer to the source of these libraries for more information on their
respective licenses.

See [CONTRIBUTING.md](../../../docs/CONTRIBUTING.md) to learn how to contribute
to Compresso.
