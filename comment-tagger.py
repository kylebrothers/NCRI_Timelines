"""
Comment tagging page handler for training NLP classification of Asana comments
"""

import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from flask import jsonify
from collections import defaultdict

logger = logging.getLogger(__name__)

class CommentTagger:
    """Handles comment tagging operations and pattern learning"""
    
    def __init__(self, base_path="/app/server_files/comment_tags"):
        self.base_path = base_path
        self.ensure_directories()
        
        # Load or initialize data structures
        self.tag_definitions = self.load_json("tag_definitions.json", {})
        self.training_data = self.load_json("training_data.json", [])
        self.patterns = self.load_json("patterns.json", {})
        self.model_cache = self.load_json("model_cache.json", {})
        
    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        os.makedirs(self.base_path, exist_ok=True)
        
    def load_json(self, filename: str, default: Any) -> Any:
        """Load JSON file or return default if not exists"""
        filepath = os.path.join(self.base_path, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {filename}: {e}")
        return default
    
    def save_json(self, filename: str, data: Any):
        """Save data to JSON file"""
        filepath = os.path.join(self.base_path, filename)
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {filename}")
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
    
    def extract_date_from_comment(self, comment: str) -> Optional[str]:
        """Extract date from comment text using regex patterns"""
        # Patterns for various date formats
        patterns = [
            r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY or M/D/YYYY
            r'(\d{1,2}/\d{1,2}/\d{2})',    # MM/DD/YY or M/D/YY
            r'(\d{1,2}/\d{1,2})',          # MM/DD or M/D (no year)
            r'(\d{1,2}-\d{1,2}-\d{4})',    # MM-DD-YYYY
            r'(\d{4}-\d{1,2}-\d{1,2})',    # YYYY-MM-DD
        ]
        
        for pattern in patterns:
            match = re.search(pattern, comment)
            if match:
                date_str = match.group(1)
                # Normalize date format
                try:
                    # Handle different formats and missing years
                    if '/' in date_str and len(date_str.split('/')[-1]) == 2:
                        # Add 20 prefix for 2-digit years
                        parts = date_str.split('/')
                        parts[-1] = '20' + parts[-1]
                        date_str = '/'.join(parts)
                    elif '/' in date_str and len(date_str.split('/')) == 2:
                        # No year provided, use current year
                        date_str += f"/{datetime.now().year}"
                    
                    return date_str
                except:
                    pass
        
        return None
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text"""
        # Remove date patterns first
        text_no_date = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]?\d{0,4}', '', text)
        
        # Convert to lowercase and extract words
        words = re.findall(r'\b[a-z]+\b', text_no_date.lower())
        
        # Filter common words (basic stopwords)
        stopwords = {'i', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 
                    'to', 'for', 'of', 'with', 'by', 'from', 'was', 'were', 'been',
                    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                    'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that'}
        
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        
        # Also extract 2-word phrases
        if len(words) > 1:
            for i in range(len(words) - 1):
                if words[i] not in stopwords and words[i+1] not in stopwords:
                    keywords.append(f"{words[i]} {words[i+1]}")
        
        return keywords
    
    def calculate_tag_confidence(self, comment: str, tag: str) -> float:
        """Calculate confidence score for a tag based on patterns"""
        if tag not in self.patterns:
            return 0.0
        
        comment_lower = comment.lower()
        tag_patterns = self.patterns[tag]
        
        # Check keyword matches
        keyword_score = 0
        if 'keywords' in tag_patterns:
            for keyword in tag_patterns['keywords']:
                if keyword.lower() in comment_lower:
                    keyword_score += tag_patterns['keywords'][keyword]
        
        # Check phrase matches
        phrase_score = 0
        if 'phrases' in tag_patterns:
            for phrase in tag_patterns['phrases']:
                if phrase.lower() in comment_lower:
                    phrase_score += tag_patterns['phrases'][phrase]
        
        # Combine scores (normalize to 0-1 range)
        total_score = (keyword_score + phrase_score * 2) / 10
        return min(1.0, total_score)
    
    def suggest_tags(self, comment: str) -> List[Dict[str, Any]]:
        """Suggest tags for a comment based on learned patterns"""
        suggestions = []
        
        # If we have defined tags, check each one
        for tag_id, tag_info in self.tag_definitions.items():
            confidence = self.calculate_tag_confidence(comment, tag_id)
            if confidence > 0.1:  # Threshold for suggestion
                suggestions.append({
                    'tag_id': tag_id,
                    'tag_name': tag_info.get('name', tag_id),
                    'confidence': confidence,
                    'auto_selected': confidence > 0.7  # Auto-select high confidence
                })
        
        # Sort by confidence
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)
        
        # If no good suggestions, propose "unknown" or "review needed"
        if not suggestions or suggestions[0]['confidence'] < 0.3:
            suggestions.insert(0, {
                'tag_id': '_suggest_new_',
                'tag_name': 'Suggest New Tag',
                'confidence': 0.0,
                'auto_selected': False
            })
        
        return suggestions
    
    def learn_from_tagging(self, comment: str, assigned_tags: List[str]):
        """Update patterns based on user's tagging decision"""
        keywords = self.extract_keywords(comment)
        
        for tag in assigned_tags:
            if tag not in self.patterns:
                self.patterns[tag] = {'keywords': {}, 'phrases': {}}
            
            # Update keyword frequencies
            for keyword in keywords:
                if ' ' in keyword:  # It's a phrase
                    if keyword not in self.patterns[tag]['phrases']:
                        self.patterns[tag]['phrases'][keyword] = 0
                    self.patterns[tag]['phrases'][keyword] += 1
                else:  # Single word
                    if keyword not in self.patterns[tag]['keywords']:
                        self.patterns[tag]['keywords'][keyword] = 0
                    self.patterns[tag]['keywords'][keyword] += 1
        
        # Save training data
        self.training_data.append({
            'comment': comment,
            'date_extracted': self.extract_date_from_comment(comment),
            'tags': assigned_tags,
            'timestamp': datetime.now().isoformat(),
            'keywords': keywords
        })
        
        # Persist changes
        self.save_json("patterns.json", self.patterns)
        self.save_json("training_data.json", self.training_data)
    
    def suggest_new_tag(self, comment: str) -> Optional[str]:
        """Suggest a new tag name based on comment content"""
        keywords = self.extract_keywords(comment)
        
        # Look for action words that might indicate activity type
        action_indicators = ['submitted', 'reviewed', 'met', 'completed', 'analyzed', 
                            'collected', 'prepared', 'discussed', 'sent', 'received',
                            'approved', 'revised', 'created', 'updated']
        
        for keyword in keywords:
            for action in action_indicators:
                if action in keyword:
                    # Generate tag suggestion based on action
                    return f"{action.capitalize()} Activity"
        
        # If no clear action, use most prominent non-common words
        if keywords:
            return f"{keywords[0].title()} Related"
        
        return None


def handle_comment_tagger_page(page_name, form_data, session_id, asana_client):
    """Handle comment tagging operations"""
    try:
        operation = form_data.get('operation')
        tagger = CommentTagger()
        
        if operation == 'load_project_comments':
            # Load all tasks and comments for a project
            project_gid = form_data.get('project_gid')
            if not project_gid:
                return jsonify({'error': 'Project GID required'}), 400
            
            # Get project info
            project = asana_client.get_project(project_gid)
            
            # Get tasks with comments
            tasks = asana_client.get_project_tasks(project_gid)
            comments_to_tag = []
            
            for task in tasks:
                task_gid = task.get('gid')
                if not task_gid:
                    continue
                
                # Get task stories (comments)
                stories = asana_client.get_task_stories(task_gid)
                
                for story in stories:
                    if story.get('type') == 'comment' and story.get('text'):
                        comment_text = story.get('text', '')
                        date_extracted = tagger.extract_date_from_comment(comment_text)
                        
                        # Get tag suggestions
                        suggestions = tagger.suggest_tags(comment_text)
                        
                        comments_to_tag.append({
                            'task_gid': task_gid,
                            'task_name': task.get('name', 'Unknown Task'),
                            'story_gid': story.get('gid'),
                            'comment_text': comment_text,
                            'date_extracted': date_extracted,
                            'created_at': story.get('created_at'),
                            'created_by': story.get('created_by', {}).get('name', 'Unknown'),
                            'suggested_tags': suggestions
                        })
            
            return jsonify({
                'success': True,
                'project': {
                    'gid': project.get('gid'),
                    'name': project.get('name')
                },
                'comments': comments_to_tag,
                'total_comments': len(comments_to_tag),
                'available_tags': tagger.tag_definitions,
                'session_id': session_id
            })
        
        elif operation == 'save_tagged_comments':
            # Save user's tagging decisions and learn from them
            tagged_comments = json.loads(form_data.get('tagged_comments', '[]'))
            
            for item in tagged_comments:
                comment_text = item.get('comment_text')
                assigned_tags = item.get('assigned_tags', [])
                
                if comment_text and assigned_tags:
                    tagger.learn_from_tagging(comment_text, assigned_tags)
            
            return jsonify({
                'success': True,
                'message': f'Saved {len(tagged_comments)} tagged comments',
                'patterns_updated': True,
                'session_id': session_id
            })
        
        elif operation == 'add_new_tag':
            # Add a new tag definition
            tag_id = form_data.get('tag_id')
            tag_name = form_data.get('tag_name')
            tag_description = form_data.get('tag_description', '')
            
            if not tag_id or not tag_name:
                return jsonify({'error': 'Tag ID and name required'}), 400
            
            tagger.tag_definitions[tag_id] = {
                'name': tag_name,
                'description': tag_description,
                'created_at': datetime.now().isoformat()
            }
            
            tagger.save_json("tag_definitions.json", tagger.tag_definitions)
            
            return jsonify({
                'success': True,
                'message': f'Added new tag: {tag_name}',
                'tag_id': tag_id,
                'session_id': session_id
            })
        
        elif operation == 'get_training_stats':
            # Get statistics about training data
            stats = {
                'total_tags': len(tagger.tag_definitions),
                'total_training_samples': len(tagger.training_data),
                'tag_usage': defaultdict(int),
                'patterns_learned': {}
            }
            
            # Count tag usage
            for sample in tagger.training_data:
                for tag in sample.get('tags', []):
                    stats['tag_usage'][tag] += 1
            
            # Summarize patterns
            for tag, patterns in tagger.patterns.items():
                top_keywords = sorted(
                    patterns.get('keywords', {}).items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:5]
                stats['patterns_learned'][tag] = {
                    'top_keywords': top_keywords,
                    'total_patterns': len(patterns.get('keywords', {})) + len(patterns.get('phrases', {}))
                }
            
            return jsonify({
                'success': True,
                'stats': stats,
                'session_id': session_id
            })
        
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
    
    except Exception as e:
        logger.error(f"Error in comment tagger handler: {e}")
        return jsonify({'error': str(e)}), 500
