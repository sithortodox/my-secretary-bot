# Changelog

## [1.0.0] - 2025-01-04

### Added
- 30-day conversation analysis for richer LLM context
- Escalation system for urgent messages
- Multimedia support (photos, stickers, GIF)
- Delayed response feature (15 minutes)
- Custom model input in admin panel
- Message length limiting (4000 chars)
- Safe callback data parsing with validation
- Environment variable validation at startup
- Try/except blocks for critical DB operations

### Changed
- Removed billing/subscription system
- Removed daily message limits
- Made LLM provider-agnostic (works with any OpenAI-compatible API)
- Updated security: token protection, .gitignore improvements
- Excluded sensitive data from logs

### Removed
- Billing handlers and payment logic
- Trial/subscription checks
- Hardcoded model names (mimo-v2.5, mimo-v2-flash)
- RavelioBot references from README

### Fixed
- `content is null` MiMo error
- `high risk` content rejection
- Token exposure in bot.get_me() calls

## [0.9.0] - 2025-01-03

### Added
- Basic auto-reply functionality
- Contact notes and AI notes
- Offline mode
- Scheduled messages
- Admin panel
- Owner admin panel
- Multimedia support (basic)
