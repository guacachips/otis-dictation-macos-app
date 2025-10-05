# Otis the Scribe 🎤

A macOS menu bar app for voice-to-text transcription using Gemini AI.

## Features

- **Menu bar integration** - Always accessible from your top bar
- **One-click recording** - Click to start, click to stop
- **Gemini-powered transcription** - Accurate, multilingual transcription
- **Copy-friendly UI** - Easy text selection and clipboard copying
- **Modular design** - Ready for Whisper integration

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API key:**
   ```bash
   cp .env.example .env
   # Edit .env and add your GOOGLE_API_KEY
   ```

3. **Get Gemini API Key:**
   - Visit https://aistudio.google.com/apikey
   - Create a free API key
   - Paste it in `.env`

## Usage

1. **Start the app:**
   ```bash
   python app.py
   ```

2. **Record audio:**
   - Click the 🎤 icon in your menu bar
   - Select "Start Recording"
   - Speak into your microphone
   - Click "Stop Recording" when done

3. **View transcription:**
   - A popup window will appear automatically
   - Click "Copy to Clipboard" to copy the text
   - Or select and copy text manually

## App States

- 🎤 **Idle** - Ready to record
- 🔴 **Recording** - Actively recording your voice
- ⏳ **Transcribing** - Processing with Gemini API

## macOS Permissions

On first run, macOS will ask for microphone permissions. Click **Allow**.

## Troubleshooting

- **No sound recorded**: Check System Settings → Privacy & Security → Microphone
- **API error**: Verify your `GOOGLE_API_KEY` in `.env`
- **App not appearing**: Make sure Python has accessibility permissions

## Future Enhancements

- [ ] Local Whisper integration
- [ ] Keyboard shortcut for global access
- [ ] Auto-paste to active window
- [ ] Transcription history
# otis-the-scribe
