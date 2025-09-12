"""
Comment tagging page handler - main orchestration module
Coordinates segmentation, date extraction, and tag suggestion
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any
from flask import jsonify
from collections import defaultdict

# Import modular components
from comment_segmenter import CommentSegmenter
from tag_suggester import TagSuggester

logger = logging.getLogger(__name__)


class CommentTagger:
    """Handles comment tagging operations and pattern learning"""
    
    def __init__(self, base_path="/app/server_files/comment_tagger"):
        self.base_path = base_path
        self.ensure_directories()
        self.segmenter = CommentSegmenter()
        self.tag_suggester = TagSuggester()
        
        # Load or initialize data structures
        self.tag_definitions = self.load_json("tag_definitions.json", {})
        self.training_data = self.load_json("training_data.json", [])
        self.patterns = self.load_json("patterns.json", {})
        self.model_cache = self.load_json("model_cache.json", {})
        self.tagged_comments = self.load_json("tagged_comments.json", {})
        self.segmentation_training = self.load_json("segmentation_training.json", [])
        
        # Train the tag suggester on existing data
        self.train_tag_suggester()
        
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
    
    def train_tag_suggester(self):
        """Train the tag suggester on existing tagged segments"""
        tagged_segments = []
        
        # Extract segments from training data
        for sample in self.training_data:
            if 'comment' in sample and 'tags' in sample and sample['tags']:
                tagged_segments.append({
                    'text': sample['comment'],
                    'tags': sample['tags']
                })
        
        # Also extract from tagged comments if they have segments
        for story_gid, comment_data in self.tagged_comments.items():
            if 'segments' in comment_data:
                for segment in comment_data['segments']:
                    if 'text' in segment and 'tags' in segment and segment['tags']:
                        tagged_segments.append({
                            'text': segment['text'],
                            'tags': segment['tags']
                        })
        
        if tagged_segments:
            self.tag_suggester.train_on_tagged_segments(tagged_segments)
            logger.info(f"Trained tag suggester on {len(tagged_segments)} segments with tags")
        else:
            logger.warning("No tagged segments found for training")
    
    def segment_comment(self, comment_text: str, asana_date: str = None) -> List[Dict]:
        """
        Use NLP to intelligently segment the comment
        """
        return self.segmenter.extract_dates_and_segments(comment_text, asana_date)
    
    def save_segmentation_training(self, comment_text: str, user_segments: List[Dict]):
        """
        Save user-corrected segmentation for training
        """
        training_example = {
            'comment_text': comment_text,
            'user_segments': user_segments,
            'timestamp': datetime.now().isoformat()
        }
        self.segmentation_training.append(training_example)
        self.save_json("segmentation_training.json", self.segmentation_training)
    
    def suggest_tags_for_segment(self, segment_text: str) -> List[Dict]:
        """
        Get tag suggestions for a segment using the trained model
        """
        suggestions = self.tag_suggester.suggest_tags(segment_text)
        
        # Add tag names from definitions
        for suggestion in suggestions:
            tag_id = suggestion['tag']
            if tag_id in self.tag_definitions:
                suggestion['tag_name'] = self.tag_definitions[tag_id].get('name', tag_id)
            else:
                suggestion['tag_name'] = tag_id
            suggestion['tag_id'] = tag_id
        
        return suggestions
    
    def learn_from_tagging(self, segment_text: str, assigned_tags: List[str]):
        """Update patterns and retrain based on user's tagging decision"""
        # Add to training data
        self.training_data.append({
            'comment': segment_text,
            'tags': assigned_tags,
            'timestamp': datetime.now().isoformat()
        })
        
        # Persist changes
        self.save_json("training_data.json", self.training_data)
        
        # Retrain the suggester with new data
        self.train_tag_suggester()
    
    def is_comment_tagged(self, story_gid: str) -> bool:
        """Check if a comment has already been tagged"""
        return story_gid in self.tagged_comments
    
    def get_comment_tags(self, story_gid: str) -> List[str]:
        """Get tags for a specific comment"""
        return self.tagged_comments.get(story_gid, {}).get('tags', [])


