"""
Page handlers for read-only Asana operations
"""

import logging
import json
from flask import jsonify
from datetime import datetime, timedelta
from typing import Dict, List, Any
from task_formatters import format_task_response, format_project_response, format_tasks_for_display
from utils import sanitize_form_key

logger = logging.getLogger(__name__)

def handle_project_finder_page(page_name, form_data, session_id, asana_client):
    """Handle project finder requests"""
    try:
        operation = form_data.get('operation')
        
        if operation == 'find_by_name':
            project_name = form_data.get('project_name', '').strip()
            if not project_name:
                return jsonify({'error': 'Project name is required'}), 400
            
            logger.info(f"Searching for project: {project_name}")
            project = asana_client.find_project_by_name(project_name)
            
            if project:
                return jsonify({
                    'success': True,
                    'project': project,
                    'session_id': session_id
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'No project found containing "{project_name}"',
                    'session_id': session_id
                })
        
        elif operation == 'get_by_gid':
            project_gid = form_data.get('project_gid', '').strip()
            if not project_gid:
                return jsonify({'error': 'Project GID is required'}), 400
            
            logger.info(f"Getting project details for GID: {project_gid}")
            project = asana_client.get_project(project_gid)
            
            return jsonify({
                'success': True,
                'project': format_project_response(project),
                'session_id': session_id
            })
        
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
            
    except Exception as e:
        logger.error(f"Error in project finder: {e}")
        return jsonify({'error': str(e)}), 500

