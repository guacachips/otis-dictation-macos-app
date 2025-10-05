# Otis Dictation 🎤

A macOS menu bar app for voice-to-text transcription with Voice Activity Detection (VAD) and multiple transcription backends.

## Features

- **Menu bar integration** - Always accessible from your menu bar
- **Automatic recording stop** - VAD detects when you finish speaking
- **Manual override** - Click to stop recording anytime
- **Multiple transcription backends**:
  - **Gemini API** (cloud, fast, accurate, small cost)
  - **Whisper Local** (offline, private, free, requires model download)
- **Auto-copy to clipboard** - Transcription instantly available for pasting
- **Configurable settings** - Choose your preferred transcription engine and model
- **Performance metrics** - See realtime factor and transcription speed

## Setup

### 1. Install Dependencies

```bash
# This will install the otis-scribe-engine library and app dependencies
pip install -r requirements.txt
```

### 2. Configure API Key (for Gemini)

If using Gemini transcription:

```bash
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

Get a Gemini API key: https://aistudio.google.com/apikey

### 3. Download Whisper Models (for local transcription)

If using Whisper transcription:

**Option A:** Use the app menu:
- Run the app: `python app.py`
- Click menu bar icon → "Download Whisper Models"
- Wait for download to complete (~2-3GB)

**Option B:** Use the command line:
```bash
python -c "from otis_scribe_engine.scripts.download_models import main; main()"
```

## Usage

### Start the App

```bash
python app.py
```

### Recording

1. Click the 🎤 icon in your menu bar
2. Select "Start Recording"
3. Speak into your microphone
4. **Automatic stop**: Recording stops automatically when you pause for 2.5 seconds
5. **Manual stop**: Click "Stop Recording" to stop immediately

### Settings

Click menu bar icon → "Transcription Settings"

- **Gemini (Cloud)**: Fast, accurate, requires internet and API key (~$0.0001 per transcription)
- **Whisper (Local)**: Free, private, offline, requires downloaded models
  - **Tiny**: Fastest, good accuracy (~150MB)
  - **Base**: Balanced speed and accuracy (~290MB)
  - **Large-Turbo**: Best accuracy, slower (~1.5GB)

Settings are persisted to `~/.otis-scribe-engine/config.json`

### View Transcription

- Transcription automatically copied to clipboard
- Click "Show Last Transcription" to view and copy again

## App States

- 🎤 **Idle** - Ready to record
- 🔴 **Recording** - Listening to your voice (VAD active)
- ⏳ **Transcribing** - Processing audio

## macOS Permissions

On first run, macOS will ask for:
- **Microphone access** - Required for recording
- **Notifications** - Optional, for transcription ready alerts

## Debug Mode

Enable detailed metrics including token counting and costs:

```bash
# In .env file
DEBUG=true
```

Then run the app. You'll see:
- Audio duration
- Transcription time
- Realtime factor
- Token usage and cost (Gemini only)

## Architecture

This app uses the [otis-scribe-engine](https://github.com/guacachips/otis-scribe-engine) library for audio recording and transcription.

The library provides:
- VAD-powered audio recording
- Pluggable transcription backends
- Model management for offline operation

## Troubleshooting

**No sound recorded**
- Check System Settings → Privacy & Security → Microphone
- Ensure your microphone is selected as default input device

**API error (Gemini)**
- Verify your `GOOGLE_API_KEY` in `.env`
- Check your internet connection

**Whisper models not found**
- Run "Download Whisper Models" from the app menu
- Models are stored in `~/.otis-scribe-engine/models/whisper/`

**App not appearing in menu bar**
- Make sure Python has accessibility permissions
- Try running from terminal to see error messages

**VAD stops too quickly/slowly**
- VAD is configured with sensible defaults
- Custom configuration coming in future updates

## Storage & Privacy

**Temporary audio files**:
- Saved to `~/.otis-dictation-macos-app/temp/` during recording
- Automatically deleted after transcription completes
- Never uploaded or stored permanently
- If app crashes, leftover files can be safely deleted from this directory

**User settings**:
- Stored in `~/.otis-scribe-engine/config.json`
- Only contains your transcription preferences (engine choice, model size)
- No sensitive data stored

## Related Projects

- [otis-scribe-engine](https://github.com/guacachips/otis-scribe-engine) - Core library
- [Agent Vero](https://github.com/guacachips/agent-vero) - Full voice assistant

## License

MIT License - see LICENSE file for details
