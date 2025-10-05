"""Otis Dictation - macOS Menu Bar Voice Transcription App.

A voice-to-text application that lives in your macOS menu bar.
Uses VAD for automatic recording stop, supports multiple transcription backends.
"""

import os
import rumps
import threading
import subprocess
from pathlib import Path
from otis_scribe_engine import (
    AudioRecorder,
    VADConfig,
    get_transcriber,
    UserSettings
)
from otis_scribe_engine.scripts.download_models import ModelDownloader
from dotenv import load_dotenv

load_dotenv()


class OtisDictationApp(rumps.App):
    """Main menu bar application."""

    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_TRANSCRIBING = "transcribing"

    def __init__(self):
        super(OtisDictationApp, self).__init__(
            name="Otis Dictation",
            title="🎤",
            quit_button=None
        )

        self.debug = os.environ.get("DEBUG", "false").lower() == "true"
        self.state = self.STATE_IDLE
        self.current_text = ""
        self.recorder = None

        if self.debug:
            print("🔬 DEBUG MODE ENABLED - Detailed metrics active")

        self.menu = [
            rumps.MenuItem("Start Recording", callback=self.toggle_recording),
            rumps.separator,
            rumps.MenuItem("Show Last Transcription", callback=self.show_text_window),
            rumps.separator,
            rumps.MenuItem("Transcription Settings", callback=self.show_settings),
            rumps.MenuItem("Download Whisper Models", callback=self.download_models),
            rumps.separator,
            rumps.MenuItem("Quit", callback=rumps.quit_application)
        ]

    def toggle_recording(self, sender):
        """Start or stop recording based on current state."""
        if self.state == self.STATE_IDLE:
            self._start_recording()
        elif self.state == self.STATE_RECORDING:
            self._stop_recording()

    def _start_recording(self):
        """Start recording audio with VAD."""
        self.state = self.STATE_RECORDING
        self.title = "🔴"
        self.menu["Start Recording"].title = "Stop Recording"

        threading.Thread(target=self._record_with_vad, daemon=True).start()

    def _record_with_vad(self):
        """Record audio with VAD auto-stop (runs in background thread)."""
        try:
            vad_config = VADConfig(
                threshold_speech=0.5,
                silence_duration_max=2.5,
                min_speech_duration=0.5
            )

            temp_dir = Path.home() / ".otis-dictation-macos-app" / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            self.recorder = AudioRecorder(output_dir=temp_dir, vad_config=vad_config)
            audio_file, audio_duration = self.recorder.record()

            if audio_file and self.state == self.STATE_RECORDING:
                self.state = self.STATE_TRANSCRIBING
                self.title = "⏳"
                self.menu["Start Recording"].title = "Transcribing..."
                self._transcribe_audio(audio_file, audio_duration)

        except Exception as e:
            print(f"❌ Recording error: {str(e)}")
            self.state = self.STATE_IDLE
            self.title = "🎤"
            self.menu["Start Recording"].title = "Start Recording"

    def _stop_recording(self):
        """Manually stop recording (override VAD)."""
        if self.recorder and self.recorder.is_recording:
            print("\n🛑 Manual stop requested")
            self.recorder.stop_recording()

    def _transcribe_audio(self, audio_file, audio_duration):
        """Transcribe the recorded audio."""
        try:
            settings = UserSettings.load()

            if settings.transcription_engine == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY not found in environment")
                transcriber = get_transcriber("gemini", api_key=api_key, debug=self.debug)
            else:
                model_id = f"openai/whisper-{settings.whisper_model}"
                transcriber = get_transcriber("whisper", model_id=model_id, debug=self.debug)

            result = transcriber.transcribe(audio_file)
            self.current_text = result['text']
            transcription_time = result['transcription_time']

            realtime_factor = transcription_time / audio_duration if audio_duration > 0 else 0
            speed_multiplier = audio_duration / transcription_time if transcription_time > 0 else 0

            print("\n" + "="*60)
            print(f"🔧 Engine:            {settings.transcription_engine}")
            if 'model' in result:
                print(f"📦 Model:             {result['model']}")
            print(f"🎙️  Audio Duration:    {audio_duration:.2f}s")
            print(f"⏱️  Transcription Time: {transcription_time:.2f}s")
            print(f"📊 Realtime Factor:   {realtime_factor:.2f}x")
            print(f"🚀 Speed:             {speed_multiplier:.1f}x faster than audio")

            if self.debug and 'tokens' in result:
                tokens = result['tokens']
                print(f"\n💰 TOKEN USAGE:")
                print(f"   Input:  {tokens['total_tokens']:,} tokens (${tokens['input_cost']:.6f})")
                print(f"   Output: {tokens['output_tokens']:,} tokens (${tokens['output_cost']:.6f})")
                print(f"   Total:  ${tokens['total_cost']:.6f}")
                print(f"   Efficiency: {tokens['total_tokens']/audio_duration:.0f} tokens/second")

            print(f"\n✅ Transcription: {self.current_text}")
            print("="*60 + "\n")

            preview = self.current_text[:100] + "..." if len(self.current_text) > 100 else self.current_text
            self._send_notification("Transcription Ready", preview)

        except Exception as e:
            print(f"❌ Transcription error: {str(e)}")
            self.current_text = f"Error: {str(e)}"
            self._send_notification("Transcription Error", str(e)[:100])

        finally:
            if audio_file and Path(audio_file).exists():
                try:
                    Path(audio_file).unlink()
                    print(f"🗑️  Cleaned up temporary audio file")
                except Exception as e:
                    print(f"⚠️  Failed to delete temp file: {e}")

            self.state = self.STATE_IDLE
            self.title = "🎤"
            self.menu["Start Recording"].title = "Start Recording"

    def show_settings(self, sender):
        """Show transcription settings dialog."""
        settings = UserSettings.load()

        current_engine = settings.transcription_engine
        current_model = settings.whisper_model

        engine_choice = rumps.alert(
            title="Transcription Settings",
            message="Choose transcription engine:",
            ok="Gemini (Cloud)",
            cancel="Whisper (Local)"
        )

        if engine_choice == 1:
            settings.transcription_engine = "gemini"
            settings.save()
            rumps.alert("Settings Saved", "Using Gemini API for transcription")
        else:
            settings.transcription_engine = "whisper"

            model_choice = rumps.alert(
                title="Whisper Model",
                message="Choose Whisper model size:",
                ok="Tiny (Fastest)",
                cancel="More Options"
            )

            if model_choice == 1:
                settings.whisper_model = "tiny"
            else:
                model_choice_2 = rumps.alert(
                    title="Whisper Model",
                    message="Choose Whisper model:",
                    ok="Base (Balanced)",
                    cancel="Large-Turbo (Best)"
                )
                settings.whisper_model = "base" if model_choice_2 == 1 else "large-turbo"

            settings.save()
            rumps.alert("Settings Saved", f"Using Whisper ({settings.whisper_model}) for transcription")

    def download_models(self, sender):
        """Download Whisper models for offline use."""
        response = rumps.alert(
            title="Download Whisper Models",
            message="This will download Whisper models for offline transcription.\n\nThis may take several minutes and requires ~2-3GB disk space.\n\nProceed?",
            ok="Download",
            cancel="Cancel"
        )

        if response != 1:
            return

        def download_in_background():
            try:
                rumps.notification(
                    title="Otis Dictation",
                    subtitle="Downloading models...",
                    message="This may take several minutes"
                )

                downloader = ModelDownloader()
                results = downloader.download_all_models()

                all_success = all(results.values())
                if all_success:
                    rumps.notification(
                        title="Otis Dictation",
                        subtitle="Download Complete",
                        message="All Whisper models ready for offline use"
                    )
                else:
                    rumps.notification(
                        title="Otis Dictation",
                        subtitle="Download Incomplete",
                        message="Some models failed. Check terminal for details."
                    )
            except Exception as e:
                rumps.notification(
                    title="Otis Dictation",
                    subtitle="Download Failed",
                    message=str(e)[:100]
                )

        threading.Thread(target=download_in_background, daemon=True).start()

    def show_text_window(self, sender):
        """Show the transcription text and copy to clipboard."""
        if not self.current_text:
            rumps.alert("No Transcription", "No transcription available yet. Record something first!")
            return

        self._copy_to_clipboard(self.current_text)

        preview = self.current_text if len(self.current_text) <= 500 else self.current_text[:500] + "..."

        rumps.alert(
            title="Transcription (Copied to Clipboard ✓)",
            message=preview,
            ok="Done"
        )

    def _send_notification(self, title, message):
        """Send macOS notification using osascript."""
        safe_message = message.replace('"', "'").replace('\\', '').replace('\n', ' ')
        safe_title = title.replace('"', "'").replace('\\', '').replace('\n', ' ')

        subprocess.run([
            'osascript', '-e',
            f'display notification "{safe_message}" with title "{safe_title}"'
        ], capture_output=True)

    def _copy_to_clipboard(self, text):
        """Copy text to macOS clipboard using pbcopy."""
        process = subprocess.Popen(
            ['pbcopy'],
            stdin=subprocess.PIPE,
            close_fds=True
        )
        process.communicate(text.encode('utf-8'))
        print(f"📋 Copied to clipboard: {len(text)} characters")


if __name__ == "__main__":
    app = OtisDictationApp()
    app.run()
