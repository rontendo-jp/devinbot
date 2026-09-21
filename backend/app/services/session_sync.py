import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.db.session import SessionLocal
from app.models.database import Session as DBSession, SessionStatus
from app.services.devin_client import DevinClient

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = [SessionStatus.PENDING, SessionStatus.RUNNING]

# Devin API status -> local status for sessions that are no longer working.
# "suspended" is Devin going idle after finishing its work (or waiting on the user);
# for this dashboard that counts as completed.
FINAL_STATUS_MAP: Dict[str, SessionStatus] = {
    "finished": SessionStatus.COMPLETED,
    "completed": SessionStatus.COMPLETED,
    "expired": SessionStatus.COMPLETED,
    "suspended": SessionStatus.COMPLETED,
    "terminated": SessionStatus.CANCELLED,
    "cancelled": SessionStatus.CANCELLED,
    "failed": SessionStatus.FAILED,
    "error": SessionStatus.FAILED,
}


def describe_live_status(live: Dict) -> str:
    """Human-readable 'status (detail)' from a Devin session payload."""
    status = str(live.get("status") or "unknown").lower()
    detail = live.get("status_detail")
    return f"{status} ({detail})" if detail and detail != status else status


class SessionSyncService:
    """Keeps local session rows in step with the live status reported by the Devin API."""

    def __init__(self, devin_client: DevinClient, notifier=None):
        self.devin_client = devin_client
        # async callable (session, live_status_text) -> None, invoked when a session reaches a final state
        self.notifier = notifier

    async def fetch_live(self, session: DBSession) -> Optional[Dict]:
        if not session.devin_session_id:
            return None
        try:
            return await self.devin_client.get_session(session.devin_session_id)
        except Exception as e:
            logger.warning(f"Could not refresh session {session.devin_session_id}: {e}")
            return None

    async def refresh(self, db, sessions: List[DBSession]) -> List[str]:
        """
        Fetch live statuses concurrently and persist any final status reached.

        Returns one status text per session (local status when Devin is unreachable).
        """
        live_results = await asyncio.gather(*(self.fetch_live(s) for s in sessions))
        texts: List[str] = []
        finished: List[Tuple[DBSession, str]] = []
        for session, live in zip(sessions, live_results):
            if not live:
                texts.append(session.status.value)
                continue
            text = describe_live_status(live)
            texts.append(text)
            final = FINAL_STATUS_MAP.get(str(live.get("status") or "").lower())
            if final and session.status != final:
                session.status = final
                session.completed_at = datetime.utcnow()
                finished.append((session, text))
        if finished:
            db.commit()
            if self.notifier:
                for session, text in finished:
                    try:
                        await self.notifier(session, text)
                    except Exception as e:
                        logger.error(f"Failed to notify about session {session.devin_session_id}: {e}")
        return texts

    async def sync_all(self) -> int:
        """Refresh every active local session. Returns the number of sessions that reached a final state."""
        with SessionLocal() as db:
            sessions = (
                db.query(DBSession)
                .filter(DBSession.status.in_(ACTIVE_STATUSES), DBSession.devin_session_id.isnot(None))
                .all()
            )
            if not sessions:
                return 0
            before = {s.id: s.status for s in sessions}
            await self.refresh(db, sessions)
            changed = sum(1 for s in sessions if s.status != before[s.id])
        if changed:
            logger.info(f"Session sync: {changed}/{len(sessions)} sessions reached a final state")
        return changed

    async def run_forever(self, interval_seconds: int):
        while True:
            try:
                await self.sync_all()
            except Exception as e:
                logger.error(f"Session sync failed: {e}")
            await asyncio.sleep(interval_seconds)
