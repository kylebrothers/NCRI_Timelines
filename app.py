"""
Main Flask application for Asana Integration Platform
"""

from flask import render_template, request, jsonify, session, send_file, abort
from datetime import datetime
import os
import re
import json

# Import modular components
from config import create_app, setup_logging, setup_rate_limiter, ensure_directories
from asana_client import AsanaClient
from file_processors import process_uploaded_file, validate_file, load_server_files
from page_handlers import (
    handle_project_finder_page,
    handle_project_dashboard_page,
    handle_task_view_page,
    handle_search_page,
    handle_report_page
)
from utils import get_session_id, get_server_files_info, sanitize_form_key
from task_formatters import format_task_response, format_project_response
from comment_tagger import handle_comment_tagger_page
from segmentation_trainer import handle_segmentation_trainer_page

# Initialize application components
app = create_app()
logger = setup_logging()
limiter = setup_rate_limiter(app)

# Initialize Asana client
asana_client = AsanaClient()

# Ensure required directories exist
ensure_directories()

# Log initialization status
if asana_client.is_connected():
    logger.info("Application initialized successfully with Asana API")
else:
    logger.warning("Application initialized without Asana API connection")

# Routes
@app.route('/')
def home():
    """Home page with workspace overview"""
    session_id = get_session_id()
    logger.info(f"Home page accessed - Session: {session_id}")
    
    # Get workspace info if connected
    workspace_info = None
    if asana_client.is_connected():
        try:
            workspace_info = asana_client.get_workspace_info()
        except Exception as e:
            logger.error(f"Error fetching workspace info: {e}")
    
    return render_template('home.html', workspace_info=workspace_info)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'asana_connected': asana_client.is_connected(),
        'workspace_id': os.environ.get('ASANA_WORKSPACE_GID', 'not_configured')
    })

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/<page_name>')
def generic_page(page_name):
    """Serve any page that has a corresponding template"""
    session_id = get_session_id()
    logger.info(f"Page accessed: {page_name} - Session: {session_id}")
    
    # Simply add .html extension - preserve original naming
    template_name = page_name + '.html'
    
    # Get page-specific configuration using original name
    page_config = get_page_configuration(page_name)
    
    # Load server files if specified using original name
    server_files_info = []
    if page_config.get('load_server_files'):
        directories = page_config.get('directories', [page_name])
        try:
            server_files_info = get_server_files_info(page_name, directories)
            logger.info(f"Server files loaded for {page_name}: {len(server_files_info)} files")
        except Exception as e:
            logger.error(f"Error loading server files for {page_name}: {e}")
    
    # Get Asana-specific data if needed
    asana_data = {}
    if page_config.get('preload_asana_data'):
        asana_data = preload_asana_data(page_config)
    
    try:
        return render_template(
            template_name,
            page_name=page_name,
            server_files_info=server_files_info,
            asana_data=asana_data,
            page_config=page_config
        )
    except Exception as e:
        logger.error(f"Template error for {template_name}: {e}")
        return render_template('404.html'), 404

