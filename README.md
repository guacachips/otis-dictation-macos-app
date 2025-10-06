# Otis Dictation

macOS menu bar voice-to-text app with VAD auto-stop.

## Setup

```bash
pip install -r requirements.txt
```

**For Cloud APIs** (optional):
```bash
cp .env.example .env
# Add GOOGLE_API_KEY and/or MISTRAL_API_KEY to .env
```

## Run

```bash
python app.py
```

## Settings

Menu bar → Transcription Settings:
- **Deployment**: Cloud (API) or Local (Whisper)
- **Cloud Provider**: Gemini or Mistral
- **Language**: French/English (Whisper only)
- **Model**: Tiny/Base/Turbo (Whisper only)

**Note**: Whisper models auto-download on first use to `~/.cache/whisper/`

## Debug Mode

```bash
DEBUG=true python app.py
```

Shows performance metrics, token costs, and keeps audio files in `~/.otis-dictation-macos-app/temp/` for analysis.
