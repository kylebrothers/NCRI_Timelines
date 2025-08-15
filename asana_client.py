"""
Asana API client wrapper for read-only operations
"""

import os
import logging
import asana
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class AsanaClient:
    """Wrapper class for Asana API read-only operations"""
    
    def __init__(self):
        """Initialize Asana client with environment credentials"""
        self.api_client = None
        self.workspace_gid = os.environ.get('ASANA_WORKSPACE_GID')
        self.access_token = os.environ.get('ASANA_ACCESS_TOKEN')
        
        # API instances
        self.users_api = None
        self.workspaces_api = None
        self.projects_api = None
        self.tasks_api = None
        self.sections_api = None
        self.tags_api = None
        self.custom_fields_api = None
        
        if self.access_token:
            try:
                # Initialize with modern API format
                configuration = asana.Configuration()
                configuration.access_token = self.access_token
                self.api_client = asana.ApiClient(configuration)
                
                # Create API instances
                self.users_api = asana.UsersApi(self.api_client)
                self.workspaces_api = asana.WorkspacesApi(self.api_client)
                self.projects_api = asana.ProjectsApi(self.api_client)
                self.tasks_api = asana.TasksApi(self.api_client)
                self.sections_api = asana.SectionsApi(self.api_client)
                self.tags_api = asana.TagsApi(self.api_client)
                self.custom_fields_api = asana.CustomFieldsApi(self.api_client)
                
                # Test connection and get workspace
                if self.workspace_gid:
                    workspace = self.workspaces_api.get_workspace(self.workspace_gid, {})
                    logger.info(f"Asana client initialized for workspace: {self.workspace_gid}")
                else:
                    # Get first available workspace
                    workspaces = list(self.workspaces_api.get_workspaces({}))
                    if workspaces:
                        self.workspace_gid = workspaces[0].get('gid') if isinstance(workspaces[0], dict) else workspaces[0].gid
                        logger.info(f"Using first available workspace: {self.workspace_gid}")
                    else:
                        logger.error("No workspaces available")
                        self.api_client = None
                        
            except Exception as e:
                logger.error(f"Failed to initialize Asana client: {e}")
                self.api_client = None
        else:
            logger.warning("No Asana access token provided")
    
    def is_connected(self) -> bool:
        """Check if client is connected to Asana"""
        return self.api_client is not None
    
    def get_workspace_info(self) -> Optional[Dict]:
        """Get current workspace information"""
        if not self.is_connected():
            return None
        
        try:
            workspace = self.workspaces_api.get_workspace(self.workspace_gid, {})
            # Handle both dict and object responses
            if isinstance(workspace, dict):
                return workspace
            else:
                return {
                    'gid': workspace.gid if hasattr(workspace, 'gid') else workspace.get('gid'),
                    'name': workspace.name if hasattr(workspace, 'name') else workspace.get('name'),
                    'is_organization': workspace.is_organization if hasattr(workspace, 'is_organization') else workspace.get('is_organization', False)
                }
        except Exception as e:
            logger.error(f"Error fetching workspace info: {e}")
            return None
    
    # Project Operations (Read-Only)
    def find_project_by_name(self, project_name: str) -> Optional[Dict]:
        """Find a project by name (searches through projects)"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            logger.info(f"Searching for project: {project_name}")
            # Iterate through projects to find match
            for project in self.projects_api.get_projects({'workspace': self.workspace_gid}):
                # Handle both dict and object responses
                if isinstance(project, dict):
                    proj_name = project.get('name', '')
                    proj_gid = project.get('gid')
                else:
                    proj_name = project.name if hasattr(project, 'name') else ''
                    proj_gid = project.gid if hasattr(project, 'gid') else None
                
                if project_name.lower() in proj_name.lower():
                    logger.info(f"Found project: {proj_name} (GID: {proj_gid})")
                    return {
                        'gid': proj_gid,
                        'name': proj_name
                    }
            
            logger.warning(f"Project not found: {project_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching for project: {e}")
            raise
    
    def get_project(self, project_gid: str) -> Dict:
        """Get project details by GID"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            project = self.projects_api.get_project(project_gid, {})
            # Handle both dict and object responses
            if isinstance(project, dict):
                return project
            else:
                # Convert object to dict
                return self._object_to_dict(project)
        except Exception as e:
            logger.error(f"Error fetching project {project_gid}: {e}")
            raise
    
    def get_project_tasks(self, project_gid: str, 
                         completed_since: Optional[str] = None,
                         limit: int = 100) -> List[Dict]:
        """Get tasks for a specific project by GID"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            params = {'limit': limit}
            if completed_since:
                params['completed_since'] = completed_since
            
            tasks = []
            for task in self.tasks_api.get_tasks_for_project(project_gid, params):
                if isinstance(task, dict):
                    tasks.append(task)
                else:
                    tasks.append(self._object_to_dict(task))
                
                # Stop at limit
                if len(tasks) >= limit:
                    break
            
            return tasks
        except Exception as e:
            logger.error(f"Error fetching tasks for project {project_gid}: {e}")
            raise
    
    def get_project_sections(self, project_gid: str) -> List[Dict]:
        """Get sections for a project"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            sections = []
            for section in self.sections_api.get_sections_for_project(project_gid, {}):
                if isinstance(section, dict):
                    sections.append(section)
                else:
                    sections.append(self._object_to_dict(section))
            return sections
        except Exception as e:
            logger.error(f"Error fetching sections for project {project_gid}: {e}")
            raise
    
    # Task Operations (Read-Only)
    def get_task(self, task_gid: str) -> Dict:
        """Get task details"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            task = self.tasks_api.get_task(task_gid, {})
            if isinstance(task, dict):
                return task
            else:
                return self._object_to_dict(task)
        except Exception as e:
            logger.error(f"Error fetching task {task_gid}: {e}")
            raise
    
    def get_task_stories(self, task_gid: str) -> List[Dict]:
        """Get comments/stories for a task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            stories = []
            stories_api = asana.StoriesApi(self.api_client)
            for story in stories_api.get_stories_for_task(task_gid, {}):
                if isinstance(story, dict):
                    stories.append(story)
                else:
                    stories.append(self._object_to_dict(story))
            return stories
        except Exception as e:
            logger.error(f"Error fetching stories for task {task_gid}: {e}")
            raise
    
    # User Operations (Read-Only)
    def get_user(self, user_gid: str) -> Dict:
        """Get user details"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            user = self.users_api.get_user(user_gid, {})
            if isinstance(user, dict):
                return user
            else:
                return self._object_to_dict(user)
        except Exception as e:
            logger.error(f"Error fetching user {user_gid}: {e}")
            raise
    
    def get_me(self) -> Dict:
        """Get current authenticated user"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            user = self.users_api.get_user('me', {})
            if isinstance(user, dict):
                return user
            else:
                return self._object_to_dict(user)
        except Exception as e:
            logger.error(f"Error fetching current user: {e}")
            raise
    
    # Search Operations
    def search_tasks_in_project(self, project_gid: str, query: str) -> List[Dict]:
        """Search for tasks within a specific project"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            # Get all tasks for the project and filter
            all_tasks = self.get_project_tasks(project_gid)
            
            # Filter tasks by search query
            matching_tasks = []
            query_lower = query.lower()
            
            for task in all_tasks:
                task_name = task.get('name', '').lower()
                task_notes = task.get('notes', '').lower()
                
                if query_lower in task_name or query_lower in task_notes:
                    matching_tasks.append(task)
            
            logger.info(f"Found {len(matching_tasks)} tasks matching '{query}' in project {project_gid}")
            return matching_tasks
            
        except Exception as e:
            logger.error(f"Error searching tasks: {e}")
            raise
    
    # Report Generation
    def get_task_metrics_for_project(self, project_gid: str,
                                    start_date: Optional[str] = None,
                                    end_date: Optional[str] = None) -> Dict:
        """Get task metrics for a specific project"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            # Get tasks for the project
            tasks = self.get_project_tasks(project_gid, completed_since=start_date)
            
            # Calculate metrics
            total_tasks = len(tasks)
            completed_tasks = sum(1 for t in tasks if t.get('completed', False))
            overdue_tasks = 0
            
            today = datetime.now().date()
            for task in tasks:
                if not task.get('completed') and task.get('due_on'):
                    try:
                        due_date = datetime.strptime(task['due_on'], '%Y-%m-%d').date()
                        if due_date < today:
                            overdue_tasks += 1
                    except:
                        pass
            
            metrics = {
                'project_gid': project_gid,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'incomplete_tasks': total_tasks - completed_tasks,
                'overdue_tasks': overdue_tasks,
                'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error generating task metrics: {e}")
            raise
    
    # Utility methods
    def _object_to_dict(self, obj) -> Dict:
        """Convert an API object to a dictionary"""
        if isinstance(obj, dict):
            return obj
        
        result = {}
        for attr in dir(obj):
            if not attr.startswith('_'):
                value = getattr(obj, attr)
                if not callable(value):
                    result[attr] = value
        return result
