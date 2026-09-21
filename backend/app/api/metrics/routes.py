import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.db.session import get_db
from app.services.devin_client import DevinClient
from app.models.database import Session as DBSession, Repository, SessionStatus
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter()
devin_client = DevinClient()


@router.get("/")
async def get_metrics(
    repository_id: Optional[str] = None,
    time_range: str = Query("24h", regex="^(1h|24h|7d|30d)$"),
    db: Session = Depends(get_db)
):
    """
    Get observability metrics including success rates, session counts, and cost consumption.
    """
    # Calculate time range
    now = datetime.utcnow()
    time_ranges = {
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30)
    }
    time_delta = time_ranges.get(time_range, timedelta(hours=24))
    time_before = now - time_delta
    
    # Build base query
    query = db.query(DBSession).filter(DBSession.created_at >= time_before)
    
    if repository_id:
        query = query.filter(DBSession.repository_id == repository_id)
    
    # Get session counts by status
    status_counts = {}
    for status in SessionStatus:
        count = query.filter(DBSession.status == status).count()
        status_counts[status.value] = count
    
    # Calculate success rate
    total_sessions = sum(status_counts.values())
    completed_sessions = status_counts.get("completed", 0)
    success_rate = (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    # Get active vs completed sessions
    active_sessions = status_counts.get("running", 0)
    completed_sessions_count = status_counts.get("completed", 0)
    
    # Get cost consumption from Devin Analytics API
    cost_data = await get_cost_consumption(time_before, now)
    
    # Get repository-specific metrics if repository_id is provided
    repository_metrics = None
    if repository_id:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if repository:
            repository_metrics = {
                "repository_name": repository.github_repo_path,
                "repository_id": str(repository.id)
            }
    
    return {
        "time_range": time_range,
        "time_period": {
            "start": time_before.isoformat(),
            "end": now.isoformat()
        },
        "session_metrics": {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions_count,
            "success_rate": round(success_rate, 2),
            "status_breakdown": status_counts
        },
        "cost_metrics": cost_data,
        "repository": repository_metrics
    }


async def get_cost_consumption(time_before: datetime, time_after: datetime) -> dict:
    """
    Get cost consumption data from Devin Analytics API.
    
    Args:
        time_before: Start of time range
        time_after: End of time range
        
    Returns:
        Cost consumption metrics
    """
    try:
        # Convert to ISO format strings
        time_before_str = time_before.isoformat()
        time_after_str = time_after.isoformat()
        
        # Get consumption data
        consumption_data = await devin_client.get_consumption_analytics(
            time_before=time_before_str,
            time_after=time_after_str
        )
        
        # Extract relevant metrics
        total_cost = 0
        total_acus = 0
        total_credits = 0
        
        if "data" in consumption_data:
            for item in consumption_data["data"]:
                # Add up costs based on billing strategy
                if "acus" in item:
                    total_acus += item.get("acus", 0)
                if "credits" in item:
                    total_credits += item.get("credits", 0)
        
        return {
            "total_acus": total_acus,
            "total_credits": total_credits,
            "currency": "USD",
            "data_points": len(consumption_data.get("data", []))
        }
        
    except Exception as e:
        logger.error(f"Error fetching cost consumption: {e}")
        return {
            "total_acus": 0,
            "total_credits": 0,
            "currency": "USD",
            "error": str(e)
        }


@router.get("/repositories")
async def get_repository_metrics(db: Session = Depends(get_db)):
    """
    Get metrics aggregated by repository.
    """
    # Get session counts by repository
    repo_metrics = db.query(
        Repository.id,
        Repository.github_repo_path,
        func.count(DBSession.id).label("total_sessions"),
        func.sum(func.case((DBSession.status == SessionStatus.RUNNING, 1), else_=0)).label("active_sessions"),
        func.sum(func.case((DBSession.status == SessionStatus.COMPLETED, 1), else_=0)).label("completed_sessions")
    ).join(
        DBSession, Repository.id == DBSession.repository_id
    ).group_by(
        Repository.id, Repository.github_repo_path
    ).all()
    
    return {
        "repositories": [
            {
                "repository_id": str(repo.id),
                "repository_name": repo.github_repo_path,
                "total_sessions": repo.total_sessions or 0,
                "active_sessions": repo.active_sessions or 0,
                "completed_sessions": repo.completed_sessions or 0
            }
            for repo in repo_metrics
        ]
    }


@router.get("/realtime")
async def get_realtime_metrics(db: Session = Depends(get_db)):
    """
    Get real-time metrics for live dashboard updates.
    """
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    
    # Get active sessions
    active_sessions = db.query(DBSession).filter(
        DBSession.status == SessionStatus.RUNNING
    ).all()
    
    # Get recent completed sessions (last hour)
    recent_completed = db.query(DBSession).filter(
        and_(
            DBSession.status == SessionStatus.COMPLETED,
            DBSession.completed_at >= one_hour_ago
        )
    ).count()
    
    # Get recent failed sessions (last hour)
    recent_failed = db.query(DBSession).filter(
        and_(
            DBSession.status == SessionStatus.FAILED,
            DBSession.completed_at >= one_hour_ago
        )
    ).count()
    
    return {
        "timestamp": now.isoformat(),
        "active_sessions": len(active_sessions),
        "recent_completed": recent_completed,
        "recent_failed": recent_failed,
        "active_session_details": [
            {
                "id": str(session.id),
                "devin_session_id": session.devin_session_id,
                "repository_name": session.repository.github_repo_path if session.repository else "Unknown",
                "trigger_type": session.trigger_type.value,
                "created_at": session.created_at.isoformat()
            }
            for session in active_sessions
        ]
    }