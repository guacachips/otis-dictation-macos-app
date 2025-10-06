# AGENTS.md - Instructions for AI Coding Agents

## About This App

macOS menu bar app using `otis-scribe-engine` library for voice-to-text transcription.

## Development Setup

```bash
pip install -r requirements.txt
```

## Testing

Run the app and verify:
```bash
python app.py
# Click menu bar icon → Start Recording → Speak → Verify transcription
```

**No unit tests** - Simple UI app, test by using it.

## Code Principles

1. **Simple menu bar app** - Don't over-engineer
2. **Minimal UI** - Only essential menu items
3. **Clean error handling** - User-friendly alerts
4. **No verbose docs** - README should be <50 lines

## Key Components

- `app.py` - Main app (rumps-based menu bar UI)
- `requirements.txt` - Uses `otis-scribe-engine` library
- `.env` - Optional Gemini API key

## Dependencies

- **otis-scribe-engine** - Core library (voice recording + transcription)
- **rumps** - macOS menu bar framework
- **python-dotenv** - Environment variables

## Releasing a New Version

1. **Update version** in `setup.py` (if exists) or git tag only:
   - Patch (0.1.0 → 0.1.1): Bug fixes, UI tweaks
   - Minor (0.1.0 → 0.2.0): New features
   - Major (0.x.x → 1.0.0): Breaking changes

2. **Commit with convention**:
   ```bash
   git add .
   git commit -m "fix: ..." # or feat: or chore:
   git push
   ```

3. **Version bump commit** (no prefix):
   ```bash
   git commit -m "Bumped to VX.Y.Z"
   git push
   ```

4. **Create and push tag**:
   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```

**Commit message convention:**
- `fix:` - Bug fixes
- `feat:` - New features
- `chore:` - Maintenance/cleanup
- `docs:` - Documentation
- No prefix - Version bumps ("Bumped to VX.Y.Z")

## What NOT to Do

- ❌ Add complex settings UI
- ❌ Add features that should be in the library (otis-scribe-engine)
- ❌ Write verbose documentation
- ❌ Add menu items that don't DO anything (info-only dialogs)
- ❌ Keep debug code in production (use `self.debug` flag)

## Debug Mode

Set `DEBUG=true` in `.env`:
- Shows performance metrics
- Shows token costs (Gemini)
- **Keeps audio files** in `~/.otis-dictation-macos-app/temp/` (doesn't delete)
