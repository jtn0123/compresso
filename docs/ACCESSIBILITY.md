# Accessibility

Compresso's UI is checked with [axe-core](https://github.com/dequelabs/axe-core)
through Playwright. This file records what is enforced today and what is still
outstanding, so the gap is tracked rather than implied.

## What CI enforces

`compresso/webserver/frontend/tests/e2e/compresso-smoke.spec.js` runs an axe scan
on every route in `MAIN_ROUTES` plus the open task dialog, and asserts:

- **zero `critical` violations** — unconditional;
- **no `serious` violation whose rule is not in `KNOWN_SERIOUS_RULES`** — the
  allowlist is a ratchet, so a new class of serious violation fails the build
  while the known ones stay visible;
- every actionable control on the dashboard carries an accessible name;
- the pending-tasks dialog is reachable by keyboard, scans clean while open,
  closes on `Escape`, and returns focus to the page.

Run it locally with:

```bash
cd compresso/webserver/frontend && npm run test:e2e
```

## Fixed (2026-08-01)

The first full sweep across the app surfaced these; all are resolved:

| Rule | Impact | Cause | Fix |
|---|---|---|---|
| `button-name` | critical | Icon-only buttons relied on `q-tooltip`, which is not an accessible name | `aria-label` on the dashboard expand buttons, drawer toggle, logo link, sidebar pin, notification dismiss, theme switch, and the dialog back/forward/close controls. `CompressoListActionButton` now derives `aria-label` from its `tooltip` prop, which names every list action button in the app at once |
| `aria-required-children` | critical | Navigation drawers rendered `role="list"` (Quasar's default for `q-list`) while interleaving links with section headings and separators | The drawers are navigation menus, not lists; `role="none"` on those `q-list`s drops a contract the markup cannot satisfy. The `q-drawer` landmark still provides structure and the links stay individually accessible |
| `aria-dialog-name` | serious | Quasar renders `role="dialog" aria-modal="true"` with no accessible name | The three shared dialog shells bind `aria-label` to their existing `title` prop |
| Escape did not close any dialog off desktop | — | Quasar's `addEscapeKey` is a no-op unless `Platform.is.desktop`, so no `QDialog` reacted to Escape on a touch-capable viewport — which includes a touchscreen laptop, a tablet with a keyboard, and a desktop browser in responsive mode | [`useEscapeDismiss`](../compresso/webserver/frontend/src/composables/useEscapeDismiss.ts) registers a fallback **only** where Quasar declined to, so desktop keeps Quasar's own handling and nothing fires twice. Dialogs stack, and only the top one dismisses |

## Known and outstanding

`KNOWN_SERIOUS_RULES` in the spec currently allows:

| Rule | Why it is still open |
|---|---|
| `color-contrast` | Fails in shared topbar/sidebar tokens (`.topbar-subtitle`, `.topbar-meter-label`, `.sidebar-brand-sub`, `.nav-section-label`, and Quasar's `text-grey` captions). Fixing it means changing design tokens, which is a visual change that belongs in its own review |
| `aria-toggle-field-name` | Quasar's own `q-table` row-selection checkboxes render without a label. Needs a header/body cell slot override per table |
| `aria-input-field-name` | Quasar's `q-slider` renders without a label. Needs a wrapper or `aria-label` at each use site |

Remove an entry from the allowlist as soon as its rule is fixed; the list must
only ever shrink.

Also outstanding, and **not** currently asserted:

- **Semantic headings.** Pages style headings with Quasar's `text-h6` classes
  rather than `<h1>`–`<h6>`, so no route exposes a heading to a screen reader.
  A sweep asserting `getByRole('heading')` fails on every page today. Fixing it
  means adding real heading elements across all pages.
- **Route coverage.** `MAIN_ROUTES` covers dashboard, approval queue, deployment
  readiness, and plugin settings — the routes the spec's API mocks fully serve.
  Compression, health, history, library settings, worker settings, and
  notification settings need `installApiMocks` extended (for example
  `compression/stats` is unmocked) before they can join the sweep.
- **Screen-reader and keyboard-only passes.** Everything above is automated
  checking. axe catches roughly a third of real accessibility problems; no
  manual assistive-technology pass has been done.