@app.route('/api/<page_name>', methods=['POST'])
@limiter.limit("10 per minute")
def generic_api(page_name):
    """Generic API endpoint for Asana operations"""
    try:
        # Check Asana connection
        if not asana_client.is_connected():
            return jsonify({'error': 'Asana API not connected'}), 503
        
        # Handle file uploads
        uploaded_files_data = {}
        for field_name in request.files:
            file = request.files[field_name]
            if file and file.filename:
                is_valid, message = validate_file(file)
                if not is_valid:
                    return jsonify({'error': f'{field_name}: {message}'}), 400
                
                try:
                    file_data = process_uploaded_file(file)
                    if file_data:
                        clean_field_name = field_name.replace('_file', '').replace('_', ' ')
                        uploaded_files_data[clean_field_name] = file_data
                        logger.info(f"File processed: {file.filename} for {field_name}")
                except Exception as e:
                    return jsonify({'error': f'Error processing {field_name}: {str(e)}'}), 400
        
        # Get page configuration using original name
        page_config = get_page_configuration(page_name)
        
        # Load server files if needed using original name
        server_files_data = {}
        if page_config.get('load_server_files'):
            directories = page_config.get('directories', [page_name])
            server_files_data = load_server_files(page_name, directories)
        
        # Handle form data
        form_data = request.form.to_dict()
        session_id = get_session_id()
        
        logger.info(f"API called for: {page_name} - Session: {session_id}")
        
        # Route to appropriate handler based on page type
        page_type = form_data.get('page_type', 'asana-call')
        
        if page_type == 'project-finder':
            return handle_project_finder_page(
                page_name, form_data, session_id, asana_client
            )
        elif page_type == 'project-dashboard':
            return handle_project_dashboard_page(
                page_name, form_data, session_id, asana_client
            )
        elif page_type == 'task-view':
            return handle_task_view_page(
                page_name, form_data, session_id, asana_client
            )
        elif page_type == 'search':
            return handle_search_page(
                page_name, form_data, session_id, asana_client
            )
        elif page_type == 'report':
            return handle_report_page(
                page_name, form_data, session_id, asana_client
            )
        elif page_type == 'comment-tagger':
            return handle_comment_tagger_page(
                page_name, form_data, session_id, asana_client
            )
        elif page_type == 'segmentation-trainer':
            return handle_segmentation_trainer_page(
                page_name, form_data, session_id, asana_client
            )
        else:
            return jsonify({'error': f'Unknown page type: {page_type}'}), 400
    
    except Exception as e:
        logger.error(f"Error in API for {page_name}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/asana/project/<project_gid>', methods=['GET'])
def get_project(project_gid):
    """Get specific project details"""
    try:
        if not asana_client.is_connected():
            return jsonify({'error': 'Asana not connected'}), 503
        
        project = asana_client.get_project(project_gid)
        formatted_project = format_project_response(project)
        return jsonify(formatted_project)
    except Exception as e:
        logger.error(f"Error fetching project {project_gid}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/asana/project/<project_gid>/tasks', methods=['GET'])
def get_project_tasks(project_gid):
    """Get tasks for a specific project"""
    try:
        if not asana_client.is_connected():
            return jsonify({'error': 'Asana not connected'}), 503
        
        tasks = asana_client.get_project_tasks(project_gid)
        return jsonify({'tasks': tasks})
    except Exception as e:
        logger.error(f"Error fetching tasks for project {project_gid}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/asana/task/<task_gid>', methods=['GET'])
def get_task(task_gid):
    """Get specific task details"""
    try:
        if not asana_client.is_connected():
            return jsonify({'error': 'Asana not connected'}), 503
        
        task = asana_client.get_task(task_gid)
        formatted_task = format_task_response(task)
        return jsonify(formatted_task)
    except Exception as e:
        logger.error(f"Error fetching task {task_gid}: {e}")
        return jsonify({'error': str(e)}), 500

# Helper functions
def get_page_configuration(page_name):
    """Get configuration for a specific page - uses exact page name"""
    # Uses exact page name as provided (with hyphens or underscores as appropriate)
    configurations = {
        'project-finder': {
            'page_type': 'project-finder',
            'load_server_files': False,
            'preload_asana_data': []
        },
        'project-dashboard': {
            'page_type': 'project-dashboard',
            'load_server_files': False,
            'preload_asana_data': []
        },
        'task-view': {
            'page_type': 'task-view',
            'load_server_files': False,
            'preload_asana_data': []
        },
        'task-search': {
            'page_type': 'search',
            'load_server_files': False,
            'preload_asana_data': []
        },
        'project-report': {
            'page_type': 'report',
            'load_server_files': False,
            'preload_asana_data': []
        },
        'comment_tagger': {
            'page_type': 'comment-tagger',
            'load_server_files': True,  # Since we're using server_files for storage
            'preload_asana_data': []
        },
        'comment-tagger': {  # Support both naming conventions
            'page_type': 'comment-tagger',
            'load_server_files': True,
            'preload_asana_data': []
        },
        'segmentation_trainer': {
            'page_type': 'segmentation-trainer',
            'load_server_files': True,
            'preload_asana_data': []
        },
        'segmentation-trainer': {  # Support both naming conventions
            'page_type': 'segmentation-trainer',
            'load_server_files': True,
            'preload_asana_data': []
        }
    }
    
    return configurations.get(page_name, {
        'page_type': 'asana-call',
        'load_server_files': False,
        'preload_asana_data': []
    })

def preload_asana_data(page_config):
    """Preload Asana data based on page configuration"""
    data = {}
    
    if not asana_client.is_connected():
        return data
    
    try:
        # Only load specific data as needed
        # No longer loading all projects or all users
        
        # Get current user info
        if 'current_user' in page_config.get('preload_asana_data', []):
            data['current_user'] = asana_client.get_me()
        
    except Exception as e:
        logger.error(f"Error preloading Asana data: {e}")
    
    return data

# Error handlers
@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 10MB.'}), 413

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(404)
def not_found(e):
    try:
        return render_template('404.html'), 404
    except:
        return '''
        <html><body>
        <h1>404 Page Not Found</h1>
        <p>The page you're looking for doesn't exist.</p>
        <a href="/">Go Home</a>
        </body></html>
        ''', 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    try:
        return render_template('500.html'), 500
    except:
        return '''
        <html><body>
        <h1>500 Internal Server Error</h1>
        <p>The server encountered an internal error.</p>
        <a href="/">Go Home</a>
        </body></html>
        ''', 500

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    )
