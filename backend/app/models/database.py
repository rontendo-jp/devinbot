from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

Base = declarative_base()


class TriggerType(str, enum.Enum):
    PR_REVIEW = "pr_review"
    ISSUE = "issue"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class SessionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DevinMode(str, enum.Enum):
    NORMAL = "normal"
    FAST = "fast"
    LITE = "lite"
    ULTRA = "ultra"
    FUSION = "fusion"


class Repository(Base):
    __tablename__ = "repositories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_repo_path = Column(String(255), unique=True, nullable=False, index=True)
    telegram_chat_id = Column(String(50), nullable=False)
    telegram_topic_id = Column(String(50), nullable=True)
    devin_org_id = Column(String(100), nullable=False)
    webhook_secret = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sessions = relationship("Session", back_populates="repository", cascade="all, delete-orphan")
    scheduled_tasks = relationship("ScheduledTask", back_populates="repository", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    devin_session_id = Column(String(100), nullable=True, index=True)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id"), nullable=False)
    trigger_type = Column(SQLEnum(TriggerType), nullable=False)
    trigger_context = Column(Text, nullable=True)  # JSON string
    status = Column(SQLEnum(SessionStatus), default=SessionStatus.PENDING, nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    devin_mode = Column(SQLEnum(DevinMode), default=DevinMode.NORMAL)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    repository = relationship("Repository", back_populates="sessions")


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id"), nullable=False)
    name = Column(String(255), nullable=False)
    cron_expression = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=False)
    devin_mode = Column(SQLEnum(DevinMode), default=DevinMode.NORMAL)
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    repository = relationship("Repository", back_populates="scheduled_tasks")