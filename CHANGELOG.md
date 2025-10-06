# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-10-05

### Added
- Transcription history with SQLite database (privacy-first 2-table architecture)
- History UI submenu showing last 15 transcriptions with click-to-copy
- Telemetry opt-in/out system (separate from transcription text)
- "Clear History" feature (keeps telemetry for analytics)
- Database sync tracking with `synced_at` column for future server sync
- Code principles documentation in AGENTS.md

### Changed
- Settings now managed at app-level (migrated from library)
- Switched to local development mode in requirements.txt

## [0.2.0] - 2025-10-05

### Added
- OpenAI Whisper integration with automatic model downloads
- Language support (French/English) for Whisper
- Cleaner settings UI with model selection dialog

### Changed
- Migrated from previous transcription backend to openai-whisper
- Improved UI feedback and user experience

## [0.1.0] - 2025-10-05

### Added
- Initial macOS menu bar voice-to-text application
- VAD (Voice Activity Detection) with auto-stop recording
- Multi-backend transcription support (Gemini, Whisper)
- Integration with otis-scribe-engine library
- Debug mode with performance stats and token usage
- macOS notification system integration
- Clipboard auto-copy functionality
- Environment-based configuration (.env support)

[0.3.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.3.0
[0.2.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.2.0
[0.1.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.1.0
