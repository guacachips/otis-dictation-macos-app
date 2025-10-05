"""Audio recording module for Otis the Scribe.

Handles microphone input recording using sounddevice.
"""

import sounddevice as sd
import numpy as np
from scipy.io import wavfile
from pathlib import Path
import tempfile
import time


class AudioRecorder:
    """Records audio from the default microphone."""

    def __init__(self, sample_rate=16000, channels=1):
        """Initialize the audio recorder.

        Args:
            sample_rate: Recording sample rate (16kHz is standard for speech)
            channels: Number of audio channels (1 for mono, 2 for stereo)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = []
        self.is_recording = False
        self.start_time = None
        self.duration = 0

    def start_recording(self):
        """Start recording audio from the microphone."""
        if self.is_recording:
            return

        self.recording = []
        self.is_recording = True
        self.start_time = time.time()  # Track start time

        # Start recording in a stream
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=self._audio_callback
        )
        self.stream.start()

    def stop_recording(self):
        """Stop recording and return the audio file path and duration.

        Returns:
            tuple: (file_path, duration_seconds)
        """
        if not self.is_recording:
            return None, 0

        self.is_recording = False
        self.stream.stop()
        self.stream.close()

        # Calculate duration
        self.duration = time.time() - self.start_time if self.start_time else 0

        # Convert list of chunks to numpy array
        audio_data = np.concatenate(self.recording, axis=0)

        # Save to temporary WAV file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        wavfile.write(temp_file.name, self.sample_rate, audio_data)

        return temp_file.name, self.duration

    def _audio_callback(self, indata, frames, time, status):
        """Callback function for audio stream.

        Called automatically by sounddevice for each audio chunk.
        """
        if status:
            print(f"Audio status: {status}")

        if self.is_recording:
            self.recording.append(indata.copy())
