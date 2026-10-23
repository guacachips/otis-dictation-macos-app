"""Otis Dictation - macOS Menu Bar Voice Transcription App.

A voice-to-text application that lives in your macOS menu bar.
Uses VAD for automatic recording stop, supports multiple transcription backends.
"""

import os
import rumps
import threading
import subprocess
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from AppKit import (
    NSBackingStoreBuffered,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSPanel,
    NSScreen,
    NSScrollView,
    NSTextView,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskUtilityWindow,
)
from Foundation import NSMakePoint, NSMakeRect, NSMakeSize
from PyObjCTools import AppHelper
from otis_scribe_engine import (
    AudioRecorder,
    AudioDeviceManager,
    DeadInputError,
    LocalServerLiveTranscriber,
    LocalServerUnavailableError,
    VADConfig,
    get_transcriber
)
from dotenv import load_dotenv
from database import TranscriptionDatabase

load_dotenv()

LIVE_MODEL = "voxtral-realtime-4bit"
# Server error codes meaning the session never ran: nothing to keep, tell the user why.
LIVE_START_ERROR_CODES = {"busy", "model_not_found", "model_not_available", "model_not_streamable",
                          "invalid_request", "shutting_down"}
SERVER_START_HINT = "Start it with: conda activate otis-speech-server; otis-speech-server"


@dataclass
class AppSettings:
    """App-specific settings (not transcription-related)"""
    telemetry_enabled: bool = True
    input_device_name: Optional[str] = None

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
    server_url: str = "http://127.0.0.1:6847"
    server_model: str = "voxtral-realtime-4bit"
    live_transcription: bool = False
    transcription_delay_ms: int = 480

    def __post_init__(self):
        # The bf16 option was dropped from the menu: settings saved with it fall back to the 4-bit model.
        if self.server_model == "voxtral-realtime-bf16":
            self.server_model = "voxtral-realtime-4bit"

    def live_supported(self) -> bool:
        return self.transcription_engine == "local-server" and self.server_model == LIVE_MODEL

    def live_enabled(self) -> bool:
        """The toggle is kept across engine changes but only applies to Local Server + Voxtral 4-bit."""
        return self.live_transcription and self.live_supported()

    def effective_language(self) -> Optional[str]:
        """Language actually applied: Voxtral detects it itself, so it only counts for Whisper models."""
        if self.transcription_engine == "whisper":
            return self.language
        if self.transcription_engine == "local-server" and self.server_model.startswith("whisper"):
            return self.language
        return None

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


