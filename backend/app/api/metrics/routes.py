import logging
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.db.session import get_db
from app.services.devin_client import DevinClient
from app.models.database import Session as DBSession, Repository, SessionStatus
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

router = APIRouter()
devin_client = DevinClient()


@router.get("/")
async def get_metrics(
    repository_id: Optional[str] = None,
    time_range: str = Query("24h", regex="^(1h|24h|7d|30d|custom)$"),
    time_from: Optional[datetime] = None,
    time_to: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """
    Get observability metrics including success rates, session counts, and cost consumption.

    With time_range=custom, time_from/time_to (ISO 8601) bound the period;
    time_from defaults to 5 minutes before time_to, time_to defaults to now.
    """
    if time_range == "custom":
        now = _to_naive_utc(time_to) if time_to else datetime.utcnow()
        time_before = _to_naive_utc(time_from) if time_from else now - timedelta(minutes=5)
        if time_before > now:
            raise HTTPException(status_code=400, detail="time_from must be before time_to")
    else:
        now = datetime.utcnow()
        time_ranges = {
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30)
        }
        time_before = now - time_ranges.get(time_range, timedelta(hours=24))
    
    # Build base query
    query = db.query(DBSession).filter(
        and_(DBSession.created_at >= time_before, DBSession.created_at <= now)
    )
    
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
    
    # Get ACU consumption from the Devin v3 consumption API
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


def _to_naive_utc(value: datetime) -> datetime:
    """Normalize a possibly tz-aware datetime to naive UTC (how created_at is stored)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def summarize_consumption(consumption_data: dict) -> dict:
    """Aggregate a v3 daily-consumption response into the dashboard's cost_metrics shape."""
    by_date = consumption_data.get("consumption_by_date") or []
    total_acus = consumption_data.get("total_acus")
    if total_acus is None:
        total_acus = sum(item.get("acus") or 0 for item in by_date)
    
    by_product: dict = {}
    for item in by_date:
        for product, acus in (item.get("acus_by_product") or {}).items():
            by_product[product] = by_product.get(product, 0) + (acus or 0)
    
    return {
        "total_acus": round(float(total_acus), 4),
        "acus_by_product": {k: round(float(v), 4) for k, v in by_product.items()},
        "granularity": "daily",
        "data_points": len(by_date),
        "daily": [
            {
                "date": item.get("date"),
                "acus": round(float(item.get("acus") or 0), 4),
                "acus_by_product": item.get("acus_by_product") or {},
            }
            for item in by_date
        ],
    }


async def get_cost_consumption(start: datetime, end: datetime) -> dict:
    """
    Get ACU consumption for [start, end] from the Devin v3 daily consumption API.
    
    The API is bucketed by day (midnight PST), so sub-day ranges (1h/24h)
    return the ACUs of the day(s) overlapping the range.
    """
    try:
        consumption_data = await devin_client.get_daily_consumption(
            time_after=int(start.replace(tzinfo=timezone.utc).timestamp()),
            time_before=int(end.replace(tzinfo=timezone.utc).timestamp()),
        )
        return summarize_consumption(consumption_data)
        
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        detail = f"HTTP {status}"
        if status == 403:
            detail = "Forbidden: consumption API requires the ViewOrgConsumption permission and an Enterprise plan"
        elif status == 401:
            detail = "Unauthorized: check DEVIN_API_KEY"
        logger.error(f"Error fetching cost consumption: {detail} ({e.response.text[:200]})")
        return {"total_acus": None, "acus_by_product": {}, "granularity": "daily", "data_points": 0, "daily": [], "error": detail}
    except Exception as e:
        logger.error(f"Error fetching cost consumption: {e}")
        return {"total_acus": None, "acus_by_product": {}, "granularity": "daily", "data_points": 0, "daily": [], "error": str(e)}


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