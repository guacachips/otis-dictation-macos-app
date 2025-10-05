"""Otis the Scribe - macOS Menu Bar Voice Transcription App.

A simple voice-to-text application that lives in your macOS menu bar.
Click to record, transcribe with Gemini, and copy the text.
"""

import rumps
import threading
import subprocess
from audio_recorder import AudioRecorder
from transcriber import get_transcriber


class OtisTheScribeApp(rumps.App):
    """Main menu bar application."""

    # App states
    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_TRANSCRIBING = "transcribing"

    def __init__(self):
        super(OtisTheScribeApp, self).__init__(
            name="Otis the Scribe",
            title="🎤",  # Use title for emoji
            quit_button=None
        )

        # Initialize components
        self.recorder = AudioRecorder()
        self.transcriber = get_transcriber("gemini")
        self.state = self.STATE_IDLE
        self.current_text = ""

        # Create menu items
        self.menu = [
            rumps.MenuItem("Start Recording", callback=self.toggle_recording),
            rumps.separator,
            rumps.MenuItem("Show Last Transcription", callback=self.show_text_window),
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
        """Start recording audio."""
        self.state = self.STATE_RECORDING
        self.title = "🔴"  # Red dot while recording
        self.menu["Start Recording"].title = "Stop Recording"
        self.recorder.start_recording()

    def _stop_recording(self):
        """Stop recording and start transcription."""
        self.state = self.STATE_TRANSCRIBING
        self.title = "⏳"  # Hourglass while processing
        self.menu["Start Recording"].title = "Transcribing..."

        # Stop recording in background thread to avoid blocking UI
        threading.Thread(target=self._transcribe_audio, daemon=True).start()

    def _transcribe_audio(self):
        """Transcribe the recorded audio (runs in background thread)."""
        try:
            # Stop recording and get file path
            audio_file = self.recorder.stop_recording()

            if audio_file:
                # Transcribe
                self.current_text = self.transcriber.transcribe(audio_file)
                print(f"✅ Transcription complete: {self.current_text}")

                # Auto-show the window on main thread
                rumps.Timer(lambda _: self.show_text_window(None), 0.1).start()

        except Exception as e:
            print(f"❌ Transcription error: {str(e)}")
            self.current_text = f"Error: {str(e)}"
            # Show error on main thread
            rumps.Timer(lambda _: self._show_error(str(e)), 0.1).start()

        finally:
            # Reset state
            self.state = self.STATE_IDLE
            self.title = "🎤"
            self.menu["Start Recording"].title = "Start Recording"

    def _show_error(self, error_msg):
        """Show error dialog on main thread."""
        rumps.alert("Transcription Error", f"Failed to transcribe: {error_msg}")

    def show_text_window(self, sender):
        """Show the transcription text and copy to clipboard."""
        if not self.current_text:
            rumps.alert("No Transcription", "No transcription available yet. Record something first!")
            return

        # Copy to clipboard using macOS pbcopy
        self._copy_to_clipboard(self.current_text)

        # Show alert with the text (truncated if too long)
        preview = self.current_text if len(self.current_text) <= 500 else self.current_text[:500] + "..."

        rumps.alert(
            title="Transcription (Copied to Clipboard ✓)",
            message=preview,
            ok="Done"
        )

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
    app = OtisTheScribeApp()
    app.run()
