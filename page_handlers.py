"""
Page handlers for different Asana operation types
"""

import logging
import json
from flask import jsonify
from datetime import datetime, timedelta
from typing import Dict, List, Any
from task_formatters import format_task_response, format_project_response, format_tasks_for_display
from utils import sanitize_form_key, parse_csv_data

logger = logging.getLogger(__name__)

def handle_task_creation_page(page_name, form_data, uploaded_files_data, 
                             server_files_data, session_id, asana_client):
    """Handle task creation requests"""
    try:
        logger.info(f"Processing task creation for page: {page_name}")
        
        # Extract task data from form
        task_data = {
            'name': form_data.get('task_name', '').strip(),
            'notes': form_data.get('task_description', '').strip(),
            'projects': [],
            'due_on': None,
            'assignee': None,
            'tags': [],
            'custom_fields': {}
        }
        
        # Validate required fields
        if not task_data['name']:
            return jsonify({'error': 'Task name is required'}), 400
        
        # Add project
        project_gid = form_data.get('project_gid')
        if project_gid:
            task_data['projects'] = [project_gid]
        
        # Add due date
        due_date = form_data.get('due_date')
        if due_date:
            task_data['due_on'] = due_date
        
        # Add assignee
        assignee_gid = form_data.get('assignee_gid')
        if assignee_gid and assignee_gid != 'unassigned':
            task_data['assignee'] = assignee_gid
        
        # Add tags
        tags = form_data.get('tags', '').split(',')
        for tag in tags:
            tag = tag.strip()
            if tag:
                # Could lookup tag GID here
                task_data['tags'].append(tag)
        
        # Process custom fields
        for key, value in form_data.items():
            if key.startswith('custom_field_'):
                field_gid = key.replace('custom_field_', '')
                task_data['custom_fields'][field_gid] = value
        
        # Process templates from server files
        if server_files_data and form_data.get('use_template'):
            template_name = form_data.get('template_name')
            if template_name in server_files_data:
                template_data = server_files_data[template_name]
                if isinstance(template_data, dict) and 'text_content' in template_data:
                    # Append template content to notes
                    task_data['notes'] += f"\n\n--- From Template ---\n{template_data['text_content']}"
        
        # Handle file attachments
        attachments = []
        for file_type, file_data in uploaded_files_data.items():
            if file_data:
                # Store file data for attachment after task creation
                attachments.append({
                    'name': f"{file_type}.{file_data.get('file_type', 'txt')}",
                    'content': file_data.get('text_content', '')
                })
        
        # Create the task
        created_task = asana_client.create_task(task_data)
        
        # Add attachments if any
        if attachments and created_task.get('gid'):
            for attachment in attachments:
                # Note: Actual file attachment would require file upload to Asana
                # For now, add as comment
                comment = f"Attachment: {attachment['name']}\n\n{attachment['content'][:500]}..."
                asana_client.add_comment_to_task(created_task['gid'], comment)
        
        # Add initial comment if provided
        initial_comment = form_data.get('initial_comment')
        if initial_comment:
            asana_client.add_comment_to_task(created_task['gid'], initial_comment)
        
        # Format response
        formatted_task = format_task_response(created_task)
        
        return jsonify({
            'success': True,
            'message': f"Task '{created_task['name']}' created successfully",
            'task': formatted_task,
            'task_url': f"https://app.asana.com/0/{project_gid}/{created_task['gid']}" if project_gid else None,
            'session_id': session_id,
            'attachments_added': len(attachments)
        })
        
    except Exception as e:
        logger.error(f"Error in task creation handler: {e}")
        return jsonify({'error': f'Failed to create task: {str(e)}'}), 500

def handle_project_dashboard_page(page_name, form_data, session_id, asana_client):
    """Handle project dashboard requests"""
    try:
        logger.info(f"Processing project dashboard for page: {page_name}")
        
        project_gid = form_data.get('project_gid')
        if not project_gid:
            return jsonify({'error': 'Project ID is required'}), 400
        
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
            tasks_by_section[section['name']] = []
        
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