def handle_project_dashboard_page(page_name, form_data, session_id, asana_client):
    """Handle project dashboard requests for a specific project GID"""
    try:
        logger.info(f"Processing project dashboard for page: {page_name}")
        
        project_gid = form_data.get('project_gid')
        if not project_gid:
            return jsonify({'error': 'Project GID is required'}), 400
        
        # Get project details
        project = asana_client.get_project(project_gid)
        
        # Get project sections
        sections = asana_client.get_project_sections(project_gid)
        
        # Get project tasks
        include_completed = form_data.get('include_completed', 'false').lower() == 'true'
        completed_since = None
        if include_completed:
            # Include tasks completed in last 30 days
            completed_since = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        tasks = asana_client.get_project_tasks(project_gid, completed_since)
        
        # Organize tasks by section
        tasks_by_section = {'No Section': []}
        for section in sections:
            section_name = section.get('name', 'Unknown Section')
            tasks_by_section[section_name] = []
        
        # Group tasks (simplified - actual implementation would need section membership)
        for task in tasks:
            # This is simplified - actual tasks would have section info
            tasks_by_section['No Section'].append(task)
        
        # Calculate project metrics
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
        
        # Format response
        dashboard_data = {
            'project': format_project_response(project),
            'sections': sections,
            'tasks_by_section': tasks_by_section,
            'metrics': {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'incomplete_tasks': total_tasks - completed_tasks,
                'overdue_tasks': overdue_tasks,
                'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            },
            'task_count_by_section': {
                section: len(tasks_list) 
                for section, tasks_list in tasks_by_section.items()
            }
        }
        
        return jsonify({
            'success': True,
            'dashboard': dashboard_data,
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in project dashboard handler: {e}")
        return jsonify({'error': f'Failed to load dashboard: {str(e)}'}), 500

def handle_task_view_page(page_name, form_data, session_id, asana_client):
    """Handle viewing task details (read-only)"""
    try:
        task_gid = form_data.get('task_gid')
        if not task_gid:
            return jsonify({'error': 'Task GID is required'}), 400
        
        # Get task details
        task = asana_client.get_task(task_gid)
        
        # Get task comments/stories
        stories = asana_client.get_task_stories(task_gid)
        
        # Format response
        formatted_task = format_task_response(task)
        formatted_task['stories'] = stories
        
        return jsonify({
            'success': True,
            'task': formatted_task,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Error in task view handler: {e}")
        return jsonify({'error': f'Failed to load task: {str(e)}'}), 500

def handle_search_page(page_name, form_data, session_id, asana_client):
    """Handle task search operations within a specific project"""
    try:
        logger.info(f"Processing search for page: {page_name}")
        
        # Require project GID for searching
        project_gid = form_data.get('project_gid')
        if not project_gid:
            return jsonify({'error': 'Project GID is required for search'}), 400
        
        # Get search query
        search_query = form_data.get('search_query', '').strip()
        if not search_query:
            return jsonify({'error': 'Search query is required'}), 400
        
        # Search within the project
        tasks = asana_client.search_tasks_in_project(project_gid, search_query)
        
        # Format results
        formatted_tasks = format_tasks_for_display(tasks)
        
        # Group results by status if requested
        group_by = form_data.get('group_by', 'none')
        grouped_results = {}
        
        if group_by == 'status':
            for task in formatted_tasks:
                status = task.get('status', 'active')
                if status not in grouped_results:
                    grouped_results[status] = []
                grouped_results[status].append(task)
        elif group_by == 'assignee':
            for task in formatted_tasks:
                assignee_name = task.get('assignee_name', 'Unassigned')
                if assignee_name not in grouped_results:
                    grouped_results[assignee_name] = []
                grouped_results[assignee_name].append(task)
        else:
            grouped_results['All Tasks'] = formatted_tasks
        
        return jsonify({
            'success': True,
            'project_gid': project_gid,
            'search_query': search_query,
            'total_results': len(tasks),
            'results': grouped_results,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Error in search handler: {e}")
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

def handle_report_page(page_name, form_data, session_id, asana_client):
    """Handle report generation for specific projects"""
    try:
        logger.info(f"Processing report for page: {page_name}")
        
        report_type = form_data.get('report_type', 'project_summary')
        project_gid = form_data.get('project_gid')
        
        if not project_gid:
            return jsonify({'error': 'Project GID is required for reports'}), 400
        
        if report_type == 'project_summary':
            # Generate project summary report
            metrics = asana_client.get_task_metrics_for_project(
                project_gid=project_gid,
                start_date=form_data.get('start_date'),
                end_date=form_data.get('end_date')
            )
            
            # Get project details
            project = asana_client.get_project(project_gid)
            
            report_data = {
                'report_type': 'Project Summary',
                'project': format_project_response(project),
                'metrics': metrics,
                'period': {
                    'start': form_data.get('start_date', 'All time'),
                    'end': form_data.get('end_date', 'Present')
                },
                'generated_at': datetime.utcnow().isoformat()
            }
            
        elif report_type == 'task_list':
            # Generate task list report for the project
            tasks = asana_client.get_project_tasks(
                project_gid,
                completed_since=form_data.get('completed_since')
            )
            
            # Format tasks
            formatted_tasks = format_tasks_for_display(tasks)
            
            # Get project details
            project = asana_client.get_project(project_gid)
            
            report_data = {
                'report_type': 'Task List',
                'project': format_project_response(project),
                'tasks': formatted_tasks,
                'total_tasks': len(formatted_tasks),
                'generated_at': datetime.utcnow().isoformat()
            }
            
        elif report_type == 'overdue_tasks':
            # Generate overdue tasks report for the project
            tasks = asana_client.get_project_tasks(project_gid)
            
            # Filter overdue tasks
            overdue_tasks = []
            today = datetime.now().date()
            
            for task in tasks:
                if not task.get('completed') and task.get('due_on'):
                    try:
                        due_date = datetime.strptime(task['due_on'], '%Y-%m-%d').date()
                        if due_date < today:
                            days_overdue = (today - due_date).days
                            task['days_overdue'] = days_overdue
                            overdue_tasks.append(task)
                    except:
                        pass
            
            # Sort by days overdue
            overdue_tasks.sort(key=lambda x: x.get('days_overdue', 0), reverse=True)
            
            # Format tasks
            formatted_overdue = format_tasks_for_display(overdue_tasks)
            
            # Get project details
            project = asana_client.get_project(project_gid)
            
            report_data = {
                'report_type': 'Overdue Tasks',
                'project': format_project_response(project),
                'overdue_tasks': formatted_overdue,
                'total_overdue': len(overdue_tasks),
                'most_overdue': formatted_overdue[0] if formatted_overdue else None,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        else:
            return jsonify({'error': f'Unknown report type: {report_type}'}), 400
        
        return jsonify({
            'success': True,
            'report': report_data,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Error in report handler: {e}")
        return jsonify({'error': f'Report generation failed: {str(e)}'}), 500
