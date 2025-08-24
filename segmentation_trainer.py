"""
Segmentation training page handler for collecting training data
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any
from flask import jsonify
from comment_tagger import CommentSegmenter

logger = logging.getLogger(__name__)

class SegmentationTrainer:
    """Handles segmentation training data collection"""
    
    def __init__(self, base_path="/app/server_files/segmentation_trainer"):
        self.base_path = base_path
        self.ensure_directories()
        self.segmenter = CommentSegmenter()
        
        # Load training data
        self.training_data = self.load_json("segmentation_training.json", [])
        self.processed_comments = self.load_json("processed_comments.json", {})
        
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
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Saved {filename}")
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
    
    def is_comment_processed(self, story_gid: str) -> bool:
        """Check if a comment has already been processed for training"""
        return story_gid in self.processed_comments
    
    def save_training_example(self, story_gid: str, comment_text: str, 
                             original_segments: List[Dict], 
                             corrected_segments: List[Dict],
                             was_corrected: bool,
                             boundaries: List[int]):
        """Save a training example"""
        training_example = {
            'story_gid': story_gid,
            'comment_text': comment_text,
            'original_segments': original_segments,
            'corrected_segments': corrected_segments,
            'was_corrected': was_corrected,
            'boundaries': boundaries,
            'timestamp': datetime.now().isoformat()
        }
        
        # Add to training data
        self.training_data.append(training_example)
        
        # Mark as processed
        self.processed_comments[story_gid] = {
            'processed_at': datetime.now().isoformat(),
            'was_corrected': was_corrected,
            'segment_count': len(corrected_segments)
        }
        
        # Save both files
        self.save_json("segmentation_training.json", self.training_data)
        self.save_json("processed_comments.json", self.processed_comments)
        
        logger.info(f"Saved training example for {story_gid} (corrected: {was_corrected})")
    
    def get_training_stats(self) -> Dict:
        """Get statistics about training data"""
        total_samples = len(self.training_data)
        confirmed_correct = sum(1 for sample in self.training_data if not sample['was_corrected'])
        corrected = sum(1 for sample in self.training_data if sample['was_corrected'])
        
        accuracy = (confirmed_correct / total_samples * 100) if total_samples > 0 else 0
        
        # Analyze common boundary patterns
        boundary_patterns = {}
        for sample in self.training_data:
            if sample.get('boundaries'):
                pattern = f"{len(sample['boundaries'])} boundaries"
                boundary_patterns[pattern] = boundary_patterns.get(pattern, 0) + 1
        
        return {
            'total_samples': total_samples,
            'confirmed': confirmed_correct,
            'corrected': corrected,
            'accuracy': round(accuracy, 1),
            'boundary_patterns': boundary_patterns
        }
    
    def export_for_training(self) -> List[Dict]:
        """Export data in format suitable for training a model"""
        export_data = []
        
        for sample in self.training_data:
            # Create training format with text and boundary positions
            export_data.append({
                'text': sample['comment_text'],
                'boundaries': sample['boundaries'],
                'segments': sample['corrected_segments'],
                'was_auto_correct': not sample['was_corrected']
            })
        
        return export_data


def handle_segmentation_trainer_page(page_name, form_data, session_id, asana_client):
    """Handle segmentation training operations"""
    import time
    
    try:
        operation = form_data.get('operation')
        trainer = SegmentationTrainer()
        
        if operation == 'load_for_segmentation':
            start_time = time.time()
            
            # Load comments for segmentation training - LIMITED TO 50 AT A TIME
            project_gid = form_data.get('project_gid')
            if not project_gid:
                return jsonify({'error': 'Project GID required'}), 400
            
            # Get project info
            logger.info(f"Fetching project {project_gid}")
            project_start = time.time()
            project = asana_client.get_project(project_gid)
            logger.info(f"Project fetch took {time.time() - project_start:.2f}s")
            
            # Get tasks with comments
            tasks_start = time.time()
            tasks = asana_client.get_project_tasks(project_gid)
            logger.info(f"Fetched {len(tasks)} tasks in {time.time() - tasks_start:.2f}s")
            
            comments_for_training = []
            total_comments_checked = 0
            total_already_processed = 0
            
            # Limit to 50 unprocessed comments
            MAX_COMMENTS = 50
            
            stories_fetch_time = 0
            segmentation_time = 0
            
            for task_idx, task in enumerate(tasks):
                # Stop if we have enough comments
                if len(comments_for_training) >= MAX_COMMENTS:
                    logger.info(f"Reached max comments limit at task {task_idx} of {len(tasks)}")
                    break
                    
                task_gid = task.get('gid')
                if not task_gid:
                    continue
                
                # Get task stories (comments)
                try:
                    stories_start = time.time()
                    stories = asana_client.get_task_stories(task_gid)
                    stories_fetch_time += time.time() - stories_start
                    
                    if task_idx % 10 == 0:
                        logger.info(f"Processing task {task_idx}: fetched {len(stories)} stories")
                except Exception as e:
                    logger.warning(f"Error fetching stories for task {task_gid}: {e}")
                    continue
                
                for story in stories:
                    # Stop if we have enough comments
                    if len(comments_for_training) >= MAX_COMMENTS:
                        break
                        
                    if story.get('type') == 'comment' and story.get('text'):
                        story_gid = story.get('gid')
                        total_comments_checked += 1
                        
                        # Skip if already processed
                        if trainer.is_comment_processed(story_gid):
                            total_already_processed += 1
                            continue
                        
                        comment_text = story.get('text', '')
                        asana_date = story.get('created_at', '').split('T')[0] if story.get('created_at') else None
                        
                        # Get automatic segmentation
                        seg_start = time.time()
                        segments = trainer.segmenter.extract_dates_and_segments(comment_text, asana_date)
                        segmentation_time += time.time() - seg_start
                        
                        comments_for_training.append({
                            'task_gid': task_gid,
                            'task_name': task.get('name', 'Unknown Task'),
                            'story_gid': story_gid,
                            'comment_text': comment_text,
                            'segments': segments,
                            'created_at': story.get('created_at'),
                            'created_by': story.get('created_by', {}).get('name', 'Unknown')
                        })
            
            total_time = time.time() - start_time
            
            # Log timing breakdown
            logger.info(f"""
                Loading complete:
                - Total time: {total_time:.2f}s
                - Stories fetch time: {stories_fetch_time:.2f}s
                - Segmentation time: {segmentation_time:.2f}s
                - Comments loaded: {len(comments_for_training)}
                - Comments checked: {total_comments_checked}
                - Already processed: {total_already_processed}
            """)
            
            return jsonify({
                'success': True,
                'project': {
                    'gid': project.get('gid'),
                    'name': project.get('name')
                },
                'comments': comments_for_training,
                'total_unprocessed': len(comments_for_training),
                'total_processed': len(trainer.processed_comments),
                'batch_size': MAX_COMMENTS,
                'message': f"Loaded {len(comments_for_training)} comments (max {MAX_COMMENTS} per session)",
                'session_id': session_id
            })
        
        elif operation == 'save_segmentation':
            # Save segmentation training data
            comment_data = json.loads(form_data.get('comment_data', '{}'))
            
            story_gid = comment_data.get('story_gid')
            comment_text = comment_data.get('comment_text')
            original_segments = comment_data.get('original_segments', [])
            corrected_segments = comment_data.get('corrected_segments', [])
            was_corrected = comment_data.get('was_corrected', False)
            boundaries = comment_data.get('boundaries', [])
            
            if not story_gid or not comment_text:
                return jsonify({'error': 'Missing required data'}), 400
            
            # Save the training example
            trainer.save_training_example(
                story_gid=story_gid,
                comment_text=comment_text,
                original_segments=original_segments,
                corrected_segments=corrected_segments,
                was_corrected=was_corrected,
                boundaries=boundaries
            )
            
            return jsonify({
                'success': True,
                'message': 'Segmentation training data saved',
                'was_corrected': was_corrected,
                'session_id': session_id
            })
        
        elif operation == 'get_stats':
            # Get training statistics
            stats = trainer.get_training_stats()
            
            return jsonify({
                'success': True,
                'stats': stats,
                'session_id': session_id
            })
        
        elif operation == 'export_training_data':
            # Export training data for model training
            export_data = trainer.export_for_training()
            
            # Save to a file that can be downloaded
            export_path = os.path.join(trainer.base_path, 'training_export.json')
            with open(export_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            return jsonify({
                'success': True,
                'message': f'Exported {len(export_data)} training samples',
                'export_path': export_path,
                'session_id': session_id
            })
        
        elif operation == 'clear_processed':
            # Clear processed comments to allow re-training
            trainer.processed_comments = {}
            trainer.save_json("processed_comments.json", trainer.processed_comments)
            
            return jsonify({
                'success': True,
                'message': 'Cleared processed comments tracking',
                'session_id': session_id
            })
        
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
    
    except Exception as e:
        logger.error(f"Error in segmentation trainer handler: {e}")
        return jsonify({'error': str(e)}), 500