def handle_bulk_update_page(page_name, form_data, uploaded_files_data, 
                           session_id, asana_client):
    """Handle bulk task update operations"""
    try:
        logger.info(f"Processing bulk update for page: {page_name}")
        
        operation = form_data.get('bulk_operation', 'update')
        
        if operation == 'create_from_csv':
            # Create tasks from CSV file
            if not uploaded_files_data:
                return jsonify({'error': 'CSV file is required for bulk creation'}), 400
            
            # Get CSV data
            csv_data = None
            for file_type, file_data in uploaded_files_data.items():
                if file_data and file_data.get('file_type') in ['csv', 'txt']:
                    csv_data = file_data.get('text_content')
                    break
            
            if not csv_data:
                return jsonify({'error': 'Valid CSV data not found'}), 400
            
            # Parse CSV
            tasks_data = parse_csv_data(csv_data)
            
            # Add project if specified
            project_gid = form_data.get('project_gid')
            if project_gid:
                for task in tasks_data:
                    task['projects'] = [project_gid]
            
            # Create tasks in batch
            result = asana_client.batch_create_tasks(tasks_data)
            
            return jsonify({
                'success': True,
                'operation': 'bulk_create',
                'created_count': result['success_count'],
                'error_count': result['error_count'],
                'errors': result['errors'],
                'session_id': session_id
            })
            
        elif operation == 'update_multiple':
            # Update multiple tasks
            task_gids = form_data.get('task_gids', '').split(',')
            if not task_gids:
                return jsonify({'error': 'Task IDs are required'}), 400
            
            # Build update data
            updates = []
            update_fields = {}
            
            if form_data.get('bulk_assignee'):
                update_fields['assignee'] = form_data.get('bulk_assignee')
            
            if form_data.get('bulk_due_date'):
                update_fields['due_on'] = form_data.get('bulk_due_date')
            
            if form_data.get('bulk_completed'):
                update_fields['completed'] = form_data.get('bulk_completed') == 'true'
            
            if form_data.get('bulk_tags'):
                update_fields['tags'] = form_data.get('bulk_tags').split(',')
            
            # Apply updates to each task
            for task_gid in task_gids:
                task_gid = task_gid.strip()
                if task_gid:
                    update = {'task_gid': task_gid}
                    update.update(update_fields)
                    updates.append(update)
            
            # Execute bulk update
            result = asana_client.batch_update_tasks(updates)
            
            return jsonify({
                'success': True,
                'operation': 'bulk_update',
                'updated_count': result['success_count'],
                'error_count': result['error_count'],
                'errors': result['errors'],
                'session_id': session_id
            })
            
        elif operation == 'archive_completed':
            # Archive completed tasks in a project
            project_gid = form_data.get('project_gid')
            if not project_gid:
                return jsonify({'error': 'Project ID is required'}), 400
            
            # Get completed tasks
            tasks = asana_client.get_project_tasks(project_gid)
            completed_tasks = [t for t in tasks if t.get('completed', False)]
            
            # Archive them (move to archive project or delete)
            archive_project_gid = form_data.get('archive_project_gid')
            archived_count = 0
            
            for task in completed_tasks:
                try:
                    if archive_project_gid:
                        # Move to archive project
                        asana_client.update_task(task['gid'], {
                            'projects': [archive_project_gid]
                        })
                    else:
                        # Just remove from current project
                        asana_client.update_task(task['gid'], {
                            'projects': []
                        })
                    archived_count += 1
                except Exception as e:
                    logger.error(f"Error archiving task {task['gid']}: {e}")
            
            return jsonify({
                'success': True,
                'operation': 'archive_completed',
                'archived_count': archived_count,
                'total_completed': len(completed_tasks),
                'session_id': session_id
            })
        
        else:
            return jsonify({'error': f'Unknown bulk operation: {operation}'}), 400
        
    except Exception as e:
        logger.error(f"Error in bulk update handler: {e}")
        return jsonify({'error': f'Bulk operation failed: {str(e)}'}), 500

def handle_search_page(page_name, form_data, session_id, asana_client):
    """Handle task search operations"""
    try:
        logger.info(f"Processing search for page: {page_name}")
        
        # Get search parameters
        search_query = form_data.get('search_query', '').strip()
        
        # Build search filters
        project_gids = None
        if form_data.get('filter_projects'):
            project_gids = form_data.get('filter_projects').split(',')
        
        assignee_gids = None
        if form_data.get('filter_assignees'):
            assignee_gids = form_data.get('filter_assignees').split(',')
        
        completed = None
        if form_data.get('filter_status'):
            completed = form_data.get('filter_status') == 'completed'
        
        modified_since = None
        if form_data.get('modified_since'):
            modified_since = form_data.get('modified_since')
        
        # Execute search
        tasks = asana_client.search_tasks(
            query=search_query,
            project_gids=project_gids,
            assignee_gids=assignee_gids,
            completed=completed,
            modified_since=modified_since
        )
        
        # Format results
        formatted_tasks = format_tasks_for_display(tasks)
        
        # Group results by project if requested
        group_by = form_data.get('group_by', 'none')
        grouped_results = {}
        
        if group_by == 'project':
            for task in formatted_tasks:
                project_name = task.get('project_name', 'No Project')
                if project_name not in grouped_results:
                    grouped_results[project_name] = []
                grouped_results[project_name].append(task)
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
            'search_query': search_query,
            'total_results': len(tasks),
            'results': grouped_results,
            'filters_applied': {
                'projects': project_gids,
                'assignees': assignee_gids,
                'status': form_data.get('filter_status'),
                'modified_since': modified_since
            },
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Error in search handler: {e}")
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

