import logging
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.github_webhook import GitHubWebhookHandler
from app.services.devin_client import DevinClient
from app.services.telegram_bot import TelegramBotService
from app.models.database import Repository, Session, TriggerType, SessionStatus, DevinMode
import json

logger = logging.getLogger(__name__)

router = APIRouter()
webhook_handler = GitHubWebhookHandler()
devin_client = DevinClient()


async def process_pr_event(context: dict, db: Session, telegram_service: TelegramBotService):
    """Process a pull request event by creating a Devin session."""
    try:
        repo_full_name = context.get("repo_full_name")
        pr_url = context.get("pr_url")
        
        # Find repository in database
        repository = db.query(Repository).filter(
            Repository.github_repo_path == repo_full_name,
            Repository.enabled == True
        ).first()
        
        if not repository:
            logger.warning(f"Repository {repo_full_name} not found or disabled")
            return
        
        # Create prompt for PR review
        prompt = f"""
Review this pull request:
PR URL: {pr_url}
PR Number: {context.get('pr_number')}
Title: {context.get('title')}
Author: {context.get('author')}
Branch: {context.get('branch')} -> {context.get('base_branch')}

Please review the changes, check for issues, and provide feedback.
"""
        
        # Create Devin session
        session_response = await devin_client.create_session(
            prompt=prompt,
            repos=[f"https://github.com/{repo_full_name}"],
            title=f"PR Review: {context.get('pr_number')}"
        )
        
        devin_session_id = session_response.get("id")
        
        # Create session record
        new_session = Session(
            devin_session_id=devin_session_id,
            repository_id=repository.id,
            trigger_type=TriggerType.PR_REVIEW,
            trigger_context=json.dumps(context),
            status=SessionStatus.RUNNING,
            prompt=prompt,
            devin_mode=DevinMode.NORMAL
        )
        db.add(new_session)
        db.commit()
        
        # Send Telegram notification
        await telegram_service.send_session_notification(
            chat_id=repository.telegram_chat_id,
            topic_id=repository.telegram_topic_id,
            session_data={
                "status": "running",
                "repository_name": repo_full_name,
                "session_id": devin_session_id,
                "trigger_type": "pr_review"
            }
        )
        
        logger.info(f"Created Devin session {devin_session_id} for PR review")
        
    except Exception as e:
        logger.error(f"Error processing PR event: {e}")
        db.rollback()


async def process_issue_event(context: dict, db: Session, telegram_service: TelegramBotService):
    """Process an issue event by creating a Devin session."""
    try:
        repo_full_name = context.get("repo_full_name")
        issue_url = context.get("issue_url")
        
        # Find repository in database
        repository = db.query(Repository).filter(
            Repository.github_repo_path == repo_full_name,
            Repository.enabled == True
        ).first()
        
        if not repository:
            logger.warning(f"Repository {repo_full_name} not found or disabled")
            return
        
        # Create prompt for issue resolution
        labels = ", ".join(context.get("labels", []))
        prompt = f"""
Work on this GitHub issue:
Issue URL: {issue_url}
Issue Number: {context.get('issue_number')}
Title: {context.get('title')}
Author: {context.get('author')}
Labels: {labels}

Description:
{context.get('body', 'No description provided')}

Please analyze the issue and implement a solution.
"""
        
        # Create Devin session
        session_response = await devin_client.create_session(
            prompt=prompt,
            repos=[f"https://github.com/{repo_full_name}"],
            title=f"Issue: {context.get('issue_number')} - {context.get('title')}"
        )
        
        devin_session_id = session_response.get("id")
        
        # Create session record
        new_session = Session(
            devin_session_id=devin_session_id,
            repository_id=repository.id,
            trigger_type=TriggerType.ISSUE,
            trigger_context=json.dumps(context),
            status=SessionStatus.RUNNING,
            prompt=prompt,
            devin_mode=DevinMode.NORMAL
        )
        db.add(new_session)
        db.commit()
        
        # Send Telegram notification
        await telegram_service.send_session_notification(
            chat_id=repository.telegram_chat_id,
            topic_id=repository.telegram_topic_id,
            session_data={
                "status": "running",
                "repository_name": repo_full_name,
                "session_id": devin_session_id,
                "trigger_type": "issue"
            }
        )
        
        logger.info(f"Created Devin session {devin_session_id} for issue resolution")
        
    except Exception as e:
        logger.error(f"Error processing issue event: {e}")
        db.rollback()


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Handle GitHub webhooks for PR and issue events.
    """
    # Get signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    # Get raw body
    body = await request.body()
    
    # First verify with default secret to allow initial parsing
    if not webhook_handler.verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse event
    event_data = webhook_handler.parse_event(request.headers, body)
    
    event_type = event_data["event_type"]
    payload = event_data["payload"]
    
    # Extract repository information to get repo-specific secret
    repo_full_name = None
    if event_type == "pull_request":
        context = webhook_handler.extract_pr_context(payload)
        repo_full_name = context.get("repo_full_name")
    elif event_type == "issues":
        context = webhook_handler.extract_issue_context(payload)
        repo_full_name = context.get("repo_full_name")
    
    # Look up repository to get its specific webhook secret
    repository = None
    if repo_full_name:
        repository = db.query(Repository).filter(
            Repository.github_repo_path == repo_full_name
        ).first()
    
    # Re-verify with repository-specific secret if available
    if repository and repository.webhook_secret:
        if not webhook_handler.verify_signature(body, signature, repository.webhook_secret):
            logger.error(f"Repository-specific signature verification failed for {repo_full_name}")
            raise HTTPException(status_code=401, detail="Invalid repository-specific signature")
        logger.info(f"Verified with repository-specific secret for {repo_full_name}")
    
    # Get telegram service (will be injected via dependency later)
    # For now, we'll create a simple instance
    telegram_service = TelegramBotService()
    
    # Process based on event type
    if event_type == "pull_request":
        context = webhook_handler.extract_pr_context(payload)
        if webhook_handler.should_process_pr_event(context):
            background_tasks.add_task(process_pr_event, context, db, telegram_service)
    
    elif event_type == "issues":
        context = webhook_handler.extract_issue_context(payload)
        if webhook_handler.should_process_issue_event(context):
            background_tasks.add_task(process_issue_event, context, db, telegram_service)
    
    return {"status": "received", "event_type": event_type}