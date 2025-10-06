"""Otis Dictation - macOS Menu Bar Voice Transcription App.

A voice-to-text application that lives in your macOS menu bar.
Uses VAD for automatic recording stop, supports multiple transcription backends.
"""

import os
import rumps
import threading
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from otis_scribe_engine import (
    AudioRecorder,
    VADConfig,
    get_transcriber
)
from dotenv import load_dotenv
from database import TranscriptionDatabase

load_dotenv()


@dataclass
class AppSettings:
    """App-specific settings (not transcription-related)"""
    telemetry_enabled: bool = True

    @classmethod
    def get_config_path(cls) -> Path:
        return Path.home() / ".otis-dictation-macos-app" / "config.json"

    @classmethod
    def load(cls) -> 'AppSettings':
        config_file = cls.get_config_path()
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: Failed to load app settings: {e}")
        return cls()

    def save(self):
        config_dir = self.get_config_path().parent
        config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.get_config_path(), 'w') as f:
            json.dump(asdict(self), f, indent=2)


@dataclass
class TranscriptionSettings:
    """Transcription settings (app-managed persistence)"""
    transcription_engine: str = "whisper"
    whisper_model: str = "tiny"
    language: str = "fr"

    @classmethod
    def get_config_path(cls) -> Path:
        return Path.home() / ".otis-dictation-macos-app" / "transcription.json"

    @classmethod
    def load(cls) -> 'TranscriptionSettings':
        config_file = cls.get_config_path()
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: Failed to load transcription settings: {e}")
        return cls()

    def save(self):
        config_dir = self.get_config_path().parent
        config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.get_config_path(), 'w') as f:
            json.dump(asdict(self), f, indent=2)


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
        self.db = TranscriptionDatabase()

        if self.debug:
            print("🔬 DEBUG MODE ENABLED - Detailed metrics active")

        # Build dynamic history submenu
        self.history_menu = rumps.MenuItem("Transcription History")
        self._update_history_menu()

        self.settings_menu = rumps.MenuItem("Transcription Settings")
        self.settings_menu.add(rumps.MenuItem("Configure...", callback=self.show_settings))
        self.settings_menu.add(rumps.MenuItem("Reset to Defaults", callback=self.reset_settings))

        self.menu = [
            rumps.MenuItem("Start Recording", callback=self.toggle_recording),
            rumps.separator,
            rumps.MenuItem("Show Last Transcription", callback=self.show_text_window),
            self.history_menu,
            rumps.separator,
            self.settings_menu,
            rumps.MenuItem("Telemetry Settings", callback=self.show_telemetry_settings),
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
            settings = TranscriptionSettings.load()

            if settings.transcription_engine == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY not found in environment")
                transcriber = get_transcriber("gemini", api_key=api_key, debug=self.debug)
            elif settings.transcription_engine == "mistral":
                api_key = os.getenv("MISTRAL_API_KEY")
                if not api_key:
                    raise ValueError("MISTRAL_API_KEY not found in environment")
                transcriber = get_transcriber("mistral", api_key=api_key, debug=self.debug)
            else:
                model_id = f"openai/whisper-{settings.whisper_model}"
                transcriber = get_transcriber("whisper", model_id=model_id, debug=self.debug, language=settings.language)

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

            tokens_total = result.get('tokens', {}).get('total_tokens') if 'tokens' in result else None
            cost_total = result.get('tokens', {}).get('total_cost') if 'tokens' in result else None

            app_settings = AppSettings.load()
            if app_settings.telemetry_enabled:
                self.db.save_transcription(
                    text=self.current_text,
                    engine=settings.transcription_engine,
                    model=result.get('model'),
                    language=settings.language if settings.transcription_engine == "whisper" else None,
                    audio_duration=audio_duration,
                    transcription_time=transcription_time,
                    realtime_factor=realtime_factor,
                    tokens_total=tokens_total,
                    cost_total=cost_total,
                    save_telemetry=True
                )
                print("💾 Saved to history database (with telemetry)")
            else:
                self.db.save_transcription(
                    text=self.current_text,
                    save_telemetry=False
                )
                print("💾 Saved to history database (telemetry disabled)")

            self._update_history_menu()

            preview = self.current_text[:100] + "..." if len(self.current_text) > 100 else self.current_text
            self._send_notification("Transcription Ready", preview)

        except Exception as e:
            print(f"❌ Transcription error: {str(e)}")
            self.current_text = f"Error: {str(e)}"
            self._send_notification("Transcription Error", str(e)[:100])

        finally:
            # Clean up temp file unless in debug mode
            if audio_file and Path(audio_file).exists():
                if not self.debug:
                    try:
                        Path(audio_file).unlink()
                        print(f"🗑️  Cleaned up temporary audio file")
                    except Exception as e:
                        print(f"⚠️  Failed to delete temp file: {e}")
                else:
                    print(f"🔍 Debug: Audio file kept at {audio_file}")

            self.state = self.STATE_IDLE
            self.title = "🎤"
            self.menu["Start Recording"].title = "Start Recording"

    def show_settings(self, sender):
        """Show transcription settings dialog."""
        settings = TranscriptionSettings.load()

        deployment_choice = rumps.alert(
            title="Transcription Engine",
            message="Choose deployment type:",
            ok="Cloud (API)",
            cancel="Local (Whisper)"
        )

        if deployment_choice == 1:
            provider_choice = rumps.alert(
                title="Cloud Provider",
                message="Choose cloud transcription provider:",
                ok="Gemini",
                cancel="Mistral"
            )

            if provider_choice == 1:
                settings.transcription_engine = "gemini"
                settings.save()
                rumps.alert("Settings Saved", "Using Gemini API for transcription")
            else:
                settings.transcription_engine = "mistral"
                settings.save()
                rumps.alert("Settings Saved", "Using Mistral API for transcription")
        else:
            settings.transcription_engine = "whisper"

            lang_choice = rumps.alert(
                title="Language Settings",
                message="Choose transcription language for Whisper:",
                ok="French",
                cancel="English"
            )

            settings.language = "fr" if lang_choice == 1 else "en"

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
                    cancel="Turbo (Best Quality)"
                )
                if model_choice_2 == 1:
                    settings.whisper_model = "base"
                else:
                    settings.whisper_model = "large-v3-turbo"

            settings.save()
            rumps.alert("Settings Saved", f"Using Whisper ({settings.whisper_model}) for transcription in {settings.language.upper()}")

    def reset_settings(self, sender):
        """Reset transcription settings to defaults."""
        response = rumps.alert(
            title="Reset to Defaults",
            message="Reset transcription settings to defaults?\n\nDefault: Whisper (Tiny, French)",
            ok="Reset",
            cancel="Cancel"
        )

        if response == 1:
            config_file = TranscriptionSettings.get_config_path()
            if config_file.exists():
                config_file.unlink()
            rumps.alert("Settings Reset", "Transcription settings reset to defaults:\n• Engine: Whisper (Local)\n• Model: Tiny\n• Language: French")

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

    def _update_history_menu(self):
        """Update history submenu with recent transcriptions."""
        if hasattr(self.history_menu, '_menu') and self.history_menu._menu is not None:
            self.history_menu.clear()

        history = self.db.get_history(limit=15)

        if not history:
            self.history_menu.add(rumps.MenuItem("No history yet", callback=None))
        else:
            for item in history:
                from datetime import datetime, timezone
                created_at = datetime.fromisoformat(item['created_at'])
                # SQLite stores in UTC, convert to local time
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                local_time = created_at.astimezone()
                timestamp = local_time.strftime("%b %d, %H:%M")

                text_preview = item['text'][:40] + "..." if len(item['text']) > 40 else item['text']
                title = f"{timestamp} - {text_preview}"

                def make_callback(session_id):
                    return lambda sender: self._show_history_item(session_id)

                menu_item = rumps.MenuItem(title, callback=make_callback(item['id']))
                self.history_menu.add(menu_item)

            self.history_menu.add(rumps.separator)
            self.history_menu.add(rumps.MenuItem("Clear History...", callback=self._clear_history))

    def _show_history_item(self, session_id):
        """Show full transcription from history and copy to clipboard."""
        text = self.db.get_transcription(session_id)

        if text:
            self._copy_to_clipboard(text)
            preview = text if len(text) <= 500 else text[:500] + "..."
            rumps.alert(
                title="Transcription (Copied to Clipboard ✓)",
                message=preview,
                ok="Done"
            )
        else:
            rumps.alert("Error", "Transcription not found")

    def _clear_history(self, sender):
        """Clear sensitive transcription data (keep telemetry)."""
        response = rumps.alert(
            title="Clear History",
            message="Delete all transcribed text? (Telemetry data will be kept for analytics)",
            ok="Clear History",
            cancel="Cancel"
        )

        if response == 1:  # OK button clicked
            self.db.clear_sensitive_data()
            self._update_history_menu()
            rumps.alert("History Cleared", "All transcription text has been deleted. Telemetry data preserved.")

    def show_telemetry_settings(self, sender):
        """Show telemetry opt-in/opt-out settings."""
        app_settings = AppSettings.load()

        if app_settings.telemetry_enabled:
            response = rumps.alert(
                title="Telemetry Settings",
                message="Telemetry is currently ENABLED.\n\nWe collect anonymous usage data (engine, model, duration, performance) to improve the app. Your transcription text is never sent.\n\nDisable telemetry?",
                ok="Disable",
                cancel="Keep Enabled"
            )

            if response == 1:
                app_settings.telemetry_enabled = False
                app_settings.save()
                rumps.alert("Telemetry Disabled", "Usage data collection disabled. Existing telemetry data preserved for your records.")
        else:
            response = rumps.alert(
                title="Telemetry Settings",
                message="Telemetry is currently DISABLED.\n\nEnabling telemetry helps us improve performance and features. Only anonymous usage data is collected - never your transcriptions.\n\nEnable telemetry?",
                ok="Enable",
                cancel="Keep Disabled"
            )

            if response == 1:
                app_settings.telemetry_enabled = True
                app_settings.save()
                rumps.alert("Telemetry Enabled", "Thank you! Usage data collection enabled.")


if __name__ == "__main__":
    app = OtisDictationApp()
    app.run()
