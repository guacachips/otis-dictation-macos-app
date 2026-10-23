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

Menu bar → Microphone: System Default (follows macOS) or a specific input, saved by name.

Menu bar → Transcription Settings:
- **Deployment**: Cloud (API), Local (Whisper) or Local Server (MLX)
- **Cloud Provider**: Gemini or Mistral
- **Language**: French/English (Whisper models only; Voxtral detects it)
- **Model**: Tiny/Base/Turbo (Whisper) or Voxtral 4-bit/Whisper Turbo (Local Server)
- **Live Transcription** (Local Server + Voxtral 4-bit): text appears in a floating panel while you talk; stops on menu Stop or after 10 s of silence

**Note**: Whisper models auto-download on first use to `~/.cache/whisper/`

**Local Server** needs a running `otis-speech-server` (`conda activate otis-speech-server; otis-speech-server`). Address: `server_url` in `~/.otis-dictation-macos-app/transcription.json` (default `http://127.0.0.1:6847`).

## Debug Mode

```bash
DEBUG=true python app.py
```

Shows performance metrics, token costs, and keeps audio files in `~/.otis-dictation-macos-app/temp/` for analysis.
