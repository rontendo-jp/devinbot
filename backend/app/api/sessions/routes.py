import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.devin_client import DevinClient
from app.models.database import Session as DBSession, Repository, SessionStatus, DevinMode, TriggerType
from datetime import datetime, timedelta, timezone
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()
devin_client = DevinClient()

DEVIN_SESSION_URL = "https://app.devin.ai/sessions/{}"


def iso_utc(value: Optional[datetime]) -> Optional[str]:
    """Timestamps are stored as naive UTC; emit them with an explicit offset so clients render local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def serialize_session(session: DBSession, include_context: bool = False) -> dict:
    data = {
        "id": str(session.id),
        "devin_session_id": session.devin_session_id,
        "session_url": DEVIN_SESSION_URL.format(session.devin_session_id) if session.devin_session_id else None,
        "repository_id": str(session.repository_id),
        "trigger_type": session.trigger_type.value,
        "status": session.status.value,
        "devin_status": session.devin_status,
        "devin_status_detail": session.devin_status_detail,
        "last_devin_message": session.last_devin_message,
        "prompt": session.prompt,
        "devin_mode": session.devin_mode.value,
        "error_message": session.error_message,
        "created_at": iso_utc(session.created_at),
        "updated_at": iso_utc(session.updated_at),
        "completed_at": iso_utc(session.completed_at),
    }
    if include_context:
        data["trigger_context"] = session.trigger_context
    return data


@router.get("/")
async def list_sessions(
    status: Optional[str] = None,
    repository_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    List sessions with optional filtering.
    """
    query = db.query(DBSession)
    
    if status:
        try:
            status_enum = SessionStatus(status)
            query = query.filter(DBSession.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if repository_id:
        try:
            repo_uuid = uuid.UUID(repository_id)
            query = query.filter(DBSession.repository_id == repo_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid repository_id format")
    
    sessions = query.order_by(DBSession.created_at.desc()).limit(limit).all()
    
    return {
        "sessions": [serialize_session(session) for session in sessions],
        "count": len(sessions)
    }


@router.get("/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific session.
    """
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    
    session = db.query(DBSession).filter(DBSession.id == session_uuid).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return serialize_session(session, include_context=True)


@router.post("/")
async def create_session(
    repository_id: str,
    prompt: str,
    devin_mode: Optional[str] = "normal",
    trigger_type: Optional[str] = "manual",
    db: Session = Depends(get_db)
):
    """
    Create a new Devin session.
    """
    try:
        repo_uuid = uuid.UUID(repository_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository_id format")
    
    # Get repository
    repository = db.query(Repository).filter(Repository.id == repo_uuid).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Validate devin_mode
    try:
        devin_mode_enum = DevinMode(devin_mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid devin_mode: {devin_mode}")
    
    try:
        # Create Devin session
        session_response = await devin_client.create_session(
            prompt=prompt,
            repos=[f"https://github.com/{repository.github_repo_path}"],
            devin_mode=devin_mode_enum,
            title=f"Manual session: {repository.github_repo_path}"
        )
        
        devin_session_id = session_response.get("session_id")
        
        # Create session record
        new_session = DBSession(
            devin_session_id=devin_session_id,
            repository_id=repository.id,
            trigger_type=TriggerType(trigger_type),
            trigger_context=None,
            status=SessionStatus.RUNNING,
            prompt=prompt,
            devin_mode=devin_mode_enum
        )
        db.add(new_session)
        db.commit()
        
        return {
            "id": str(new_session.id),
            "devin_session_id": devin_session_id,
            "status": "running",
            "message": "Session created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/cancel")
async def cancel_session(session_id: str, db: Session = Depends(get_db)):
    """
    Cancel a running session.
    """
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    
    session = db.query(DBSession).filter(DBSession.id == session_uuid).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.status != SessionStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Session is not running")
    
    if not session.devin_session_id:
        raise HTTPException(status_code=400, detail="No Devin session ID available")
    
    try:
        # Cancel Devin session
        await devin_client.terminate_session(session.devin_session_id)
        
        # Update session status
        session.status = SessionStatus.CANCELLED
        session.completed_at = datetime.utcnow()
        db.commit()
        
        return {
            "id": str(session.id),
            "status": "cancelled",
            "message": "Session cancelled successfully"
        }
        
    except Exception as e:
        logger.error(f"Error cancelling session: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))