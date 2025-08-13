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
        """Get tasks for a project
        
        Args:
            project_gid: The project GID
            completed_since: Optional date string to include completed tasks
        """
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            params = {}
            if completed_since:
                params['completed_since'] = completed_since
            
            tasks = list(self.client.tasks.get_tasks_for_project(
                project_gid,
                params
            ))
            return tasks
        except Exception as e:
            logger.error(f"Error fetching tasks for project {project_gid}: {e}")
            raise
    
    def get_project_sections(self, project_gid: str) -> List[Dict]:
        """Get sections for a project"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            sections = list(self.client.sections.get_sections_for_project(project_gid))
            return sections
        except Exception as e:
            logger.error(f"Error fetching sections for project {project_gid}: {e}")
            raise
    
    def create_section(self, project_gid: str, section_name: str) -> Dict:
        """Create a new section in a project"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            section = self.client.sections.create_section_for_project(
                project_gid,
                {'name': section_name}
            )
            logger.info(f"Section created in project {project_gid}: {section_name}")
            return section
        except Exception as e:
            logger.error(f"Error creating section in project {project_gid}: {e}")
            raise
    
    # User Operations
    def get_users(self) -> List[Dict]:
        """Get all users in workspace"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            users = list(self.client.users.get_users(
                {'workspace': self.workspace_gid}
            ))
            return users
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            raise
    
    def get_user(self, user_gid: str) -> Dict:
        """Get user details"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            return self.client.users.get_user(user_gid)
        except Exception as e:
            logger.error(f"Error fetching user {user_gid}: {e}")
            raise
    
    def get_me(self) -> Dict:
        """Get current authenticated user"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            return self.client.users.get_user('me')
        except Exception as e:
            logger.error(f"Error fetching current user: {e}")
            raise
    
    # Tag Operations
    def get_tags(self) -> List[Dict]:
        """Get all tags in workspace"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            tags = list(self.client.tags.get_tags(
                {'workspace': self.workspace_gid}
            ))
            return tags
        except Exception as e:
            logger.error(f"Error fetching tags: {e}")
            raise
    
    def create_tag(self, tag_name: str, color: Optional[str] = None) -> Dict:
        """Create a new tag"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            tag_data = {
                'name': tag_name,
                'workspace': self.workspace_gid
            }
            if color:
                tag_data['color'] = color
            
            tag = self.client.tags.create_tag(tag_data)
            logger.info(f"Tag created: {tag_name}")
            return tag
        except Exception as e:
            logger.error(f"Error creating tag {tag_name}: {e}")
            raise
    
    def add_tag_to_task(self, task_gid: str, tag_gid: str) -> bool:
        """Add a tag to a task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            self.client.tasks.add_tag_for_task(task_gid, {'tag': tag_gid})
            logger.info(f"Tag {tag_gid} added to task {task_gid}")
            return True
        except Exception as e:
            logger.error(f"Error adding tag to task: {e}")
            raise
    
    # Custom Field Operations
    def get_custom_fields(self) -> List[Dict]:
        """Get custom fields for workspace"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            custom_fields = list(self.client.custom_fields.get_custom_fields_for_workspace(
                self.workspace_gid
            ))
            return custom_fields
        except Exception as e:
            logger.error(f"Error fetching custom fields: {e}")
            raise
    
    def get_custom_field(self, field_gid: str) -> Dict:
        """Get custom field details"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            return self.client.custom_fields.get_custom_field(field_gid)
        except Exception as e:
            logger.error(f"Error fetching custom field {field_gid}: {e}")
            raise
    
    def update_custom_field_on_task(self, task_gid: str, field_gid: str, value: Any) -> bool:
        """Update a custom field value on a task"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            # Format value based on field type
            custom_field_data = {field_gid: value}
            
            self.client.tasks.update_task(
                task_gid,
                {'custom_fields': custom_field_data}
            )
            logger.info(f"Custom field {field_gid} updated on task {task_gid}")
            return True
        except Exception as e:
            logger.error(f"Error updating custom field: {e}")
            raise
    
    # Search Operations
    def search_tasks(self, query: str, project_gids: Optional[List[str]] = None,
                    assignee_gids: Optional[List[str]] = None,
                    completed: Optional[bool] = None,
                    modified_since: Optional[str] = None) -> List[Dict]:
        """Search for tasks with various filters"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            search_params = {
                'workspace': self.workspace_gid,
                'text': query
            }
            
            if project_gids:
                search_params['projects.any'] = ','.join(project_gids)
            
            if assignee_gids:
                search_params['assignee.any'] = ','.join(assignee_gids)
            
            if completed is not None:
                search_params['completed'] = completed
            
            if modified_since:
                search_params['modified_since'] = modified_since
            
            tasks = list(self.client.workspaces.search_tasks_for_workspace(
                self.workspace_gid,
                search_params
            ))
            
            logger.info(f"Search returned {len(tasks)} tasks")
            return tasks
            
        except Exception as e:
            logger.error(f"Error searching tasks: {e}")
            raise
    
    # Batch Operations
    def batch_create_tasks(self, tasks_data: List[Dict[str, Any]]) -> List[Dict]:
        """Create multiple tasks in batch"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        created_tasks = []
        errors = []
        
        for task_data in tasks_data:
            try:
                if 'workspace' not in task_data:
                    task_data['workspace'] = self.workspace_gid
                
                task = self.create_task(task_data)
                created_tasks.append(task)
                
                # Small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                errors.append({
                    'task_name': task_data.get('name', 'Unknown'),
                    'error': str(e)
                })
                logger.error(f"Error creating task in batch: {e}")
        
        result = {
            'created': created_tasks,
            'errors': errors,
            'success_count': len(created_tasks),
            'error_count': len(errors)
        }
        
        logger.info(f"Batch creation: {len(created_tasks)} succeeded, {len(errors)} failed")
        return result
    
    def batch_update_tasks(self, updates: List[Dict[str, Any]]) -> Dict:
        """Update multiple tasks in batch
        
        Args:
            updates: List of dicts with 'task_gid' and update data
        """
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        updated_tasks = []
        errors = []
        
        for update in updates:
            try:
                task_gid = update.pop('task_gid')
                updated_task = self.update_task(task_gid, update)
                updated_tasks.append(updated_task)
                
                # Small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                errors.append({
                    'task_gid': update.get('task_gid', 'Unknown'),
                    'error': str(e)
                })
                logger.error(f"Error updating task in batch: {e}")
        
        result = {
            'updated': updated_tasks,
            'errors': errors,
            'success_count': len(updated_tasks),
            'error_count': len(errors)
        }
        
        logger.info(f"Batch update: {len(updated_tasks)} succeeded, {len(errors)} failed")
        return result
    
    # Report Generation
    def get_task_metrics(self, project_gid: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None) -> Dict:
        """Get task metrics for reporting"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            # Get tasks based on filters
            if project_gid:
                tasks = self.get_project_tasks(project_gid, completed_since=start_date)
            else:
                # Get all tasks in workspace (limited)
                tasks = list(self.client.tasks.get_tasks({
                    'workspace': self.workspace_gid,
                    'modified_since': start_date if start_date else None,
                    'limit': 100
                }))
            
            # Calculate metrics
            total_tasks = len(tasks)
            completed_tasks = sum(1 for t in tasks if t.get('completed', False))
            overdue_tasks = 0
            
            today = datetime.now().date()
            for task in tasks:
                if not task.get('completed') and task.get('due_on'):
                    due_date = datetime.strptime(task['due_on'], '%Y-%m-%d').date()
                    if due_date < today:
                        overdue_tasks += 1
            
            metrics = {
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
    
    def get_user_workload(self, user_gid: Optional[str] = None) -> Dict:
        """Get workload information for a user or all users"""
        if not self.is_connected():
            raise Exception("Asana client not connected")
        
        try:
            workload = {}
            
            if user_gid:
                # Get tasks for specific user
                tasks = list(self.client.tasks.get_tasks({
                    'workspace': self.workspace_gid,
                    'assignee': user_gid,
                    'completed': False
                }))
                
                user = self.get_user(user_gid)
                workload[user['name']] = {
                    'task_count': len(tasks),
                    'tasks': tasks
                }
            else:
                # Get workload for all users
                users = self.get_users()
                for user in users:
                    tasks = list(self.client.tasks.get_tasks({
                        'workspace': self.workspace_gid,
                        'assignee': user['gid'],
                        'completed': False,
                        'limit': 50
                    }))
                    
                    workload[user['name']] = {
                        'task_count': len(tasks),
                        'user_gid': user['gid']
                    }
            
            return workload
            
        except Exception as e:
            logger.error(f"Error getting user workload: {e}")
            raise
