import hmac
import hashlib
import json
import logging
from typing import Dict, Any, Mapping, Optional
from fastapi import HTTPException, Request
from app.core.config import settings

logger = logging.getLogger(__name__)


class GitHubWebhookHandler:
    """Handler for GitHub webhooks."""
    
    def __init__(self, default_secret: Optional[str] = None):
        self.default_secret = default_secret or settings.github_webhook_secret
    
    def verify_signature(self, payload: bytes, signature: str, secret: Optional[str] = None) -> bool:
        """
        Verify GitHub webhook signature.
        
        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value
            secret: Optional repository-specific secret (uses default if not provided)
            
        Returns:
            True if signature is valid
        """
        if not signature:
            logger.error("No signature provided")
            return False
        
        if not signature.startswith("sha256="):
            logger.error(f"Invalid signature format: {signature}")
            return False
        
        signature_hash = signature.split("=")[1]
        
        # Use repository-specific secret or default
        webhook_secret = secret or self.default_secret
        
        # Calculate expected signature
        mac = hmac.new(
            webhook_secret.encode(),
            payload,
            hashlib.sha256
        )
        expected_signature = mac.hexdigest()
        
        # Compare signatures
        if not hmac.compare_digest(signature_hash, expected_signature):
            logger.error(f"Signature mismatch: expected {expected_signature}, got {signature_hash}")
            return False
        
        return True
    
    def parse_event(self, headers: Mapping[str, str], body: bytes) -> Dict[str, Any]:
        """
        Parse GitHub webhook event.
        
        Args:
            headers: Request headers (case-insensitive mapping, e.g. starlette Headers)
            body: Request body
            
        Returns:
            Parsed event data
        """
        event_type = headers.get("X-GitHub-Event", "")
        delivery_id = headers.get("X-GitHub-Delivery", "")
        
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse webhook payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        logger.info(f"Received GitHub event: {event_type}, delivery: {delivery_id}")
        
        return {
            "event_type": event_type,
            "delivery_id": delivery_id,
            "payload": payload
        }
    
    def extract_pr_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract context from pull request event.
        
        Args:
            payload: GitHub webhook payload
            
        Returns:
            PR context data
        """
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        repository = payload.get("repository", {})
        
        pr_url = pr.get("html_url", "")
        pr_number = pr.get("number", "")
        branch = pr.get("head", {}).get("ref", "")
        base_branch = pr.get("base", {}).get("ref", "")
        title = pr.get("title", "")
        body = pr.get("body", "")
        author = pr.get("user", {}).get("login", "")
        
        repo_full_name = repository.get("full_name", "")
        repo_owner = repository.get("owner", {}).get("login", "")
        repo_name = repository.get("name", "")
        
        return {
            "action": action,
            "pr_url": pr_url,
            "pr_number": pr_number,
            "branch": branch,
            "base_branch": base_branch,
            "title": title,
            "body": body,
            "author": author,
            "repo_full_name": repo_full_name,
            "repo_owner": repo_owner,
            "repo_name": repo_name
        }
    
    def extract_issue_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract context from issue event.
        
        Args:
            payload: GitHub webhook payload
            
        Returns:
            Issue context data
        """
        action = payload.get("action", "")
        issue = payload.get("issue", {})
        repository = payload.get("repository", {})
        
        issue_url = issue.get("html_url", "")
        issue_number = issue.get("number", "")
        title = issue.get("title", "")
        body = issue.get("body", "")
        author = issue.get("user", {}).get("login", "")
        labels = [label.get("name", "") for label in issue.get("labels", [])]
        
        repo_full_name = repository.get("full_name", "")
        repo_owner = repository.get("owner", {}).get("login", "")
        repo_name = repository.get("name", "")
        
        return {
            "action": action,
            "issue_url": issue_url,
            "issue_number": issue_number,
            "title": title,
            "body": body,
            "author": author,
            "labels": labels,
            "repo_full_name": repo_full_name,
            "repo_owner": repo_owner,
            "repo_name": repo_name
        }
    
    def should_process_pr_event(self, context: Dict[str, Any]) -> bool:
        """
        Determine if a PR event should be processed.
        
        Args:
            context: PR context data
            
        Returns:
            True if event should be processed
        """
        # Process on opened and synchronize events
        action = context.get("action", "")
        return action in ["opened", "synchronize", "reopened"]
    
    def should_process_issue_event(self, context: Dict[str, Any]) -> bool:
        """
        Determine if an issue event should be processed.
        
        Args:
            context: Issue context data
            
        Returns:
            True if event should be processed
        """
        # Process on opened events
        action = context.get("action", "")
        return action == "opened"