# Debugging And Optimization Baseline

This pass focuses on the dashboard live-update path without changing the public REST or websocket contract.

## Current Validation Commands

- `pytest tests/unit -q`
- `pytest tests/unit -q --durations=25`
- `ruff check compresso/ tests/`
- `mypy compresso/webserver/websocket.py compresso/webserver/api_v2/base_api_handler.py compresso/webserver/api_v2/system_api.py compresso/libs/system.py --ignore-missing-imports --follow-imports=silent --no-error-summary`
- `cd compresso/webserver/frontend && npm run lint && npm run build:publish`

## Observed Hotspots

- `CompressoWebsocketHandler` pushed full worker, task, and message payloads on fixed loops even when data was unchanged.
- Dashboard websocket listeners were registered against the current socket instance only, so reconnects could lose page-specific subscriptions.
- `MainDashboard.vue` rebuilt the entire worker progress object for every live update, increasing render churn on busy systems.
- Test static-analysis debt was concentrated in unused imports/variables and a few structural issues, while source lint was already green.

## Pass Deliverables

- Suppress duplicate websocket payloads while preserving existing message types.
- Rebind registered frontend websocket listeners across reconnects and clean them up on page teardown.
- Reduce dashboard recomputation by updating worker state in place and batching worker updates to the next animation frame.
- Enforce `ruff` on source and tests, plus a scoped `mypy` gate for the live dashboard/system-status path.
