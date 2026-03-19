from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fred_query.schemas.analysis import RoutedQueryResponse


@dataclass(slots=True)
class QuerySession:
    session_id: str
    created_at: datetime
    updated_at: datetime
    last_query: str | None = None
    last_response: RoutedQueryResponse | None = None


class QuerySessionService:
    """In-memory request session storage for multi-turn follow-up queries."""

    def __init__(self) -> None:
        self._sessions: dict[str, QuerySession] = {}
        self._lock = Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_session_id(session_id: str | None) -> str:
        normalized = (session_id or "").strip()
        return normalized or str(uuid4())

    def _get_or_create_unlocked(self, session_id: str | None = None) -> QuerySession:
        normalized_session_id = self._normalize_session_id(session_id)
        session = self._sessions.get(normalized_session_id)
        if session is None:
            now = self._now()
            session = QuerySession(
                session_id=normalized_session_id,
                created_at=now,
                updated_at=now,
            )
            self._sessions[normalized_session_id] = session
        return session

    def get_or_create(self, session_id: str | None = None) -> QuerySession:
        with self._lock:
            return self._get_or_create_unlocked(session_id)

    def store_turn(
        self,
        *,
        session_id: str,
        query: str,
        response: RoutedQueryResponse,
    ) -> QuerySession:
        with self._lock:
            session = self._get_or_create_unlocked(session_id)
            session.last_query = query
            session.last_response = response
            session.updated_at = self._now()
            return session