def handle_report_page(page_name, form_data, session_id, asana_client):
    """Handle report generation requests"""
    try:
        logger.info(f"Processing report for page: {page_name}")
        
        report_type = form_data.get('report_type', 'project_summary')
        
        if report_type == 'project_summary':
            # Generate project summary report
            project_gid = form_data.get('project_gid')
            if not project_gid:
                return jsonify({'error': 'Project ID is required'}), 400
            
            # Get project metrics
            metrics = asana_client.get_task_metrics(
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
            
        elif report_type == 'user_workload':
            # Generate user workload report
            user_gid = form_data.get('user_gid')  # Optional - None means all users
            
            workload = asana_client.get_user_workload(user_gid)
            
            # Sort by task count
            sorted_workload = sorted(
                workload.items(),
                key=lambda x: x[1].get('task_count', 0),
                reverse=True
            )
            
            report_data = {
                'report_type': 'User Workload',
                'workload_data': dict(sorted_workload),
                'total_users': len(workload),
                'total_tasks': sum(w.get('task_count', 0) for w in workload.values()),
                'generated_at': datetime.utcnow().isoformat()
            }
            
        elif report_type == 'overdue_tasks':
            # Generate overdue tasks report
            project_gid = form_data.get('project_gid')  # Optional
            
            # Search for incomplete tasks
            tasks = []
            if project_gid:
                tasks = asana_client.get_project_tasks(project_gid)
            else:
                # Get tasks from workspace
                tasks = asana_client.search_tasks(
                    query='',
                    completed=False
                )
            
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
            
            report_data = {
                'report_type': 'Overdue Tasks',
                'overdue_tasks': formatted_overdue,
                'total_overdue': len(overdue_tasks),
                'most_overdue': formatted_overdue[0] if formatted_overdue else None,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        elif report_type == 'productivity_trends':
            # Generate productivity trends report
            days_back = int(form_data.get('days_back', 30))
            
            # Calculate date ranges
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Get completed tasks in period
            project_gid = form_data.get('project_gid')
            
            tasks = []
            if project_gid:
                tasks = asana_client.get_project_tasks(
                    project_gid,
                    completed_since=start_date.strftime('%Y-%m-%d')
                )
            else:
                tasks = asana_client.search_tasks(
                    query='',
                    modified_since=start_date.strftime('%Y-%m-%d')
                )
            
            # Group tasks by completion date
            tasks_by_date = {}
            for task in tasks:
                if task.get('completed_at'):
                    try:
                        completed_date = datetime.strptime(
                            task['completed_at'][:10], '%Y-%m-%d'
                        ).date()
                        date_key = completed_date.strftime('%Y-%m-%d')
                        
                        if date_key not in tasks_by_date:
                            tasks_by_date[date_key] = {
                                'completed': 0,
                                'created': 0
                            }
                        
                        tasks_by_date[date_key]['completed'] += 1
                    except:
                        pass
                
                if task.get('created_at'):
                    try:
                        created_date = datetime.strptime(
                            task['created_at'][:10], '%Y-%m-%d'
                        ).date()
                        date_key = created_date.strftime('%Y-%m-%d')
                        
                        if date_key not in tasks_by_date:
                            tasks_by_date[date_key] = {
                                'completed': 0,
                                'created': 0
                            }
                        
                        tasks_by_date[date_key]['created'] += 1
                    except:
                        pass
            
            # Sort by date
            sorted_dates = sorted(tasks_by_date.items())
            
            report_data = {
                'report_type': 'Productivity Trends',
                'period_days': days_back,
                'daily_stats': dict(sorted_dates),
                'total_completed': sum(d['completed'] for d in tasks_by_date.values()),
                'total_created': sum(d['created'] for d in tasks_by_date.values()),
                'average_daily_completion': sum(d['completed'] for d in tasks_by_date.values()) / max(len(tasks_by_date), 1),
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
