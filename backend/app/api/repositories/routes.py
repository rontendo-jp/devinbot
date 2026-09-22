import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.auth import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.database import Repository
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()
admin = Depends(require_admin)


class RepositoryCreate(BaseModel):
    github_repo_path: str = Field(min_length=3, pattern=r"^[^/\s]+/[^/\s]+$")
    telegram_chat_id: str
    telegram_topic_id: Optional[str] = None
    devin_org_id: Optional[str] = None
    webhook_secret: Optional[str] = None
    enabled: bool = True


class RepositoryUpdate(BaseModel):
    telegram_chat_id: Optional[str] = None
    telegram_topic_id: Optional[str] = None
    webhook_secret: Optional[str] = None
    enabled: Optional[bool] = None


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


@router.post("/", dependencies=[admin])
async def create_repository(body: RepositoryCreate, db: Session = Depends(get_db)):
    """
    Create a new repository configuration (admin token required; secrets travel in the JSON body).
    """
    existing = db.query(Repository).filter(
        Repository.github_repo_path == body.github_repo_path
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Repository already exists")
    
    try:
        new_repository = Repository(
            github_repo_path=body.github_repo_path,
            telegram_chat_id=body.telegram_chat_id,
            telegram_topic_id=body.telegram_topic_id,
            devin_org_id=body.devin_org_id or settings.devin_org_id,
            webhook_secret=body.webhook_secret or settings.github_webhook_secret,
            enabled=body.enabled
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


@router.put("/{repository_id}", dependencies=[admin])
async def update_repository(repository_id: str, body: RepositoryUpdate, db: Session = Depends(get_db)):
    """
    Update a repository configuration (admin token required).
    """
    try:
        repo_uuid = uuid.UUID(repository_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository_id format")
    
    repository = db.query(Repository).filter(Repository.id == repo_uuid).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(repository, field, value)
        
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


@router.delete("/{repository_id}", dependencies=[admin])
async def delete_repository(repository_id: str, db: Session = Depends(get_db)):
    """
    Delete a repository configuration (admin token required).
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