# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-10-16

### Added
- Local Server (MLX) engine: transcription through a running `otis-speech-server` (requires otis-scribe-engine 0.4.0). Transcription Settings offers a third deployment choice, then Voxtral 4-bit or Whisper Turbo; the language question is only asked for Whisper
- `server_url` (default `http://127.0.0.1:6847`) and `server_model` in `transcription.json`; existing settings files load unchanged
- "Speech server not running" notification with the start command when the server is not reachable
- Telemetry records the language for local server Whisper models (Voxtral detects it, so none is recorded)

## [0.4.1] - 2026-10-16

### Added
- Microphone submenu: System Default or a specific input device, saved by name in `config.json`
- "Microphone problem" notification when the selected input delivers no signal

### Changed
- Menu bar updates from the recording thread are posted to the main thread

### Fixed
- Recordings came from a stale microphone after the macOS default input changed (requires otis-scribe-engine 0.3.2)
- Silent recordings no longer reach the transcriber (Whisper hallucinated text on them)
- Debug token output crashed with `KeyError: 'input_cost'` and discarded the transcription
- Manual stop no longer saves the recording twice

## [0.4.0] - 2025-10-06

### Added
- Mistral API transcription support with improved settings UX
- Settings reset button and nested menu structure
- Default to Whisper for better out-of-box experience

### Changed
- Removed cost_total from database schema (server-side calculation)
- Time values now stored with 2 decimal precision
- Menu item renamed to "Copy Last Transcription"
- Copy Last Transcription now fetches from database if no current session

### Fixed
- Semaphore leak warning on quit by cleaning up recording threads

### Removed
- Database migration code (clean schema for new users)

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

[0.5.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.5.0
[0.4.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.4.0
[0.3.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.3.0
[0.2.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.2.0
[0.1.0]: https://github.com/guacachips/otis-dictation-macos-app/releases/tag/v0.1.0
