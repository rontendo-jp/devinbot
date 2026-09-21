import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.database import Repository
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def list_repositories(
    enabled_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    List all repositories.
    """
    query = db.query(Repository)
    
    if enabled_only:
        query = query.filter(Repository.enabled == True)
    
    repositories = query.order_by(Repository.github_repo_path).all()
    
    return {
        "repositories": [
            {
                "id": str(repo.id),
                "github_repo_path": repo.github_repo_path,
                "telegram_chat_id": repo.telegram_chat_id,
                "telegram_topic_id": repo.telegram_topic_id,
                "devin_org_id": repo.devin_org_id,
                "enabled": repo.enabled,
                "created_at": repo.created_at.isoformat(),
                "updated_at": repo.updated_at.isoformat()
            }
            for repo in repositories
        ],
        "count": len(repositories)
    }


@router.post("/")
async def create_repository(
    github_repo_path: str,
    telegram_chat_id: str,
    telegram_topic_id: Optional[str] = None,
    devin_org_id: Optional[str] = None,
    webhook_secret: Optional[str] = None,
    enabled: bool = True,
    db: Session = Depends(get_db)
):
    """
    Create a new repository configuration.
    """
    from app.core.config import settings
    
    # Use default org_id if not provided
    if not devin_org_id:
        devin_org_id = settings.devin_org_id
    
    # Check if repository already exists
    existing = db.query(Repository).filter(
        Repository.github_repo_path == github_repo_path
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Repository already exists")
    
    try:
        new_repository = Repository(
            github_repo_path=github_repo_path,
            telegram_chat_id=telegram_chat_id,
            telegram_topic_id=telegram_topic_id,
            devin_org_id=devin_org_id,
            webhook_secret=webhook_secret or settings.github_webhook_secret,
            enabled=enabled
        )
        db.add(new_repository)
        db.commit()
        db.refresh(new_repository)
        
        return {
            "id": str(new_repository.id),
            "github_repo_path": new_repository.github_repo_path,
            "enabled": new_repository.enabled,
            "message": "Repository created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating repository: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{repository_id}")
async def get_repository(repository_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific repository.
    """
    try:
        repo_uuid = uuid.UUID(repository_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository_id format")
    
    repository = db.query(Repository).filter(Repository.id == repo_uuid).first()
    
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    return {
        "id": str(repository.id),
        "github_repo_path": repository.github_repo_path,
        "telegram_chat_id": repository.telegram_chat_id,
        "telegram_topic_id": repository.telegram_topic_id,
        "devin_org_id": repository.devin_org_id,
        "enabled": repository.enabled,
        "created_at": repository.created_at.isoformat(),
        "updated_at": repository.updated_at.isoformat()
    }


@router.put("/{repository_id}")
async def update_repository(
    repository_id: str,
    telegram_chat_id: Optional[str] = None,
    telegram_topic_id: Optional[str] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Update a repository configuration.
    """
    try:
        repo_uuid = uuid.UUID(repository_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository_id format")
    
    repository = db.query(Repository).filter(Repository.id == repo_uuid).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        if telegram_chat_id is not None:
            repository.telegram_chat_id = telegram_chat_id
        if telegram_topic_id is not None:
            repository.telegram_topic_id = telegram_topic_id
        if enabled is not None:
            repository.enabled = enabled
        
        repository.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "id": str(repository.id),
            "message": "Repository updated successfully"
        }
        
    except Exception as e:
        logger.error(f"Error updating repository: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{repository_id}")
async def delete_repository(repository_id: str, db: Session = Depends(get_db)):
    """
    Delete a repository configuration.
    """
    try:
        repo_uuid = uuid.UUID(repository_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository_id format")
    
    repository = db.query(Repository).filter(Repository.id == repo_uuid).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        db.delete(repository)
        db.commit()
        
        return {"message": "Repository deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting repository: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))