"""
Formatting utilities for Asana data
"""

from datetime import datetime
from typing import Dict, List, Any, Optional

def format_task_response(task: Dict[str, Any]) -> Dict[str, Any]:
    """Format task data for frontend display"""
    if not task:
        return {}
    
    formatted = {
        'gid': task.get('gid'),
        'name': task.get('name', 'Untitled Task'),
        'notes': task.get('notes', ''),
        'completed': task.get('completed', False),
        'completed_at': format_datetime(task.get('completed_at')),
        'created_at': format_datetime(task.get('created_at')),
        'modified_at': format_datetime(task.get('modified_at')),
        'due_on': task.get('due_on'),
        'due_at': format_datetime(task.get('due_at')),
        'assignee': None,
        'assignee_name': 'Unassigned',
        'projects': [],
        'project_names': [],
        'tags': [],
        'custom_fields': [],
        'num_subtasks': task.get('num_subtasks', 0),
        'num_hearts': task.get('num_hearts', 0),
        'liked': task.get('liked', False),
        'permalink_url': task.get('permalink_url')
    }
    
    # Format assignee
    if task.get('assignee'):
        assignee = task['assignee']
        formatted['assignee'] = assignee.get('gid')
        formatted['assignee_name'] = assignee.get('name', 'Unknown User')
        formatted['assignee_email'] = assignee.get('email')
    
    # Format projects
    if task.get('projects'):
        for project in task['projects']:
            formatted['projects'].append(project.get('gid'))
            formatted['project_names'].append(project.get('name', 'Unknown Project'))
    
    # Format tags
    if task.get('tags'):
        for tag in task['tags']:
            formatted['tags'].append({
                'gid': tag.get('gid'),
                'name': tag.get('name'),
                'color': tag.get('color')
            })
    
    # Format custom fields
    if task.get('custom_fields'):
        for field in task['custom_fields']:
            formatted_field = {
                'gid': field.get('gid'),
                'name': field.get('name'),
                'type': field.get('type'),
                'value': format_custom_field_value(field)
            }
            formatted['custom_fields'].append(formatted_field)
    
    # Calculate status
    if formatted['completed']:
        formatted['status'] = 'completed'
    elif formatted['due_on']:
        try:
            due_date = datetime.strptime(formatted['due_on'], '%Y-%m-%d').date()
            today = datetime.now().date()
            if due_date < today:
                formatted['status'] = 'overdue'
            elif due_date == today:
                formatted['status'] = 'due_today'
            else:
                formatted['status'] = 'upcoming'
        except:
            formatted['status'] = 'active'
    else:
        formatted['status'] = 'active'
    
    return formatted

def format_project_response(project: Dict[str, Any]) -> Dict[str, Any]:
    """Format project data for frontend display"""
    if not project:
        return {}
    
    formatted = {
        'gid': project.get('gid'),
        'name': project.get('name', 'Untitled Project'),
        'notes': project.get('notes', ''),
        'color': project.get('color'),
        'created_at': format_datetime(project.get('created_at')),
        'modified_at': format_datetime(project.get('modified_at')),
        'due_date': project.get('due_date'),
        'start_on': project.get('start_on'),
        'archived': project.get('archived', False),
        'public': project.get('public', True),
        'owner': None,
        'owner_name': 'Unknown',
        'team': None,
        'team_name': None,
        'members': [],
        'custom_fields': [],
        'permalink_url': project.get('permalink_url')
    }
    
    # Format owner
    if project.get('owner'):
        owner = project['owner']
        formatted['owner'] = owner.get('gid')
        formatted['owner_name'] = owner.get('name', 'Unknown User')
    
    # Format team
    if project.get('team'):
        team = project['team']
        formatted['team'] = team.get('gid')
        formatted['team_name'] = team.get('name')
    
    # Format members
    if project.get('members'):
        for member in project['members']:
            formatted['members'].append({
                'gid': member.get('gid'),
                'name': member.get('name'),
                'email': member.get('email')
            })
    
    # Format custom field settings
    if project.get('custom_field_settings'):
        for setting in project['custom_field_settings']:
            field = setting.get('custom_field', {})
            formatted['custom_fields'].append({
                'gid': field.get('gid'),
                'name': field.get('name'),
                'type': field.get('type'),
                'is_important': setting.get('is_important', False)
            })
    
    # Calculate project status
    if formatted['archived']:
        formatted['status'] = 'archived'
    elif formatted['due_date']:
        try:
            due_date = datetime.strptime(formatted['due_date'], '%Y-%m-%d').date()
            today = datetime.now().date()
            if due_date < today:
                formatted['status'] = 'overdue'
            elif (due_date - today).days <= 7:
                formatted['status'] = 'due_soon'
            else:
                formatted['status'] = 'on_track'
        except:
            formatted['status'] = 'active'
    else:
        formatted['status'] = 'active'
    
    return formatted