class LiveTranscriptPanel:
    """Floating window with the live text (main thread only).

    Non-activating, so the app being dictated into keeps keyboard focus.
    """

    WIDTH, HEIGHT, MARGIN = 480, 220, 20

    def __init__(self):
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow
                 | NSWindowStyleMaskNonactivatingPanel | NSWindowStyleMaskResizable)
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.WIDTH, self.HEIGHT), style, NSBackingStoreBuffered, False
        )
        self.panel.setLevel_(NSFloatingWindowLevel)
        self.panel.setFloatingPanel_(True)
        self.panel.setHidesOnDeactivate_(False)
        # Closing only hides the panel: the next live session shows it again.
        self.panel.setReleasedWhenClosed_(False)

        scroll_view = NSScrollView.alloc().initWithFrame_(self.panel.contentView().bounds())
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        content_size = scroll_view.contentSize()
        self.text_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, content_size.width, content_size.height))
        self.text_view.setEditable_(False)
        self.text_view.setSelectable_(True)
        self.text_view.setVerticallyResizable_(True)
        self.text_view.setHorizontallyResizable_(False)
        self.text_view.setAutoresizingMask_(NSViewWidthSizable)
        self.text_view.textContainer().setWidthTracksTextView_(True)
        self.text_view.setTextContainerInset_(NSMakeSize(8, 8))
        scroll_view.setDocumentView_(self.text_view)
        self.panel.setContentView_(scroll_view)

        visible = NSScreen.mainScreen().visibleFrame()
        self.panel.setFrameTopLeftPoint_(NSMakePoint(
            visible.origin.x + visible.size.width - self.WIDTH - self.MARGIN,
            visible.origin.y + visible.size.height - self.MARGIN
        ))

    def show(self, title):
        self.panel.setTitle_(title)
        self.panel.orderFrontRegardless()

    def set_title(self, title):
        self.panel.setTitle_(title)

    def set_text(self, text):
        self.text_view.setString_(text)
        # setString_ resets the text attributes; labelColor follows light/dark mode.
        self.text_view.setFont_(NSFont.systemFontOfSize_(15))
        self.text_view.setTextColor_(NSColor.labelColor())
        self.text_view.scrollToEndOfDocument_(None)

    def hide(self):
        self.panel.orderOut_(None)


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

        self.live_panel = None
        self.live_mode = False
        self.live_client = None
        self._live_error = None
        self._live_lock = threading.Lock()
        self._live_text = ""
        self._live_flush_pending = False
        self._live_stop = threading.Event()
        self._live_recording_done = threading.Event()

        if self.debug:
            print("🔬 DEBUG MODE ENABLED - Detailed metrics active")

        # Build dynamic history submenu
        self.history_menu = rumps.MenuItem("Transcription History")
        self._update_history_menu()

        self.microphone_menu = rumps.MenuItem("Microphone")
        self._update_microphone_menu(refresh=False)

        self.settings_menu = rumps.MenuItem("Transcription Settings")
        self.settings_menu.add(rumps.MenuItem("Configure...", callback=self.show_settings))
        self.live_menu_item = rumps.MenuItem("Live Transcription", callback=self.toggle_live_transcription)
        self.settings_menu.add(self.live_menu_item)
        self._update_live_menu_item()
        self.settings_menu.add(rumps.MenuItem("Reset to Defaults", callback=self.reset_settings))

        self.menu = [
            rumps.MenuItem("Start Recording", callback=self.toggle_recording),
            rumps.separator,
            rumps.MenuItem("Copy Last Transcription", callback=self.show_text_window),
            self.history_menu,
            rumps.separator,
            self.microphone_menu,
            self.settings_menu,
            rumps.MenuItem("Telemetry Settings", callback=self.show_telemetry_settings),
            rumps.separator,
            rumps.MenuItem("Quit", callback=self.clean_quit)
        ]

    def clean_quit(self, sender=None):
        """Clean up resources before quitting."""
        if self.live_client:
            self.live_client.cancel()

        if self.state == self.STATE_RECORDING and self.recorder:
            print("Stopping recording before quit...")
            self.recorder.stop_recording()
            time.sleep(0.5)

        rumps.quit_application()

    def toggle_recording(self, sender):
        """Start or stop recording based on current state."""
        if self.state == self.STATE_IDLE:
            self._start_recording()
        elif self.state == self.STATE_RECORDING:
            self._stop_recording()

    def _start_recording(self):
        """Start recording audio with VAD (live transcription when enabled)."""
        self.state = self.STATE_RECORDING
        settings = TranscriptionSettings.load()
        if settings.live_enabled():
            # Set here on the main thread so a Stop click is honored even before the worker thread runs.
            self.live_mode = True
            self._live_stop.clear()
            self._live_recording_done.clear()
            self._set_status("🔴", "Stop Live Transcription")
            threading.Thread(target=self._record_live, args=(settings,), daemon=True).start()
            return

        # The panel of the last live session stays up until the next recording starts.
        self._hide_live_panel()
        self._set_status("🔴", "Stop Recording")

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

            settings = AppSettings.load()
            self.recorder = AudioRecorder(output_dir=temp_dir, device_id=settings.input_device_name, vad_config=vad_config)
            try:
                audio_file, audio_duration = self.recorder.record()
            finally:
                # The stream is closed here, so re-initializing PortAudio to list devices is safe.
                menu_data = self._microphone_menu_data(refresh=True)
                if menu_data:
                    AppHelper.callAfter(self._apply_microphone_menu, *menu_data)

            if audio_file and self.state == self.STATE_RECORDING:
                self.state = self.STATE_TRANSCRIBING
                AppHelper.callAfter(self._set_status, "⏳", "Transcribing...")
                self._transcribe_audio(audio_file, audio_duration)

        except DeadInputError as e:
            print(f"❌ Recording error: {str(e)}")
            self._send_notification(
                "Microphone problem",
                f"No signal from '{e.device_name}' (muted?). Pick another microphone in the Otis menu."
            )
            self._reset_to_idle()

        except Exception as e:
            print(f"❌ Recording error: {str(e)}")
            self._reset_to_idle()

    def _reset_to_idle(self):
        """Callable from the recording thread: AppKit changes are posted to the main thread."""
        self.state = self.STATE_IDLE
        AppHelper.callAfter(self._set_status, "🎤", "Start Recording")

    def _set_status(self, icon, label):
        self.title = icon
        self.menu["Start Recording"].title = label

    def _stop_recording(self):
        """Manually stop recording (override VAD)."""
        if self.live_mode:
            print("\n🛑 Manual stop requested")
            self._request_live_stop()
        elif self.recorder and self.recorder.is_recording:
            print("\n🛑 Manual stop requested")
            self.recorder.stop_recording()

    def _transcribe_audio(self, audio_file, audio_duration):
        """Transcribe the recorded audio."""
        try:
            settings = TranscriptionSettings.load()
            transcriber = self._create_transcriber(settings)
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
                # Debug output must never discard a successful transcription.
                try:
                    self._print_token_usage(result['tokens'], audio_duration)
                except Exception as e:
                    print(f"⚠️  Failed to print token usage: {e}")

            print(f"\n✅ Transcription: {self.current_text}")
            print("="*60 + "\n")

            tokens_total = result.get('tokens', {}).get('total_tokens') if 'tokens' in result else None

            self._save_to_history(
                self.current_text, settings, result.get('model'),
                audio_duration, transcription_time, tokens_total=tokens_total
            )
            self._send_notification("Transcription Ready", self._preview(self.current_text))

        except LocalServerUnavailableError as e:
            print(f"❌ Transcription error: {str(e)}")
            self.current_text = f"Error: {str(e)}"
            self._send_notification("Speech server not running", SERVER_START_HINT)

        except Exception as e:
            print(f"❌ Transcription error: {str(e)}")
            self.current_text = f"Error: {str(e)}"
            self._send_notification("Transcription Error", str(e)[:100])

        finally:
            self._cleanup_audio_file(audio_file)
            self._reset_to_idle()

    def _save_to_history(self, text, settings, model, audio_duration, transcription_time, tokens_total=None, error=None):
        """Save to the history database (callable from a worker thread)."""
        realtime_factor = transcription_time / audio_duration if audio_duration > 0 else 0
        if AppSettings.load().telemetry_enabled:
            self.db.save_transcription(
                text=text,
                engine=settings.transcription_engine,
                model=model,
                language=settings.effective_language(),
                audio_duration=round(audio_duration, 2),
                transcription_time=round(transcription_time, 2),
                realtime_factor=round(realtime_factor, 2),
                tokens_total=tokens_total,
                error=error,
                save_telemetry=True
            )
            print("💾 Saved to history database (with telemetry)")
        else:
            self.db.save_transcription(
                text=text,
                save_telemetry=False
            )
            print("💾 Saved to history database (telemetry disabled)")

        AppHelper.callAfter(self._update_history_menu)

    @staticmethod
    def _preview(text):
        return text[:100] + "..." if len(text) > 100 else text

    def _cleanup_audio_file(self, audio_file):
        """Delete the temp recording unless in debug mode."""
        if audio_file and Path(audio_file).exists():
            if not self.debug:
                try:
                    Path(audio_file).unlink()
                    print(f"🗑️  Cleaned up temporary audio file")
                except Exception as e:
                    print(f"⚠️  Failed to delete temp file: {e}")
            else:
                print(f"🔍 Debug: Audio file kept at {audio_file}")

    def _record_live(self, settings):
        """Record while streaming to otis-speech-server; text shows in the live panel (runs in background thread)."""
        client = LocalServerLiveTranscriber(
            base_url=settings.server_url,
            model=settings.server_model,
            transcription_delay_ms=settings.transcription_delay_ms,
            on_delta=self._on_live_delta,
            on_error=self._on_live_error,
            on_final=self._on_live_final,
            debug=self.debug
        )
        self.recorder = None
        self.live_client = client
        self._live_error = None
        with self._live_lock:
            self._live_text = ""

        try:
            client.start()
        except Exception as e:
            print(f"❌ Live transcription error: {str(e)}")
            if isinstance(e, LocalServerUnavailableError):
                self._send_notification("Speech server not running", SERVER_START_HINT)
            else:
                self._send_notification("Live transcription could not start", str(e)[:100])
            self._live_recording_done.set()
            self._end_live()
            return

        AppHelper.callAfter(self._show_live_panel)
        audio_file, audio_duration = None, 0.0
        try:
            try:
                temp_dir = Path.home() / ".otis-dictation-macos-app" / "temp"
                temp_dir.mkdir(parents=True, exist_ok=True)
                # Live sessions end on menu Stop, after 10 s of silence, or when the server ends them.
                vad_config = VADConfig(threshold_speech=0.5, silence_duration_max=10.0, min_speech_duration=0.5)
                self.recorder = AudioRecorder(
                    output_dir=temp_dir,
                    device_id=AppSettings.load().input_device_name,
                    vad_config=vad_config,
                    on_audio=client.feed
                )
                # Stop or a server error can arrive while the VAD model loads, before record() starts.
                if not self._live_stop.is_set():
                    audio_file, audio_duration = self.recorder.record()
            finally:
                self._live_recording_done.set()
                menu_data = self._microphone_menu_data(refresh=True)
                if menu_data:
                    AppHelper.callAfter(self._apply_microphone_menu, *menu_data)

        # A server error stops the recorder early, so the recording may be empty or all zeros:
        # the server error is the real cause and finish() reports it below.
        except DeadInputError as e:
            print(f"❌ Recording error: {str(e)}")
            if self._live_error is None:
                self._abort_live(client)
                self._send_notification(
                    "Microphone problem",
                    f"No signal from '{e.device_name}' (muted?). Pick another microphone in the Otis menu."
                )
                return

        except Exception as e:
            print(f"❌ Recording error: {str(e)}")
            if self._live_error is None:
                self._abort_live(client)
                return

        self.state = self.STATE_TRANSCRIBING
        AppHelper.callAfter(self._set_status, "⏳", "Finalizing...")
        AppHelper.callAfter(self._set_live_panel_title, "Otis — Finalizing…")
        try:
            result = client.finish()
        except (RuntimeError, TimeoutError) as e:
            self._handle_live_failure(e, settings, audio_duration)
        except Exception as e:
            print(f"❌ Live transcription error: {str(e)}")
            self._send_notification("Transcription Error", str(e)[:100])
            AppHelper.callAfter(self._set_live_panel_title, "Otis — Error")
        else:
            self._complete_live(result, settings, audio_duration, client.dropped_seconds)
        finally:
            self._cleanup_audio_file(audio_file)
            self._end_live()

    def _abort_live(self, client):
        """End a live session that produced nothing worth keeping (recording thread)."""
        client.cancel()
        AppHelper.callAfter(self._hide_live_panel)
        self._end_live()

    def _end_live(self):
        self.live_mode = False
        self.live_client = None
        self._reset_to_idle()

    def _complete_live(self, result, settings, audio_duration, dropped_seconds):
        self.current_text = result['text']
        stats = result['stats']

        print("\n" + "="*60)
        print(f"🔧 Engine:            {settings.transcription_engine} (live)")
        print(f"📦 Model:             {result['model']}")
        print(f"🎙️  Audio Duration:    {audio_duration:.2f}s")
        print(f"⏱️  Finalize Time:     {result['transcription_time']:.2f}s")
        print(f"🛑 Stop Reason:       {stats.get('stop_reason')}")
        if dropped_seconds:
            print(f"⚠️  Dropped Audio:     {dropped_seconds:.2f}s (sender fell behind)")
        if self.debug:
            print(f"📊 Server Stats:      {stats}")
        print(f"\n✅ Transcription: {self.current_text}")
        print("="*60 + "\n")

        AppHelper.callAfter(self._show_live_result, self.current_text, "Otis — Done")
        if not self.current_text:
            self._send_notification("No speech detected", "Nothing was transcribed.")
            return

        self._save_to_history(
            self.current_text, settings, result['model'], audio_duration, result['transcription_time']
        )
        self._send_notification("Transcription Ready", self._preview(self.current_text))

    def _handle_live_failure(self, error, settings, audio_duration):
        code = getattr(error, 'code', None)
        partial_text = getattr(error, 'partial_text', "")

        if code in LIVE_START_ERROR_CODES or not partial_text:
            print(f"❌ Live transcription could not start: {error}")
            AppHelper.callAfter(self._hide_live_panel)
            if code == "busy":
                self._send_notification("Speech server busy", "Another live transcription is running. Try again when it ends.")
            elif code == "shutting_down":
                self._send_notification("Speech server shutting down", SERVER_START_HINT)
            else:
                self._send_notification("Live transcription could not start", str(error)[:100])
            return

        print(f"❌ Live transcription interrupted: {error}")
        self.current_text = partial_text
        AppHelper.callAfter(self._show_live_result, partial_text, "Otis — Interrupted")
        self._save_to_history(partial_text, settings, settings.server_model, audio_duration, 0.0, error=str(error))
        self._send_notification("Live transcription interrupted", self._preview(partial_text))

    def _on_live_delta(self, delta, text_so_far):
        """Receiver thread: keep only the latest text and schedule one main-thread update at a time."""
        with self._live_lock:
            self._live_text = text_so_far
            if self._live_flush_pending:
                return
            self._live_flush_pending = True
        AppHelper.callAfter(self._flush_live)

    def _on_live_error(self, error):
        """Receiver thread: the session failed; finish() reports it once the recording has stopped."""
        self._live_error = error
        client = self.live_client
        if client and getattr(error, 'code', None) in LIVE_START_ERROR_CODES:
            client.cancel()
        self._request_live_stop()

    def _on_live_final(self, stop_reason):
        """Receiver thread: a final the app did not ask for (eos, max_duration) ends the recording."""
        if stop_reason != "end":
            print(f"\n🛑 Server ended the live session ({stop_reason})")
            self._request_live_stop()

    def _request_live_stop(self):
        self._live_stop.set()
        threading.Thread(target=self._stop_live_recorder, daemon=True).start()

    def _stop_live_recorder(self):
        # record() may not have started yet (VAD model loading): wait until it records or was skipped.
        while not self._live_recording_done.is_set():
            recorder = self.recorder
            if recorder is not None and recorder.is_recording:
                recorder.stop_recording()
                return
            time.sleep(0.05)

    def _show_live_panel(self):
        if self.live_panel is None:
            self.live_panel = LiveTranscriptPanel()
        self.live_panel.set_text("")
        self.live_panel.show("Otis — Listening…")

    def _flush_live(self):
        with self._live_lock:
            text = self._live_text
            self._live_flush_pending = False
        if self.live_panel:
            self.live_panel.set_text(text)

    def _show_live_result(self, text, title):
        if self.live_panel:
            self.live_panel.set_text(text)
            self.live_panel.set_title(title)

    def _set_live_panel_title(self, title):
        if self.live_panel:
            self.live_panel.set_title(title)

    def _hide_live_panel(self):
        if self.live_panel:
            self.live_panel.hide()

    def _create_transcriber(self, settings):
        if settings.transcription_engine == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not found in environment")
            return get_transcriber("gemini", api_key=api_key, debug=self.debug)
        elif settings.transcription_engine == "mistral":
            api_key = os.getenv("MISTRAL_API_KEY")
            if not api_key:
                raise ValueError("MISTRAL_API_KEY not found in environment")
            return get_transcriber("mistral", api_key=api_key, debug=self.debug)
        elif settings.transcription_engine == "local-server":
            return get_transcriber(
                "local-server",
                base_url=settings.server_url,
                model=settings.server_model,
                language=settings.effective_language(),
                debug=self.debug
            )
        else:
            model_id = f"openai/whisper-{settings.whisper_model}"
            return get_transcriber("whisper", model_id=model_id, debug=self.debug, language=settings.language)

    @staticmethod
    def _print_token_usage(tokens, audio_duration):
        """Print whichever token counts the provider returned (keys differ per provider)."""
        print(f"\n💰 TOKEN USAGE:")
        for key, label in (("output_tokens", "Output"), ("total_tokens", "Total")):
            if key in tokens:
                print(f"   {label + ':':<7} {tokens[key]:,} tokens")
        if tokens.get('total_tokens') and audio_duration > 0:
            print(f"   Efficiency: {tokens['total_tokens']/audio_duration:.0f} tokens/second")

    def show_settings(self, sender):
        """Show transcription settings dialog."""
        settings = TranscriptionSettings.load()

        # rumps.alert returns NSAlert's legacy codes: ok = 1, cancel = 0, other = -1.
        deployment_choice = rumps.alert(
            title="Transcription Engine",
            message="Choose deployment type:",
            ok="Cloud (API)",
            cancel="Local (Whisper)",
            other="Local Server (MLX)"
        )

        if deployment_choice == -1:
            self._configure_local_server(settings)
        elif deployment_choice == 1:
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
            settings.language = self._ask_language()

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

        self._update_live_menu_item()

    def toggle_live_transcription(self, sender):
        settings = TranscriptionSettings.load()
        if settings.live_enabled():
            settings.live_transcription = False
        elif settings.live_supported():
            settings.live_transcription = True
        else:
            rumps.alert("Live Transcription", "Live transcription needs Local Server (MLX) → Voxtral 4-bit")
            return
        settings.save()
        self._update_live_menu_item()

    def _update_live_menu_item(self):
        self.live_menu_item.state = int(TranscriptionSettings.load().live_enabled())

    @staticmethod
    def _ask_language():
        lang_choice = rumps.alert(
            title="Language Settings",
            message="Choose transcription language for Whisper:",
            ok="French",
            cancel="English"
        )
        return "fr" if lang_choice == 1 else "en"

    def _configure_local_server(self, settings):
        model_choice = rumps.alert(
            title="Local Server Model",
            message="Choose the otis-speech-server model:",
            ok="Voxtral 4-bit (Fast)",
            cancel="Whisper Turbo"
        )
        settings.transcription_engine = "local-server"
        settings.server_model = "voxtral-realtime-4bit" if model_choice == 1 else "whisper-large-v3-turbo"

        if settings.server_model.startswith("whisper"):
            settings.language = self._ask_language()
            language_note = f"in {settings.language.upper()}"
        else:
            language_note = "(language auto-detected)"

        settings.save()
        rumps.alert(
            "Settings Saved",
            f"Using local server model {settings.server_model} {language_note} at {settings.server_url}\n\n"
            "Start the server with: conda activate otis-speech-server; otis-speech-server"
        )

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
            self._update_live_menu_item()
            rumps.alert("Settings Reset", "Transcription settings reset to defaults:\n• Engine: Whisper (Local)\n• Model: Tiny\n• Language: French")

    def show_text_window(self, sender):
        """Show the transcription text and copy to clipboard."""
        text_to_show = self.current_text

        if not text_to_show:
            history = self.db.get_history(limit=1)
            if history and history[0].get('text'):
                text_to_show = history[0]['text']

        if not text_to_show:
            rumps.alert("No Transcription", "No transcription available yet. Record something first!")
            return

        self._copy_to_clipboard(text_to_show)

        preview = text_to_show if len(text_to_show) <= 500 else text_to_show[:500] + "..."

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

    def _update_microphone_menu(self, refresh):
        """Rebuild the microphone submenu (main thread only)."""
        menu_data = self._microphone_menu_data(refresh)
        if menu_data:
            self._apply_microphone_menu(*menu_data)

    def _microphone_menu_data(self, refresh):
        """Device names, saved choice and active device. refresh=True re-initializes PortAudio: never while a stream is open."""
        try:
            if refresh:
                AudioDeviceManager.refresh()
            names = AudioDeviceManager.list_input_device_names()
            chosen = AppSettings.load().input_device_name
            try:
                active = AudioDeviceManager.resolve_input_device(chosen)[1]['name']
            except ValueError:
                active = "none"
        except Exception as e:
            print(f"⚠️  Failed to list microphones: {e}")
            return None
        return names, chosen, active

    def _apply_microphone_menu(self, names, chosen, active):
        if hasattr(self.microphone_menu, '_menu') and self.microphone_menu._menu is not None:
            self.microphone_menu.clear()
        self.microphone_menu.title = f"Microphone: {active}"

        def make_callback(name):
            return lambda sender: self._select_microphone(name)

        default_item = rumps.MenuItem("System Default", callback=make_callback(None))
        default_item.state = int(chosen is None)
        self.microphone_menu.add(default_item)
        self.microphone_menu.add(rumps.separator)

        for name in names:
            item = rumps.MenuItem(name, callback=make_callback(name))
            item.state = int(name == chosen)
            self.microphone_menu.add(item)

        if chosen is not None and chosen not in names:
            missing_item = rumps.MenuItem(f"{chosen} (not connected)", callback=None)
            missing_item.state = 1
            self.microphone_menu.add(missing_item)

    def _select_microphone(self, name):
        app_settings = AppSettings.load()
        app_settings.input_device_name = name
        app_settings.save()
        print(f"🎙️  Microphone set to: {name or 'System Default'}")
        self._update_microphone_menu(refresh=False)

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
