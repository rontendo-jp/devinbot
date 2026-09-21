import logging
from typing import Optional, Dict, Any, Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from datetime import datetime
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.database import ScheduledTask, Repository, Session, TriggerType, SessionStatus, DevinMode
from app.services.devin_client import DevinClient
import json

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Scheduler for managing recurring Devin tasks."""
    
    def __init__(self):
        # Configure job store for persistence
        jobstores = {
            'default': SQLAlchemyJobStore(url=settings.database_url)
        }
        
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)
        self.devin_client = DevinClient()
    
    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Task scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Task scheduler stopped")
    
    async def execute_scheduled_task(self, task_id: str):
        """
        Execute a scheduled task by creating a Devin session.
        
        Args:
            task_id: The scheduled task ID
        """
        db = SessionLocal()
        try:
            # Get the scheduled task
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                logger.error(f"Scheduled task {task_id} not found")
                return
            
            if not task.enabled:
                logger.info(f"Scheduled task {task_id} is disabled, skipping")
                return
            
            # Get repository context
            repository = db.query(Repository).filter(Repository.id == task.repository_id).first()
            if not repository:
                logger.error(f"Repository {task.repository_id} not found for task {task_id}")
                return
            
            logger.info(f"Executing scheduled task {task_id} for repository {repository.github_repo_path}")
            
            # Create Devin session
            try:
                session_response = await self.devin_client.create_session(
                    prompt=task.prompt,
                    repos=[f"https://github.com/{repository.github_repo_path}"],
                    devin_mode=DevinMode(task.devin_mode),
                    title=f"Scheduled: {task.name}"
                )
                
                devin_session_id = session_response.get("id")
                
                # Create session record in database
                new_session = Session(
                    devin_session_id=devin_session_id,
                    repository_id=repository.id,
                    trigger_type=TriggerType.SCHEDULED,
                    trigger_context=json.dumps({
                        "scheduled_task_id": str(task.id),
                        "task_name": task.name
                    }),
                    status=SessionStatus.RUNNING,
                    prompt=task.prompt,
                    devin_mode=DevinMode(task.devin_mode)
                )
                db.add(new_session)
                
                # Update task last run time
                task.last_run_at = datetime.utcnow()
                db.commit()
                
                logger.info(f"Created Devin session {devin_session_id} for scheduled task {task_id}")
                
            except Exception as e:
                logger.error(f"Failed to create Devin session for scheduled task {task_id}: {e}")
                
                # Create failed session record
                new_session = Session(
                    repository_id=repository.id,
                    trigger_type=TriggerType.SCHEDULED,
                    trigger_context=json.dumps({
                        "scheduled_task_id": str(task.id),
                        "task_name": task.name
                    }),
                    status=SessionStatus.FAILED,
                    prompt=task.prompt,
                    devin_mode=DevinMode(task.devin_mode),
                    error_message=str(e)
                )
                db.add(new_session)
                db.commit()
                
        except Exception as e:
            logger.error(f"Error executing scheduled task {task_id}: {e}")
            db.rollback()
        finally:
            db.close()
    
    def add_scheduled_task(self, task: ScheduledTask):
        """
        Add a scheduled task to the scheduler.
        
        Args:
            task: The scheduled task object
        """
        try:
            # Parse cron expression
            trigger = CronTrigger.from_crontab(task.cron_expression)
            
            # Add job to scheduler
            self.scheduler.add_job(
                self.execute_scheduled_task,
                trigger=trigger,
                args=[str(task.id)],
                id=str(task.id),
                replace_existing=True,
                name=task.name
            )
            
            logger.info(f"Added scheduled task {task.id} with cron expression: {task.cron_expression}")
            
        except Exception as e:
            logger.error(f"Failed to add scheduled task {task.id}: {e}")
            raise
    
    def remove_scheduled_task(self, task_id: str):
        """
        Remove a scheduled task from the scheduler.
        
        Args:
            task_id: The scheduled task ID
        """
        try:
            self.scheduler.remove_job(task_id)
            logger.info(f"Removed scheduled task {task_id}")
        except Exception as e:
            logger.error(f"Failed to remove scheduled task {task_id}: {e}")
    
    def update_scheduled_task(self, task: ScheduledTask):
        """
        Update a scheduled task in the scheduler.
        
        Args:
            task: The scheduled task object
        """
        # Remove existing job if it exists
        try:
            self.scheduler.remove_job(str(task.id))
        except:
            pass
        
        # Add updated job
        if task.enabled:
            self.add_scheduled_task(task)
    
    def load_scheduled_tasks(self):
        """Load all enabled scheduled tasks from database and add to scheduler."""
        db = SessionLocal()
        try:
            tasks = db.query(ScheduledTask).filter(ScheduledTask.enabled == True).all()
            for task in tasks:
                try:
                    self.add_scheduled_task(task)
                except Exception as e:
                    logger.error(f"Failed to load scheduled task {task.id}: {e}")
            
            logger.info(f"Loaded {len(tasks)} scheduled tasks")
        finally:
            db.close()
    
    def get_next_run_time(self, task_id: str) -> Optional[datetime]:
        """
        Get the next run time for a scheduled task.
        
        Args:
            task_id: The scheduled task ID
            
        Returns:
            Next run time or None
        """
        try:
            job = self.scheduler.get_job(task_id)
            if job:
                return job.next_run_time
        except:
            pass
        return None