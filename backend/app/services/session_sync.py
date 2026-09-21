import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.db.session import SessionLocal
from app.models.database import Session as DBSession, SessionStatus
from app.services.devin_client import DevinClient

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = [SessionStatus.PENDING, SessionStatus.RUNNING]

# Devin v3 session `status` enum: new, claimed, running, exit, error, suspended, resuming.
# `status_detail` refines it: for running -> working | waiting_for_user | waiting_for_approval | finished;
# for suspended -> the reason (inactivity, user_request, out_of_credits, ...).
# The raw pair is stored and displayed as-is; the local SessionStatus enum is only a coarse
# summary derived from it for the dashboard's active/completed/failed counters.
NEEDS_USER_DETAILS = {"waiting_for_user", "waiting_for_approval"}
BENIGN_SUSPEND_REASONS = {"inactivity", "user_request"}


def live_pair(live: Dict) -> Tuple[str, str]:
    status = str(live.get("status") or "").lower()
    detail = str(live.get("status_detail") or "").lower()
    return status, detail


def describe_live_status(live: Dict) -> str:
    """'status / detail' exactly as Devin reports it."""
    status, detail = live_pair(live)
    status = status or "unknown"
    return f"{status} / {detail}" if detail and detail != status else status


def needs_user(live: Dict) -> bool:
    status, detail = live_pair(live)
    return status == "running" and detail in NEEDS_USER_DETAILS


def summary_status_of(live: Dict) -> SessionStatus:
    """Coarse local summary of a live Devin payload."""
    status, detail = live_pair(live)
    if status == "running":
        return SessionStatus.COMPLETED if detail == "finished" else SessionStatus.RUNNING
    if status == "suspended":
        return SessionStatus.COMPLETED if detail in BENIGN_SUSPEND_REASONS else SessionStatus.FAILED
    if status in ("exit", "finished", "expired"):
        return SessionStatus.COMPLETED
    if status in ("terminated", "cancelled"):
        return SessionStatus.CANCELLED
    if status in ("error", "failed"):
        return SessionStatus.FAILED
    return SessionStatus.RUNNING  # new / claimed / resuming


class SessionSyncService:
    """Keeps local session rows in step with the live status reported by the Devin API."""

    def __init__(self, devin_client: DevinClient, notifier=None):
        self.devin_client = devin_client
        # async callable (session, previous_live_text) -> None, invoked whenever the raw
        # Devin status/detail pair changes
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
        Fetch live statuses concurrently and persist them as-is.

        Returns one status text per session (last known value when Devin is unreachable).
        """
        live_results = await asyncio.gather(*(self.fetch_live(s) for s in sessions))
        texts: List[str] = []
        changed: List[Tuple[DBSession, str]] = []
        for session, live in zip(sessions, live_results):
            if not live:
                texts.append(session_status_text(session))
                continue
            status, detail = live_pair(live)
            text = describe_live_status(live)
            texts.append(text)
            if (status, detail) == (session.devin_status or "", session.devin_status_detail or ""):
                continue
            previous = session_status_text(session)
            session.devin_status = status
            session.devin_status_detail = detail or None
            summary = summary_status_of(live)
            if session.status != summary:
                session.status = summary
                session.completed_at = datetime.utcnow() if summary not in ACTIVE_STATUSES else None
            changed.append((session, previous))
        if changed:
            db.commit()
            if self.notifier:
                for session, previous in changed:
                    try:
                        await self.notifier(session, previous)
                    except Exception as e:
                        logger.error(f"Failed to notify about session {session.devin_session_id}: {e}")
        return texts

    async def sync_all(self) -> int:
        """Refresh every active local session. Returns the number of sessions whose Devin status changed."""
        with SessionLocal() as db:
            sessions = (
                db.query(DBSession)
                .filter(DBSession.status.in_(ACTIVE_STATUSES), DBSession.devin_session_id.isnot(None))
                .all()
            )
            if not sessions:
                return 0
            before = {s.id: (s.devin_status, s.devin_status_detail) for s in sessions}
            await self.refresh(db, sessions)
            changed = sum(1 for s in sessions if (s.devin_status, s.devin_status_detail) != before[s.id])
        if changed:
            logger.info(f"Session sync: {changed}/{len(sessions)} sessions changed status")
        return changed

    async def run_forever(self, interval_seconds: int):
        while True:
            try:
                await self.sync_all()
            except Exception as e:
                logger.error(f"Session sync failed: {e}")
            await asyncio.sleep(interval_seconds)


def session_status_text(session: DBSession) -> str:
    """Raw Devin status if known, otherwise the local summary."""
    if session.devin_status:
        detail = session.devin_status_detail
        return f"{session.devin_status} / {detail}" if detail else session.devin_status
    return session.status.value
