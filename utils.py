# utils.py
"""
Utility functions for the Asana Integration Platform
"""

import os
import uuid
import csv
import io
import logging
from flask import session
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def get_session_id():
    """Generate or retrieve session ID"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_server_files_info(page_name, directories=None):
    """Get information about available server files"""
    server_files_info = []
    
    if directories is None:
        directories = [page_name]
    
    for directory in directories:
        server_dir = f"/app/server_files/{directory}"
        
        if not os.path.exists(server_dir):
            continue
        
        try:
            for filename in os.listdir(server_dir):
                file_path = os.path.join(server_dir, filename)
                
                if not os.path.isfile(file_path):
                    continue
                
                file_stat = os.stat(file_path)
                file_size = file_stat.st_size
                
                # Format file size
                if file_size < 1024:
                    size_str = f"{file_size} B"
                elif file_size < 1024 * 1024:
                    size_str = f"{file_size / 1024:.1f} KB"
                else:
                    size_str = f"{file_size / (1024 * 1024):.1f} MB"
                
                # Get file type
                file_ext = os.path.splitext(filename)[1].lower()
                file_types = {
                    '.csv': 'CSV File',
                    '.xlsx': 'Excel File',
                    '.json': 'JSON File',
                    '.txt': 'Text File',
                    '.md': 'Markdown File'
                }
                file_type = file_types.get(file_ext, 'Unknown')
                
                # Create display name
                display_name = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').title()
                if len(directories) > 1 and directory != page_name:
                    display_name = f"{directory.title()} - {display_name}"
                
                file_info = {
                    'filename': filename,
                    'display_name': display_name,
                    'file_type': file_type,
                    'size': size_str,
                    'supported': file_ext in ['.csv', '.xlsx', '.json', '.txt'],
                    'source_directory': directory
                }
                
                server_files_info.append(file_info)
        
        except Exception as e:
            logger.error(f"Error listing files in {server_dir}: {e}")
    
    return sorted(server_files_info, key=lambda x: x['display_name'])

def sanitize_form_key(key):
    """Sanitize form key for display"""
    return key.replace('_', ' ').title()

def parse_csv_data(csv_content: str) -> List[Dict[str, Any]]:
    """Parse CSV content into task data"""
    tasks = []
    
    try:
        csv_file = io.StringIO(csv_content)
        reader = csv.DictReader(csv_file)
        
        for row in reader:
            task = {
                'name': row.get('name', row.get('title', row.get('task', ''))),
                'notes': row.get('notes', row.get('description', '')),
                'due_on': row.get('due_date', row.get('due_on', '')),
                'assignee': row.get('assignee', row.get('assigned_to', '')),
                'tags': []
            }
            
            # Parse tags if present
            if row.get('tags'):
                task['tags'] = [tag.strip() for tag in row['tags'].split(',')]
            
            # Only add if task has a name
            if task['name']:
                tasks.append(task)
    
    except Exception as e:
        logger.error(f"Error parsing CSV data: {e}")
        raise ValueError(f"Failed to parse CSV: {str(e)}")
    
    return tasks

def validate_asana_gid(gid: str) -> bool:
    """Validate Asana GID format"""
    if not gid:
        return False
    
    # Asana GIDs are numeric strings
    return gid.isdigit()

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
