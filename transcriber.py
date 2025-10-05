"""Transcription module for Otis the Scribe.

Provides an abstract interface for transcription engines.
Currently supports: Gemini API
Future: OpenAI Whisper (local)
"""

import os
import time
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

    def __init__(self, api_key=None, debug=False):
        """Initialize Gemini transcriber.

        Args:
            api_key: Gemini API key (if None, loads from environment)
            debug: Enable debug mode (token counting, detailed metrics)
        """
        load_dotenv()

        if api_key is None:
            api_key = os.environ.get("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")

        self.client = genai.Client(api_key=api_key)
        self.debug = debug
        self.model = "gemini-2.5-flash-lite"

    def transcribe(self, audio_file_path):
        """Transcribe audio using Gemini API.

        Args:
            audio_file_path: Path to audio file

        Returns:
            dict: {
                'text': str,
                'transcription_time': float,
                'tokens': int (if debug=True),
                'cost': dict (if debug=True)
            }
        """
        start_time = time.time()

        # Upload audio file
        audio_file = self.client.files.upload(file=audio_file_path)

        # Optional: Count tokens (debug mode only)
        tokens_data = None
        if self.debug:
            try:
                token_response = self.client.models.count_tokens(
                    model=self.model,
                    contents=[audio_file]
                )
                tokens_data = {
                    'total_tokens': token_response.total_tokens,
                    'input_cost': token_response.total_tokens * 0.30 / 1_000_000,  # $0.30 per 1M tokens
                }
            except Exception as e:
                print(f"⚠️ Token counting failed: {e}")

        # Generate transcription
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                "Transcribe this audio exactly as spoken. Only return the transcription, nothing else.",
                audio_file
            ]
        )

        transcription_time = time.time() - start_time

        # Calculate output tokens and cost if debug
        if self.debug and tokens_data:
            output_tokens = len(response.text.split()) * 1.3  # Rough estimate
            tokens_data['output_tokens'] = int(output_tokens)
            tokens_data['output_cost'] = output_tokens * 0.40 / 1_000_000  # $0.40 per 1M tokens
            tokens_data['total_cost'] = tokens_data['input_cost'] + tokens_data['output_cost']

        result = {
            'text': response.text.strip(),
            'transcription_time': transcription_time,
        }

        if self.debug and tokens_data:
            result['tokens'] = tokens_data

        return result


class WhisperTranscriber(Transcriber):
    """Local Whisper-based transcription (placeholder for future implementation)."""

    def __init__(self):
        raise NotImplementedError("Whisper transcription coming soon!")

    def transcribe(self, audio_file_path):
        raise NotImplementedError("Whisper transcription coming soon!")


def get_transcriber(engine="gemini", debug=False):
    """Factory function to get a transcriber instance.

    Args:
        engine: Transcription engine ("gemini" or "whisper")
        debug: Enable debug mode (token counting, detailed metrics)

    Returns:
        Transcriber instance
    """
    if engine == "gemini":
        return GeminiTranscriber(debug=debug)
    elif engine == "whisper":
        return WhisperTranscriber()
    else:
        raise ValueError(f"Unknown transcription engine: {engine}")
