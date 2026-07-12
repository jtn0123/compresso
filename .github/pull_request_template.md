## Summary

- 

## Test Plan

- [ ] I have the right to submit this work under GPL-3.0-only and preserved existing file-level notices.
- [ ] `python3.13 -m pytest tests/unit -q --maxfail=1 --disable-warnings`
- [ ] `cd compresso/webserver/frontend && npm ci`
- [ ] `cd compresso/webserver/frontend && npm run test -- --run`
- [ ] `cd compresso/webserver/frontend && npm run lint`
- [ ] `cd compresso/webserver/frontend && npx vitest run --coverage`
- [ ] `cd compresso/webserver/frontend && npm run build:publish`
- [ ] `cd compresso/webserver/frontend && npm run test:e2e`
- [ ] `bash scripts/verify-local.sh fast`
- [ ] `bash scripts/verify-local.sh full` (required before merge/release; note intentional skips)

## Notes

- 