def handle_comment_tagger_page(page_name, form_data, session_id, asana_client):
    """Handle comment tagging operations"""
    try:
        operation = form_data.get('operation')
        tagger = CommentTagger()
        
        if operation == 'segment_comment':
            # Segment a single comment using SpaCy
            comment_text = form_data.get('comment_text')
            asana_date = form_data.get('asana_date')
            
            if not comment_text:
                return jsonify({'error': 'Comment text required'}), 400
            
            # Use intelligent segmentation
            segments = tagger.segment_comment(comment_text, asana_date)
            
            # Get tag suggestions for each segment
            for segment in segments:
                segment['suggested_tags'] = tagger.suggest_tags_for_segment(segment['text'])
            
            return jsonify({
                'success': True,
                'segments': segments,
                'session_id': session_id
            })
        
        elif operation == 'load_project_comments':
            # Load all tasks and comments for a project
            project_gid = form_data.get('project_gid')
            if not project_gid:
                return jsonify({'error': 'Project GID required'}), 400
            
            # Get project info
            project = asana_client.get_project(project_gid)
            
            # Get tasks with comments - LIMIT TO PREVENT TIMEOUT
            tasks = asana_client.get_project_tasks(project_gid)
            comments_to_tag = []
            
            MAX_COMMENTS = 50  # Limit to prevent timeout
            comment_count = 0
            
            for task in tasks:
                if comment_count >= MAX_COMMENTS:
                    logger.info(f"Reached max comments limit ({MAX_COMMENTS})")
                    break
                    
                task_gid = task.get('gid')
                if not task_gid:
                    continue
                
                # Get task stories (comments)
                try:
                    stories = asana_client.get_task_stories(task_gid)
                except Exception as e:
                    logger.warning(f"Error fetching stories for task {task_gid}: {e}")
                    continue
                
                for story in stories:
                    if comment_count >= MAX_COMMENTS:
                        break
                        
                    if story.get('type') == 'comment' and story.get('text'):
                        story_gid = story.get('gid')
                        
                        # Skip if already tagged
                        if tagger.is_comment_tagged(story_gid):
                            continue
                        
                        comment_text = story.get('text', '')
                        asana_date = story.get('created_at', '').split('T')[0] if story.get('created_at') else None
                        
                        # Use intelligent segmentation
                        segments = tagger.segment_comment(comment_text, asana_date)
                        
                        # Get tag suggestions for each segment
                        for segment in segments:
                            suggestions = tagger.suggest_tags_for_segment(segment['text'])
                            segment['suggested_tags'] = suggestions
                            logger.info(f"Segment suggestions: {len(suggestions)} tags suggested")
                        
                        # Also get suggestions for the whole comment (backwards compatibility)
                        overall_suggestions = tagger.suggest_tags_for_segment(comment_text)
                        logger.info(f"Overall suggestions for comment: {len(overall_suggestions)} tags")
                        
                        comments_to_tag.append({
                            'task_gid': task_gid,
                            'task_name': task.get('name', 'Unknown Task'),
                            'story_gid': story_gid,
                            'comment_text': comment_text,
                            'segments': segments,
                            'created_at': story.get('created_at'),
                            'created_by': story.get('created_by', {}).get('name', 'Unknown'),
                            'suggested_tags': overall_suggestions  # Keep for backwards compatibility
                        })
                        
                        comment_count += 1
            
            # Count already tagged comments for stats (simplified)
            total_already_tagged = len([gid for gid in tagger.tagged_comments])
            
            logger.info(f"Loaded {len(comments_to_tag)} untagged comments (max {MAX_COMMENTS})")
            
            return jsonify({
                'success': True,
                'project': {
                    'gid': project.get('gid'),
                    'name': project.get('name')
                },
                'comments': comments_to_tag,
                'total_untagged': len(comments_to_tag),
                'total_already_tagged': total_already_tagged,
                'available_tags': tagger.tag_definitions,
                'max_comments': MAX_COMMENTS,
                'session_id': session_id
            })
        
        elif operation == 'save_tagged_comment':
            # Save a single tagged comment and learn from it
            comment_data = json.loads(form_data.get('comment_data', '{}'))
            
            story_gid = comment_data.get('story_gid')
            comment_text = comment_data.get('comment_text')
            segments = comment_data.get('segments', [])
            
            if not story_gid or not comment_text:
                return jsonify({'error': 'Missing required data'}), 400
            
            # Save segmentation training data if user modified segments
            if segments:
                tagger.save_segmentation_training(comment_text, segments)
            
            # Learn from each tagged segment
            all_tags = []
            for segment in segments:
                if 'tags' in segment and segment['tags']:
                    tagger.learn_from_tagging(segment['text'], segment['tags'])
                    all_tags.extend(segment['tags'])
            
            if all_tags:  # Only save if tags were assigned
                # Mark comment as tagged
                tagger.tagged_comments[story_gid] = {
                    'tags': list(set(all_tags)),  # Unique tags across all segments
                    'segments': segments,
                    'tagged_at': datetime.now().isoformat(),
                    'comment_text': comment_text[:100]  # Store preview for reference
                }
                
                # Save the tagged comments registry
                tagger.save_json("tagged_comments.json", tagger.tagged_comments)
            
            return jsonify({
                'success': True,
                'message': 'Comment tagged successfully',
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
                'total_segmentation_samples': len(tagger.segmentation_training),
                'tag_usage': defaultdict(int),
                'model_accuracy': 0.0
            }
            
            # Count tag usage
            for sample in tagger.training_data:
                for tag in sample.get('tags', []):
                    stats['tag_usage'][tag] += 1
            
            # Calculate model accuracy if we have enough data
            if len(tagger.training_data) > 10:
                # Simple accuracy based on how often top suggestion matches actual tags
                correct = 0
                total = min(20, len(tagger.training_data))  # Sample last 20
                for sample in tagger.training_data[-total:]:
                    suggestions = tagger.suggest_tags_for_segment(sample['comment'])
                    if suggestions and suggestions[0]['tag'] in sample['tags']:
                        correct += 1
                stats['model_accuracy'] = float((correct / total) * 100)  # Convert to native Python float
            
            # Convert all NumPy types to native Python types for JSON serialization
            stats['tag_usage'] = dict(stats['tag_usage'])  # Ensure it's a regular dict
            
            return jsonify({
                'success': True,
                'stats': stats,
                'session_id': session_id
            })
        
        elif operation == 'get_progress_stats':
            # Get comprehensive progress statistics
            project_gid = form_data.get('project_gid')
            
            # Load all relevant data files
            tagged_comments = tagger.tagged_comments
            segmentation_training = tagger.segmentation_training
            training_data = tagger.training_data
            
            # Also load segmentation trainer data if available
            seg_trainer_path = "/app/server_files/segmentation_trainer"
            seg_processed_comments = {}
            seg_training_data = []
            
            try:
                seg_processed_path = os.path.join(seg_trainer_path, "processed_comments.json")
                if os.path.exists(seg_processed_path):
                    with open(seg_processed_path, 'r') as f:
                        seg_processed_comments = json.load(f)
                
                seg_training_path = os.path.join(seg_trainer_path, "segmentation_training.json")
                if os.path.exists(seg_training_path):
                    with open(seg_training_path, 'r') as f:
                        seg_training_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load segmentation trainer data: {e}")
            
            # Calculate statistics
            stats = {
                'total_comments_in_project': 0,  # Would need project access to get true total
                'comments_tagged': len(tagged_comments),
                'comments_segmentation_reviewed': len(seg_processed_comments),
                'comments_segmentation_confirmed': 0,
                'comments_segmentation_corrected': 0,
                'segmentation_accuracy': 0.0,
                'total_segments_tagged': 0,
                'total_tags_applied': 0,
                'unique_tags_used': set(),
                'comments_with_auto_tags': 0,
                'segments_by_count': defaultdict(int),  # Distribution of segment counts
                'tag_frequency': defaultdict(int),
                'timeline': {
                    'earliest_activity': None,
                    'latest_activity': None,
                    'daily_activity': defaultdict(int)
                }
            }
            
            # Process segmentation training data
            for sample in seg_training_data:
                if not sample.get('was_corrected', True):
                    stats['comments_segmentation_confirmed'] += 1
                else:
                    stats['comments_segmentation_corrected'] += 1
                
                # Track segment counts
                if 'corrected_segments' in sample:
                    segment_count = len(sample['corrected_segments'])
                    stats['segments_by_count'][segment_count] += 1
                
                # Track timeline
                if 'timestamp' in sample:
                    try:
                        timestamp = datetime.fromisoformat(sample['timestamp'].replace('Z', '+00:00'))
                        date_key = timestamp.strftime('%Y-%m-%d')
                        stats['timeline']['daily_activity'][date_key] += 1
                        
                        if stats['timeline']['earliest_activity'] is None or timestamp < datetime.fromisoformat(stats['timeline']['earliest_activity']):
                            stats['timeline']['earliest_activity'] = sample['timestamp']
                        if stats['timeline']['latest_activity'] is None or timestamp > datetime.fromisoformat(stats['timeline']['latest_activity']):
                            stats['timeline']['latest_activity'] = sample['timestamp']
                    except:
                        pass
            
            # Calculate segmentation accuracy
            total_reviewed = stats['comments_segmentation_confirmed'] + stats['comments_segmentation_corrected']
            if total_reviewed > 0:
                stats['segmentation_accuracy'] = (stats['comments_segmentation_confirmed'] / total_reviewed) * 100
            
            # Process tagged comments
            for story_gid, comment_data in tagged_comments.items():
                # Count segments and tags
                if 'segments' in comment_data:
                    stats['total_segments_tagged'] += len(comment_data['segments'])
                    
                    for segment in comment_data['segments']:
                        if 'tags' in segment and segment['tags']:
                            stats['total_tags_applied'] += len(segment['tags'])
                            for tag in segment['tags']:
                                stats['unique_tags_used'].add(tag)
                                stats['tag_frequency'][tag] += 1
                
                # Check if any segments had auto-selected tags
                if 'segments' in comment_data:
                    has_auto = any(
                        any(sugg.get('auto_select', False) for sugg in seg.get('suggested_tags', []))
                        for seg in comment_data['segments']
                    )
                    if has_auto:
                        stats['comments_with_auto_tags'] += 1
            
            # Convert sets to lists for JSON serialization
            stats['unique_tags_used'] = list(stats['unique_tags_used'])
            stats['unique_tags_count'] = len(stats['unique_tags_used'])
            
            # Convert defaultdicts to regular dicts
            stats['segments_by_count'] = dict(stats['segments_by_count'])
            stats['tag_frequency'] = dict(stats['tag_frequency'])
            stats['timeline']['daily_activity'] = dict(stats['timeline']['daily_activity'])
            
            # Calculate auto-tagging accuracy (approximate)
            if stats['comments_tagged'] > 0:
                stats['auto_tagging_rate'] = (stats['comments_with_auto_tags'] / stats['comments_tagged']) * 100
            else:
                stats['auto_tagging_rate'] = 0.0
            
            # Get project-specific stats if project_gid provided
            if project_gid and asana_client and asana_client.is_connected():
                try:
                    # Get total tasks in project
                    tasks = asana_client.get_project_tasks(project_gid)
                    total_comments_estimate = 0
                    
                    # This is an estimate - we'd need to fetch all stories to get exact count
                    # For now, estimate based on task count
                    stats['total_tasks_in_project'] = len(tasks)
                    stats['estimated_total_comments'] = len(tasks) * 3  # Rough estimate
                    
                    # Calculate completion percentage
                    if stats['estimated_total_comments'] > 0:
                        stats['tagging_completion_rate'] = (stats['comments_tagged'] / stats['estimated_total_comments']) * 100
                        stats['segmentation_review_rate'] = (stats['comments_segmentation_reviewed'] / stats['estimated_total_comments']) * 100
                    else:
                        stats['tagging_completion_rate'] = 0.0
                        stats['segmentation_review_rate'] = 0.0
                        
                except Exception as e:
                    logger.warning(f"Could not fetch project stats: {e}")
                    stats['project_error'] = str(e)
            
            # Add summary metrics
            stats['summary'] = {
                'total_processed': stats['comments_tagged'] + stats['comments_segmentation_reviewed'],
                'segmentation_quality': f"{stats['segmentation_accuracy']:.1f}%",
                'average_segments_per_comment': stats['total_segments_tagged'] / stats['comments_tagged'] if stats['comments_tagged'] > 0 else 0,
                'average_tags_per_segment': stats['total_tags_applied'] / stats['total_segments_tagged'] if stats['total_segments_tagged'] > 0 else 0,
                'most_used_tags': sorted(stats['tag_frequency'].items(), key=lambda x: x[1], reverse=True)[:10]
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
