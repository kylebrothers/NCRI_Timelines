"""
Tag Manager page handler for renaming tags
"""

import os
import json
import logging
from flask import jsonify

logger = logging.getLogger(__name__)

def handle_tag_manager_page(page_name, form_data, session_id, asana_client):
    """Handle tag manager operations"""
    try:
        operation = form_data.get('operation')
        base_path = "/app/server_files/comment_tagger"
        
        if operation == 'load_tags':
            # Load tag definitions
            tag_definitions_path = os.path.join(base_path, "tag_definitions.json")
            
            if os.path.exists(tag_definitions_path):
                with open(tag_definitions_path, 'r') as f:
                    tags = json.load(f)
            else:
                tags = {}
            
            return jsonify({
                'success': True,
                'tags': tags,
                'session_id': session_id
            })
        
        elif operation == 'save_tags':
            # Save updated tag definitions
            tags_data = json.loads(form_data.get('tags', '{}'))
            
            tag_definitions_path = os.path.join(base_path, "tag_definitions.json")
            
            with open(tag_definitions_path, 'w') as f:
                json.dump(tags_data, f, indent=2)
            
            logger.info(f"Updated {len(tags_data)} tag definitions")
            
            return jsonify({
                'success': True,
                'message': f'Successfully updated {len(tags_data)} tags',
                'session_id': session_id
            })
        
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
            
    except Exception as e:
        logger.error(f"Error in tag manager handler: {e}")
        return jsonify({'error': str(e)}), 500
