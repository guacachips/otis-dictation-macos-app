"""Transcription module for Otis the Scribe.

Provides an abstract interface for transcription engines.
Currently supports: Gemini API
Future: OpenAI Whisper (local)
"""

import os
from abc import ABC, abstractmethod
from google import genai
from dotenv import load_dotenv


class Transcriber(ABC):
    """Abstract base class for transcription engines."""

    @abstractmethod
    def transcribe(self, audio_file_path):
        """Transcribe an audio file to text.

        Args:
            audio_file_path: Path to the audio file

        Returns:
            str: Transcribed text
        """
        pass


class GeminiTranscriber(Transcriber):
    """Gemini API-based transcription."""

    def __init__(self, api_key=None):
        """Initialize Gemini transcriber.

        Args:
            api_key: Gemini API key (if None, loads from environment)
        """
        load_dotenv()

        if api_key is None:
            api_key = os.environ.get("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")

        self.client = genai.Client(api_key=api_key)

    def transcribe(self, audio_file_path):
        """Transcribe audio using Gemini API.

        Args:
            audio_file_path: Path to audio file

        Returns:
            str: Transcribed text
        """
        # Upload audio file
        audio_file = self.client.files.upload(file=audio_file_path)

        # Generate transcription
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[
                "Transcribe this audio exactly as spoken. Only return the transcription, nothing else.",
                audio_file
            ]
        )

        return response.text.strip()


class WhisperTranscriber(Transcriber):
    """Local Whisper-based transcription (placeholder for future implementation)."""

    def __init__(self):
        raise NotImplementedError("Whisper transcription coming soon!")

    def transcribe(self, audio_file_path):
        raise NotImplementedError("Whisper transcription coming soon!")


def get_transcriber(engine="gemini"):
    """Factory function to get a transcriber instance.

    Args:
        engine: Transcription engine ("gemini" or "whisper")

    Returns:
        Transcriber instance
    """
    if engine == "gemini":
        return GeminiTranscriber()
    elif engine == "whisper":
        return WhisperTranscriber()
    else:
        raise ValueError(f"Unknown transcription engine: {engine}")
