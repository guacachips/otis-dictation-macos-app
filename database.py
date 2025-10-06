"""Database module for transcription history with privacy-first design.

Two-table architecture:
- sessions: Telemetry data (safe to export for analytics)
- transcriptions: Sensitive content (always stays local)
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager


class TranscriptionDatabase:
    """SQLite database for storing transcription history."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection.

        Args:
            db_path: Path to database file. Defaults to ~/.otis-dictation-macos-app/history.db
        """
        if db_path is None:
            db_path = Path.home() / ".otis-dictation-macos-app" / "history.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    engine TEXT NOT NULL,
                    model TEXT,
                    language TEXT,
                    audio_duration REAL,
                    transcription_time REAL,
                    realtime_factor REAL,
                    tokens_total INTEGER,
                    cost_total REAL,
                    error TEXT,
                    synced_at TIMESTAMP DEFAULT NULL
                )
            """)

            # Add synced_at column if it doesn't exist (migration)
            cursor.execute("PRAGMA table_info(sessions)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'synced_at' not in columns:
                cursor.execute("ALTER TABLE sessions ADD COLUMN synced_at TIMESTAMP DEFAULT NULL")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL UNIQUE,
                    text TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_created
                ON sessions(created_at DESC)
            """)

    def save_transcription(
        self,
        text: str,
        engine: str = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        audio_duration: Optional[float] = None,
        transcription_time: Optional[float] = None,
        realtime_factor: Optional[float] = None,
        tokens_total: Optional[int] = None,
        cost_total: Optional[float] = None,
        error: Optional[str] = None,
        save_telemetry: bool = True
    ) -> int:
        """Save transcription with optional session metadata.

        Args:
            text: Transcription text
            engine: Transcription engine (required if save_telemetry=True)
            save_telemetry: If False, only saves transcription text without session metadata

        Returns:
            session_id: ID of the created session (or None if telemetry disabled)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            session_id = None

            if save_telemetry:
                cursor.execute("""
                    INSERT INTO sessions (
                        engine, model, language, audio_duration, transcription_time,
                        realtime_factor, tokens_total, cost_total, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    engine, model, language, audio_duration, transcription_time,
                    realtime_factor, tokens_total, cost_total, error
                ))

                session_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO transcriptions (session_id, text)
                    VALUES (?, ?)
                """, (session_id, text))
            else:
                # Create a dummy session to maintain FK constraint
                cursor.execute("""
                    INSERT INTO sessions (engine, error)
                    VALUES (?, ?)
                """, ("telemetry_disabled", None))

                session_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO transcriptions (session_id, text)
                    VALUES (?, ?)
                """, (session_id, text))

            return session_id

    def get_history(self, limit: int = 20) -> List[Dict]:
        """Get recent transcription history with metadata.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of dicts with session metadata and transcription text
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    s.id,
                    s.created_at,
                    s.engine,
                    s.model,
                    s.language,
                    s.audio_duration,
                    s.transcription_time,
                    s.realtime_factor,
                    t.text
                FROM sessions s
                LEFT JOIN transcriptions t ON s.id = t.session_id
                WHERE s.error IS NULL AND s.engine != 'telemetry_disabled'
                ORDER BY s.created_at DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_transcription(self, session_id: int) -> Optional[str]:
        """Get transcription text by session ID.

        Args:
            session_id: Session ID

        Returns:
            Transcription text or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT text FROM transcriptions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            return row['text'] if row else None

    def delete_transcription(self, session_id: int):
        """Delete a specific transcription and its session.

        Args:
            session_id: Session ID to delete
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Delete transcription first (child)
            cursor.execute("DELETE FROM transcriptions WHERE session_id = ?", (session_id,))
            # Delete session (parent)
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def clear_sensitive_data(self):
        """Clear all transcription text but keep telemetry data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transcriptions")

    def get_unsynced_sessions(self, limit: int = 100) -> List[Dict]:
        """Get sessions that haven't been synced yet.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of session dicts without transcription text
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    id, created_at, engine, model, language,
                    audio_duration, transcription_time, realtime_factor,
                    tokens_total, cost_total
                FROM sessions
                WHERE synced_at IS NULL
                  AND error IS NULL
                  AND engine != 'telemetry_disabled'
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def mark_synced(self, session_ids: List[int]):
        """Mark sessions as synced.

        Args:
            session_ids: List of session IDs to mark as synced
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(session_ids))
            cursor.execute(
                f"UPDATE sessions SET synced_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                session_ids
            )

    def get_stats(self) -> Dict:
        """Get database statistics.

        Returns:
            Dict with total sessions, total transcriptions, etc.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as count FROM sessions")
            total_sessions = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM transcriptions")
            total_transcriptions = cursor.fetchone()['count']

            return {
                'total_sessions': total_sessions,
                'total_transcriptions': total_transcriptions
            }
