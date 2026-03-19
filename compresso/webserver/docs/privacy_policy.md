# Changelog

All notable changes to this project will be documented here.

## [1.1.0] - 2026-03-18

### Added
- **Approval Workflow** — transcoded files now wait for review before replacing originals
  - Settings UI toggle to enable/disable approval mode
  - Approval Queue page with summary cards, codec metadata, color coding
  - Detail dialog with side-by-side comparison and quality preview integration
  - Reject dialog with clear Discard vs Requeue options
  - Context-aware empty state
  - Auto-refresh with selection preservation
  - Mobile-responsive layout
- **Codec & Resolution Metadata** — approval queue shows source and transcoded codec/resolution via ffprobe
- **Integration Tests** — real-file tests for staging, approve, reject, and auto-mode flows

### Changed
- Footer now shows version only (removed copyright)
- HelpSupportDialog no longer fires API calls on page load (only when opened)
- Removed non-English language files (English only)

### Fixed
- Missing `py-cpuinfo` dependency causing system config error toast on every page load
- Version file now shows actual version instead of "UNKNOWN"
- API paths in ApprovalQueue use `getCompressoApiUrl()` consistently
- Settings toggle properly distinguishes `null` (loading) from `false` (loaded)

## [1.0.0] - 2026-03-15

### Added
- Initial fork from Compresso
- Compression Dashboard with per-file stats, codec/resolution charts, timeline
- A/B Preview comparison with side-by-side and slider modes
- Health Check system
- Rate limiting for API endpoints
- Safe defaults and startup validation
