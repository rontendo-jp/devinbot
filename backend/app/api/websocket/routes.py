import logging
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.db.session import SessionLocal
from app.models.database import Session as DBSession, SessionStatus
from datetime import datetime, timedelta
from sqlalchemy import and_

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time metrics updates.
    """
    await manager.connect(websocket)
    
    try:
        # Send initial data
        await send_realtime_metrics(websocket)
        
        # Keep sending updates every 30 seconds
        while True:
            await send_realtime_metrics(websocket)
            # Wait for 30 seconds
            import asyncio
            await asyncio.sleep(30)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def send_realtime_metrics(websocket: WebSocket):
    """
    Send real-time metrics to a WebSocket client.
    """
    db = SessionLocal()
    try:
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
        
        metrics = {
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
        
        await websocket.send_json(metrics)
        
    except Exception as e:
        logger.error(f"Error sending realtime metrics: {e}")
        await websocket.send_json({"error": str(e)})
    finally:
        db.close()