def format_tasks_for_display(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format a list of tasks for display"""
    formatted_tasks = []
    
    for task in tasks:
        formatted = format_task_response(task)
        
        # Add simplified display fields
        formatted['display_assignee'] = formatted['assignee_name']
        formatted['display_project'] = ', '.join(formatted['project_names']) if formatted['project_names'] else 'No Project'
        formatted['display_due'] = format_due_date_display(formatted['due_on'])
        formatted['display_status'] = format_status_display(formatted['status'])
        
        formatted_tasks.append(formatted)
    
    return formatted_tasks

def format_custom_field_value(field: Dict[str, Any]) -> Any:
    """Format custom field value based on type"""
    field_type = field.get('type')
    
    if field_type == 'text':
        return field.get('text_value', '')
    elif field_type == 'number':
        return field.get('number_value')
    elif field_type == 'enum':
        enum_value = field.get('enum_value')
        if enum_value:
            return enum_value.get('name')
        return None
    elif field_type == 'multi_enum':
        values = field.get('multi_enum_values', [])
        return [v.get('name') for v in values]
    elif field_type == 'date':
        date_value = field.get('date_value')
        if date_value:
            return format_date_display(date_value.get('date'))
        return None
    elif field_type == 'people':
        people = field.get('people_value', [])
        return [p.get('name') for p in people]
    else:
        return field.get('display_value')

def format_datetime(datetime_str: Optional[str]) -> Optional[str]:
    """Format datetime string for display"""
    if not datetime_str:
        return None
    
    try:
        dt = datetime.strptime(datetime_str[:19], '%Y-%m-%dT%H:%M:%S')
        return dt.strftime('%Y-%m-%d %H:%M')
    except:
        return datetime_str

def format_date_display(date_str: Optional[str]) -> str:
    """Format date for user-friendly display"""
    if not date_str:
        return 'No date'
    
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        diff = (date - today).days
        
        if diff == 0:
            return 'Today'
        elif diff == 1:
            return 'Tomorrow'
        elif diff == -1:
            return 'Yesterday'
        elif 0 < diff <= 7:
            return f'In {diff} days'
        elif -7 <= diff < 0:
            return f'{abs(diff)} days ago'
        else:
            return date.strftime('%b %d, %Y')
    except:
        return date_str

def format_due_date_display(due_date: Optional[str]) -> str:
    """Format due date for display with urgency indicators"""
    if not due_date:
        return 'No due date'
    
    try:
        date = datetime.strptime(due_date, '%Y-%m-%d').date()
        today = datetime.now().date()
        diff = (date - today).days
        
        if diff < 0:
            return f'⚠️ Overdue by {abs(diff)} days'
        elif diff == 0:
            return '🔴 Due today'
        elif diff == 1:
            return '🟡 Due tomorrow'
        elif diff <= 3:
            return f'🟡 Due in {diff} days'
        elif diff <= 7:
            return f'Due in {diff} days'
        else:
            return date.strftime('%b %d, %Y')
    except:
        return due_date

def format_status_display(status: str) -> str:
    """Format status with emoji indicators"""
    status_map = {
        'completed': '✅ Completed',
        'overdue': '⚠️ Overdue',
        'due_today': '🔴 Due Today',
        'upcoming': '📅 Upcoming',
        'active': '🔵 Active',
        'archived': '📦 Archived',
        'on_track': '✅ On Track',
        'due_soon': '🟡 Due Soon'
    }
    
    return status_map.get(status, status.title())

def format_workload_summary(workload_data: Dict[str, Any]) -> str:
    """Format workload data into a summary string"""
    if not workload_data:
        return "No workload data available"
    
    summary_parts = []
    
    for user_name, data in workload_data.items():
        task_count = data.get('task_count', 0)
        if task_count == 0:
            summary_parts.append(f"{user_name}: No tasks")
        elif task_count == 1:
            summary_parts.append(f"{user_name}: 1 task")
        else:
            summary_parts.append(f"{user_name}: {task_count} tasks")
    
    return " | ".join(summary_parts)

def format_metrics_summary(metrics: Dict[str, Any]) -> Dict[str, str]:
    """Format metrics data for display"""
    formatted = {
        'total': f"{metrics.get('total_tasks', 0)} tasks",
        'completed': f"{metrics.get('completed_tasks', 0)} completed",
        'incomplete': f"{metrics.get('incomplete_tasks', 0)} incomplete",
        'overdue': f"{metrics.get('overdue_tasks', 0)} overdue",
        'completion_rate': f"{metrics.get('completion_rate', 0):.1f}% complete"
    }
    
    # Add emoji indicators based on performance
    completion_rate = metrics.get('completion_rate', 0)
    if completion_rate >= 80:
        formatted['performance'] = '🟢 Excellent'
    elif completion_rate >= 60:
        formatted['performance'] = '🟡 Good'
    elif completion_rate >= 40:
        formatted['performance'] = '🟠 Needs Attention'
    else:
        formatted['performance'] = '🔴 Critical'
    
    return formatted
