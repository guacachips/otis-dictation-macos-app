"""Otis the Scribe - macOS Menu Bar Voice Transcription App.

A simple voice-to-text application that lives in your macOS menu bar.
Click to record, transcribe with Gemini, and copy the text.
"""

import os
import rumps
import threading
import subprocess
from audio_recorder import AudioRecorder
from transcriber import get_transcriber
from dotenv import load_dotenv

load_dotenv()


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

        # Check for debug mode
        self.debug = os.environ.get("DEBUG", "false").lower() == "true"

        # Initialize components
        self.recorder = AudioRecorder()
        self.transcriber = get_transcriber("gemini", debug=self.debug)
        self.state = self.STATE_IDLE
        self.current_text = ""

        if self.debug:
            print("🔬 DEBUG MODE ENABLED - Token counting active")

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
            # Stop recording and get file path + duration
            audio_file, audio_duration = self.recorder.stop_recording()

            if audio_file:
                # Transcribe
                result = self.transcriber.transcribe(audio_file)
                self.current_text = result['text']
                transcription_time = result['transcription_time']

                # Calculate performance metrics
                realtime_factor = transcription_time / audio_duration if audio_duration > 0 else 0
                speed_multiplier = audio_duration / transcription_time if transcription_time > 0 else 0

                # Display metrics
                print("\n" + "="*60)
                print(f"🎙️  Audio Duration:    {audio_duration:.2f}s")
                print(f"⏱️  Transcription Time: {transcription_time:.2f}s")
                print(f"📊 Realtime Factor:   {realtime_factor:.2f}x")
                print(f"🚀 Speed:             {speed_multiplier:.1f}x faster than audio")

                # Debug mode: Show token and cost info
                if self.debug and 'tokens' in result:
                    tokens = result['tokens']
                    print(f"\n💰 TOKEN USAGE:")
                    print(f"   Input:  {tokens['total_tokens']:,} tokens (${tokens['input_cost']:.6f})")
                    print(f"   Output: {tokens['output_tokens']:,} tokens (${tokens['output_cost']:.6f})")
                    print(f"   Total:  ${tokens['total_cost']:.6f}")
                    print(f"   Efficiency: {tokens['total_tokens']/audio_duration:.0f} tokens/second")

                print(f"\n✅ Transcription: {self.current_text}")
                print("="*60 + "\n")

                # Send notification using osascript (no setup required!)
                preview = self.current_text[:100] + "..." if len(self.current_text) > 100 else self.current_text
                self._send_notification("Transcription Ready", preview)

        except Exception as e:
            print(f"❌ Transcription error: {str(e)}")
            self.current_text = f"Error: {str(e)}"
            self._send_notification("Transcription Error", str(e)[:100])

        finally:
            # Reset state
            self.state = self.STATE_IDLE
            self.title = "🎤"
            self.menu["Start Recording"].title = "Start Recording"

    def _send_notification(self, title, message):
        """Send macOS notification using osascript (no Info.plist needed)."""
        # Remove problematic characters for AppleScript (full text preserved in app)
        safe_message = message.replace('"', "'").replace('\\', '').replace('\n', ' ')
        safe_title = title.replace('"', "'").replace('\\', '').replace('\n', ' ')

        subprocess.run([
            'osascript', '-e',
            f'display notification "{safe_message}" with title "{safe_title}"'
        ], capture_output=True)

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
