import httpx
from typing import Optional, Dict, Any, List
from app.core.config import settings
from app.models.database import DevinMode
import logging

logger = logging.getLogger(__name__)


class DevinClient:
    """Client for interacting with Devin API v3."""
    
    def __init__(self):
        self.base_url = "https://api.devin.ai/v3"
        self.analytics_url = "https://server.codeium.com/api/v2alpha"
        self.api_key = settings.devin_api_key
        self.org_id = settings.devin_org_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def create_session(
        self,
        prompt: str,
        repos: Optional[List[str]] = None,
        devin_mode: Optional[DevinMode] = None,
        playbook_id: Optional[str] = None,
        knowledge_ids: Optional[List[str]] = None,
        secret_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        title: Optional[str] = None,
        create_as_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new Devin session.
        
        Args:
            prompt: The prompt for the session
            repos: List of repository URLs
            devin_mode: Devin agent mode (normal, fast, lite, ultra, fusion)
            playbook_id: Optional playbook ID to use
            knowledge_ids: Optional knowledge note IDs
            secret_ids: Optional secret IDs
            tags: Optional tags for the session
            title: Optional title for the session
            create_as_user_id: Optional user ID to create session as
            
        Returns:
            Session response data
        """
        url = f"{self.base_url}/organizations/{self.org_id}/sessions"
        
        payload = {
            "prompt": prompt,
            "resumable": True
        }
        
        if repos:
            payload["repos"] = repos
        if devin_mode:
            payload["devin_mode"] = devin_mode.value
        if playbook_id:
            payload["playbook_id"] = playbook_id
        if knowledge_ids:
            payload["knowledge_ids"] = knowledge_ids
        if secret_ids:
            payload["secret_ids"] = secret_ids
        if tags:
            payload["tags"] = tags
        if title:
            payload["title"] = title
        if create_as_user_id:
            payload["create_as_user_id"] = create_as_user_id
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
    
    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get details of a specific session.
        
        Args:
            session_id: The Devin session ID
            
        Returns:
            Session details
        """
        url = f"{self.base_url}/organizations/{self.org_id}/sessions/{session_id}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
    
    async def list_sessions(
        self,
        limit: int = 100,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List sessions for the organization.
        
        Args:
            limit: Maximum number of sessions to return
            status: Optional status filter
            
        Returns:
            List of sessions
        """
        url = f"{self.base_url}/organizations/{self.org_id}/sessions"
        params = {"limit": limit}
        
        if status:
            params["status"] = status
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
    
    async def terminate_session(self, session_id: str) -> Dict[str, Any]:
        """
        Terminate a running session.
        
        Args:
            session_id: The Devin session ID
            
        Returns:
            Response data
        """
        url = f"{self.base_url}/organizations/{self.org_id}/sessions/{session_id}"
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=self.headers)
            response.raise_for_status()
            return response.json() if response.content else {}
    
    async def trigger_pr_review(self, pr_url: str) -> Dict[str, Any]:
        """
        Trigger a Devin Review for a pull request.
        
        Args:
            pr_url: Full URL of the pull request
            
        Returns:
            PR review response data
        """
        url = f"{self.base_url}/organizations/{self.org_id}/pr-reviews"
        
        payload = {"pr_url": pr_url}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
    
    async def get_pr_review_status(self, pr_url: str) -> Dict[str, Any]:
        """
        Get the latest Devin Review status for a PR.
        
        Args:
            pr_url: Full URL of the pull request
            
        Returns:
            PR review status data
        """
        url = f"{self.base_url}/organizations/{self.org_id}/pr-reviews"
        params = {"pr_url": pr_url}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
    
    async def get_usage_metrics(
        self,
        time_before: Optional[int] = None,
        time_after: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated usage metrics for the organization.
        
        Args:
            time_before: Optional Unix timestamp for time range end
            time_after: Optional Unix timestamp for time range start
            
        Returns:
            Usage metrics data
        """
        url = f"{self.base_url}/organizations/{self.org_id}/metrics/usage"
        params = {}
        
        if time_before:
            params["time_before"] = time_before
        if time_after:
            params["time_after"] = time_after
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
    
    async def get_consumption_analytics(
        self,
        start_date: str,
        end_date: str,
        product: str = "agent",
        page_cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get consumption analytics from Analytics API v2.
        
        Args:
            start_date: Start of range, YYYY-MM-DD
            end_date: End of range, YYYY-MM-DD
            product: Product to report on (API currently supports "agent")
            page_cursor: Optional cursor for pagination
            
        Returns:
            Consumption analytics data
        """
        url = f"{self.analytics_url}/analytics/consumption"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "product": product,
        }
        if page_cursor:
            params["page_cursor"] = page_cursor
        
        analytics_headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=analytics_headers, params=params)
            response.raise_for_status()
            return response.json()