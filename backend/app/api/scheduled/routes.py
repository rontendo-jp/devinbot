import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.database import ScheduledTask, Repository, DevinMode
from app.services.scheduler import TaskScheduler
from datetime import datetime
import uuid
import json

logger = logging.getLogger(__name__)

router = APIRouter()
# Task scheduler will be injected as a dependency later
task_scheduler = None


def set_task_scheduler(scheduler: TaskScheduler):
    """Set the task scheduler instance."""
    global task_scheduler
    task_scheduler = scheduler


@router.get("/")
async def list_scheduled_tasks(
    repository_id: Optional[str] = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    List scheduled tasks with optional filtering.
    """
    query = db.query(ScheduledTask)
    
    if repository_id:
        try:
            repo_uuid = uuid.UUID(repository_id)
            query = query.filter(ScheduledTask.repository_id == repo_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid repository_id format")
    
    if enabled_only:
        query = query.filter(ScheduledTask.enabled == True)
    
    tasks = query.order_by(ScheduledTask.created_at.desc()).all()
    
    return {
        "tasks": [
            {
                "id": str(task.id),
                "repository_id": str(task.repository_id),
                "name": task.name,
                "cron_expression": task.cron_expression,
                "prompt": task.prompt,
                "devin_mode": task.devin_mode.value,
                "enabled": task.enabled,
                "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "created_at": task.created_at.isoformat()
            }
            for task in tasks
        ],
        "count": len(tasks)
    }


@router.post("/")
async def create_scheduled_task(
    repository_id: str,
    name: str,
    cron_expression: str,
    prompt: str,
    devin_mode: str = "normal",
    enabled: bool = True,
    db: Session = Depends(get_db)
):
    """
    Create a new scheduled task.
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
        # Create scheduled task
        new_task = ScheduledTask(
            repository_id=repository.id,
            name=name,
            cron_expression=cron_expression,
            prompt=prompt,
            devin_mode=devin_mode_enum,
            enabled=enabled
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        
        # Add to scheduler if enabled
        if enabled and task_scheduler:
            task_scheduler.add_scheduled_task(new_task)
        
        return {
            "id": str(new_task.id),
            "repository_id": str(new_task.repository_id),
            "name": new_task.name,
            "cron_expression": new_task.cron_expression,
            "enabled": new_task.enabled,
            "message": "Scheduled task created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating scheduled task: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}")
async def get_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific scheduled task.
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_uuid).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    
    # Get next run time from scheduler
    next_run_time = None
    if task_scheduler:
        next_run_time = task_scheduler.get_next_run_time(task_id)
    
    return {
        "id": str(task.id),
        "repository_id": str(task.repository_id),
        "name": task.name,
        "cron_expression": task.cron_expression,
        "prompt": task.prompt,
        "devin_mode": task.devin_mode.value,
        "enabled": task.enabled,
        "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
        "next_run_at": next_run_time.isoformat() if next_run_time else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat()
    }


@router.put("/{task_id}")
async def update_scheduled_task(
    task_id: str,
    name: Optional[str] = None,
    cron_expression: Optional[str] = None,
    prompt: Optional[str] = None,
    devin_mode: Optional[str] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Update a scheduled task.
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    
    try:
        # Update fields if provided
        if name is not None:
            task.name = name
        if cron_expression is not None:
            task.cron_expression = cron_expression
        if prompt is not None:
            task.prompt = prompt
        if devin_mode is not None:
            try:
                task.devin_mode = DevinMode(devin_mode)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid devin_mode: {devin_mode}")
        if enabled is not None:
            task.enabled = enabled
        
        task.updated_at = datetime.utcnow()
        db.commit()
        
        # Update scheduler
        if task_scheduler:
            task_scheduler.update_scheduled_task(task)
        
        return {
            "id": str(task.id),
            "message": "Scheduled task updated successfully"
        }
        
    except Exception as e:
        logger.error(f"Error updating scheduled task: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    """
    Delete a scheduled task.
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    
    try:
        # Remove from scheduler
        if task_scheduler:
            task_scheduler.remove_scheduled_task(task_id)
        
        # Delete from database
        db.delete(task)
        db.commit()
        
        return {"message": "Scheduled task deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting scheduled task: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))