"""
Asana API client wrapper for simplified operations
"""

import os
import logging
import asana
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

class AsanaClient:
    """Wrapper class for Asana API operations"""
    
    def __init__(self):
        """Initialize Asana client with environment credentials"""
        self.client = None
        self.workspace_gid = os.environ.get('ASANA_WORKSPACE_GID')
        self.access_token = os.environ.get('ASANA_ACCESS_TOKEN')
        
        if self.access_token:
            try:
                self.client = asana.Client.access_token(self.access_token)
                # Enable auto-retry for rate limits
                self.client.options['max_retries'] = 3
                self.client.options['full_payload'] = True
                
                # Test connection
                if self.workspace_gid:
                    self.client.workspaces.get_workspace(self.workspace_gid)
                    logger.info(f"Asana client initialized for workspace: {self.workspace_gid}")
                else:
                    # Get first available workspace
                    workspaces = list(self.client.workspaces.get_workspaces())
                    if workspaces:
                        self.workspace_gid = workspaces[0]['gid']
                        logger.info(f"Using first available workspace: {self.workspace_gid}")
                    else:
                        logger.error("No workspaces available")
                        self.client = None
                        
            except Exception as e:
                logger.error(f"Failed to initialize Asana client: {e}")
                self.client = None
        else:
            logger.warning("No Asana access token provided")
    
    def is_connected(self) -> bool:
        """Check if client is connected to Asana"""
        return self.client is not None
    
    def get_workspace_info(self) -> Optional[Dict]:
        """Get current workspace information"""
        if not self.is_connected():
            return None
        
        try:
            workspace = self.client.workspaces.get_workspace(self.workspace_gid)
            return {
                'gid': workspace['gid'],
                'name': workspace['name'],
                'is_organization': workspace.get('is_organization', False)
            }
        except Exception as e:
            logger.error(f"Error fetching workspace info: {e}")
            return None
    
    # Task Operations
    def create_task(self, task_data: Dict[str, Any]) -> Dict:
        """Create a new task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            # Add workspace if not specified
            if 'workspace' not in task_data:
                task_data['workspace'] = self.workspace_gid
            
            # Handle file attachments if present
            attachments = task_data.pop('attachments', [])
            
            # Create the task
            result = self.client.tasks.create_task(task_data)
            
            # Add attachments if any
            if attachments and result.get('gid'):
                for attachment in attachments:
                    self.attach_file_to_task(result['gid'], attachment)
            
            logger.info(f"Task created: {result.get('gid')}")
            return result
            
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            raise
    
    def get_task(self, task_gid: str) -> Dict:
        """Get task details"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            return self.client.tasks.get_task(task_gid)
        except Exception as e:
            logger.error(f"Error fetching task {task_gid}: {e}")
            raise
    
    def update_task(self, task_gid: str, update_data: Dict[str, Any]) -> Dict:
        """Update an existing task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            result = self.client.tasks.update_task(task_gid, update_data)
            logger.info(f"Task updated: {task_gid}")
            return result
        except Exception as e:
            logger.error(f"Error updating task {task_gid}: {e}")
            raise
    
    def delete_task(self, task_gid: str) -> bool:
        """Delete a task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            self.client.tasks.delete_task(task_gid)
            logger.info(f"Task deleted: {task_gid}")
            return True
        except Exception as e:
            logger.error(f"Error deleting task {task_gid}: {e}")
            raise
    
    def add_comment_to_task(self, task_gid: str, comment_text: str) -> Dict:
        """Add a comment to a task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            story = self.client.stories.create_story_for_task(
                task_gid,
                {'text': comment_text}
            )
            logger.info(f"Comment added to task {task_gid}")
            return story
        except Exception as e:
            logger.error(f"Error adding comment to task {task_gid}: {e}")
            raise
    
    def attach_file_to_task(self, task_gid: str, file_data: Dict) -> Dict:
        """Attach a file to a task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            # file_data should contain 'file' (file object) and 'name'
            attachment = self.client.attachments.create_attachment_for_task(
                task_gid,
                file=file_data['file'],
                name=file_data.get('name', 'attachment')
            )
            logger.info(f"File attached to task {task_gid}")
            return attachment
        except Exception as e:
            logger.error(f"Error attaching file to task {task_gid}: {e}")
            raise
    
    # Project Operations
    def get_projects(self) -> List[Dict]:
        """Get all projects in workspace"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            projects = list(self.client.projects.get_projects(
                {'workspace': self.workspace_gid}
            ))
            return projects
        except Exception as e:
            logger.error(f"Error fetching projects: {e}")
            raise
    
    def get_project(self, project_gid: str) -> Dict:
        """Get project details"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            return self.client.projects.get_project(project_gid)
        except Exception as e:
            logger.error(f"Error fetching project {project_gid}: {e}")
            raise
    
    def create_project(self, project_data: Dict[str, Any]) -> Dict:
        """Create a new project"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            if 'workspace' not in project_data:
                project_data['workspace'] = self.workspace_gid
            
            result = self.client.projects.create_project(project_data)
            logger.info(f"Project created: {result.get('gid')}")
            return result
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            raise
    
    def get_project_tasks(self, project_gid: str, 
                         completed_since: Optional[str] = None) -> List[Dict]:
        """
