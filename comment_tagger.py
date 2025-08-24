"""
Comment tagging page handler with SpaCy NLP for intelligent segmentation and tag suggestions
"""

import os
import json
import re
import logging
import spacy
import dateparser
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from flask import jsonify
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# Initialize SpaCy model (will be loaded once)
try:
    nlp = spacy.load("en_core_web_sm")
except:
    logger.warning("SpaCy model not found. Run: python -m spacy download en_core_web_sm")
    nlp = None

class CommentSegmenter:
    """Intelligent comment segmentation using SpaCy and dateparser"""
    
    def __init__(self):
        self.nlp = nlp
        # Load segmentation training data if available
        self.load_training_data()
        
    def load_training_data(self):
        """Load segmentation training data to improve accuracy"""
        try:
            training_path = "/app/server_files/segmentation_trainer/segmentation_training.json"
            if os.path.exists(training_path):
                with open(training_path, 'r') as f:
                    self.training_data = json.load(f)
                logger.info(f"Loaded {len(self.training_data)} segmentation training examples")
            else:
                self.training_data = []
        except Exception as e:
            logger.warning(f"Could not load segmentation training data: {e}")
            self.training_data = []
    
    def extract_dates_and_segments(self, text: str, asana_date: str = None) -> List[Dict]:
        """
        Extract dates and create intelligent segments using NLP
        
        New algorithm:
        1. Split at colons, sentence boundaries, and newlines
        2. Check each segment for dates or time references
        3. Merge segments without dates/time refs with previous segment
        4. Continue until all segments have dates or only one segment remains
        """
        logger.info(f"Starting segmentation for text of length {len(text)}")
        
        if not self.nlp:
            logger.warning("SpaCy not available, using fallback segmentation")
            return self.simple_fallback_segmentation(text, asana_date)
        
        # Parse text with SpaCy
        doc = self.nlp(text)
        
        # Step 1: Create initial segments at boundaries
        initial_segments = self.create_initial_segments(doc, text)
        logger.info(f"Created {len(initial_segments)} initial segments")
        
        # Step 2: Merge segments without dates/time references
        final_segments = self.merge_segments_without_dates(initial_segments, doc, asana_date)
        logger.info(f"Final segmentation: {len(final_segments)} segments")
        
        return final_segments
    
    def create_initial_segments(self, doc, text: str) -> List[Dict]:
        """
        Create initial segments at:
        - Colons followed by space (": ")
        - Sentence boundaries
        - Newlines
        """
        segments = []
        boundaries = set()
        
        # Find colon boundaries
        colon_pattern = re.compile(r':\s')
        for match in colon_pattern.finditer(text):
            boundaries.add(match.end())
        
        # Find sentence boundaries using SpaCy
        for sent in doc.sents:
            if sent.end_char < len(text):
                boundaries.add(sent.end_char)
        
        # Find newline boundaries
        for i, char in enumerate(text):
            if char == '\n':
                boundaries.add(i + 1)
        
        # Sort boundaries
        sorted_boundaries = sorted(list(boundaries))
        logger.debug(f"Found {len(sorted_boundaries)} boundary positions")
        
        # Create segments
        last_pos = 0
        for boundary in sorted_boundaries:
            if boundary > last_pos:
                segment_text = text[last_pos:boundary].strip()
                if segment_text:  # Only add non-empty segments
                    segments.append({
                        'text': segment_text,
                        'startIndex': last_pos,
                        'endIndex': boundary,
                        'has_date_or_time': False  # Will be checked next
                    })
                last_pos = boundary
        
        # Add final segment
        if last_pos < len(text):
            segment_text = text[last_pos:].strip()
            if segment_text:
                segments.append({
                    'text': segment_text,
                    'startIndex': last_pos,
                    'endIndex': len(text),
                    'has_date_or_time': False
                })
        
        # If no segments created, treat entire text as one segment
        if not segments:
            segments.append({
                'text': text,
                'startIndex': 0,
                'endIndex': len(text),
                'has_date_or_time': False
            })
        
        return segments
    
    def has_date_or_time_reference(self, segment_text: str, asana_date: str = None) -> bool:
        """
        Check if segment contains:
        - An explicit date (equal to or before asana_date)
        - Time references to present/past (today, yesterday, X days/weeks ago, etc.)
        """
        # Quick length check - very short segments unlikely to have dates
        if len(segment_text) < 3:
            return False
            
        segment_lower = segment_text.lower()
        
        # Check for past/present time references
        time_patterns = [
            r'\btoday\b',
            r'\byesterday\b',
            r'\b\d+\s*(day|week|month|year)s?\s*ago\b',
            r'\blast\s*(week|month|year)\b',
            r'\bthis\s*(morning|afternoon|evening)\b',
            r'\bearlier\b',
            r'\bpreviously\b',
            r'\bbefore\b',
            r'\balready\b',
        ]
        
        for pattern in time_patterns:
            if re.search(pattern, segment_lower):
                logger.debug(f"Found time pattern '{pattern}' in segment")
                return True
        
        # Check for explicit dates using dateparser
        # Look for common date patterns
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{2,4}',  # MM/DD/YYYY or MM/DD/YY
            r'\d{1,2}-\d{1,2}-\d{2,4}',   # MM-DD-YYYY
            r'\d{4}-\d{1,2}-\d{1,2}',     # YYYY-MM-DD
            r'\d{1,2}\.\d{1,2}\.\d{2,4}', # MM.DD.YYYY
            r'\d{1,2}/\d{1,2}',           # MM/DD (no year)
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}',  # Month DD
            r'\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',  # DD Month
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, segment_lower, re.IGNORECASE):
                # Found a date pattern - check if it's in the past
                match = re.search(pattern, segment_text, re.IGNORECASE)
                if match:
                    date_str = match.group()
                    try:
                        parsed_date = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'past'})
                        if parsed_date:
                            # Check if date is in the past or same as asana_date
                            if asana_date:
                                asana_datetime = dateparser.parse(asana_date)
                                if asana_datetime and parsed_date <= asana_datetime:
                                    logger.debug(f"Found valid past date: {date_str}")
                                    return True
                            else:
                                # No asana date, check if before today
                                if parsed_date <= datetime.now():
                                    logger.debug(f"Found valid past date: {date_str}")
                                    return True
                    except Exception as e:
                        logger.debug(f"Failed to parse date '{date_str}': {e}")
        
        # Use SpaCy to find DATE entities (only if we have SpaCy)
        if self.nlp:
            try:
                doc = self.nlp(segment_text[:1000])  # Limit text length for SpaCy
                for ent in doc.ents:
                    if ent.label_ in ['DATE', 'TIME']:
                        # Check if it refers to past/present
                        ent_lower = ent.text.lower()
                        if any(word in ent_lower for word in ['today', 'yesterday', 'ago', 'last', 'earlier']):
                            logger.debug(f"SpaCy found time entity: {ent.text}")
                            return True
                        # Try to parse the date
                        try:
                            parsed_date = dateparser.parse(ent.text, settings={'PREFER_DATES_FROM': 'past'})
                            if parsed_date:
                                if asana_date:
                                    asana_datetime = dateparser.parse(asana_date)
                                    if asana_datetime and parsed_date <= asana_datetime:
                                        logger.debug(f"SpaCy found valid past date: {ent.text}")
                                        return True
                                elif parsed_date <= datetime.now():
                                    logger.debug(f"SpaCy found valid past date: {ent.text}")
                                    return True
                        except:
                            pass
            except Exception as e:
                logger.warning(f"SpaCy processing failed: {e}")
        
        return False
    
    def merge_segments_without_dates(self, segments: List[Dict], doc, asana_date: str) -> List[Dict]:
        """
        Merge segments that don't contain dates/time references with the previous segment.
        Continue until all segments have dates or only one segment remains.
        """
        logger.info(f"Starting merge process with {len(segments)} segments")
        
        # First, mark which segments have dates/time references
        for i, segment in enumerate(segments):
            has_date = self.has_date_or_time_reference(segment['text'], asana_date)
            segment['has_date_or_time'] = has_date
            logger.debug(f"Segment {i}: has_date={has_date}, text_preview='{segment['text'][:50]}...'")
        
        # Keep merging until all segments have dates or we have only one segment
        max_iterations = 100  # Safety limit to prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Check if we're done
            segments_without_dates = [s for s in segments if not s['has_date_or_time']]
            logger.debug(f"Iteration {iteration}: {len(segments)} segments, {len(segments_without_dates)} without dates")
            
            if len(segments_without_dates) == 0 or len(segments) == 1:
                logger.info(f"Merge complete after {iteration} iterations")
                break
            
            # Find first segment without date/time and merge with previous
            merged_any = False
            new_segments = []
            i = 0
            
            while i < len(segments):
                if i > 0 and not segments[i]['has_date_or_time']:
                    # Merge with previous segment
                    prev_segment = new_segments[-1]
                    merged_text = prev_segment['text'] + ' ' + segments[i]['text']
                    prev_segment['text'] = merged_text
                    prev_segment['endIndex'] = segments[i]['endIndex']
                    # Re-check if merged segment now has date/time
                    prev_segment['has_date_or_time'] = self.has_date_or_time_reference(merged_text, asana_date)
                    logger.debug(f"Merged segment {i} with previous, new has_date={prev_segment['has_date_or_time']}")
                    merged_any = True
                else:
                    new_segments.append(segments[i].copy())
                i += 1
            
            segments = new_segments
            
            # Check if we made any progress
            if not merged_any:
                logger.warning("No segments were merged in this iteration - breaking to prevent infinite loop")
                break
        
        if iteration >= max_iterations:
            logger.error(f"Reached maximum iterations ({max_iterations}) - stopping merge to prevent infinite loop")
        
        # Format final segments for output
        final_segments = []
        for i, segment in enumerate(segments):
            # Determine date for segment
            segment_date = self.extract_segment_date(segment['text'], asana_date)
            
            final_segments.append({
                'text': segment['text'],
                'date': segment_date,
                'dateSource': 'extracted' if segment['has_date_or_time'] else 'asana_timestamp',
                'startIndex': segment['startIndex'],
                'endIndex': segment['endIndex']
            })
        
        return final_segments
    
    def extract_segment_date(self, segment_text: str, asana_date: str) -> str:
        """
        Extract the most relevant date from a segment.
        Returns YYYY-MM-DD format.
        """
        # Try to find and parse dates in the segment
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{2,4}',
            r'\d{1,2}-\d{1,2}-\d{2,4}',
            r'\d{4}-\d{1,2}-\d{1,2}',
            r'\d{1,2}\.\d{1,2}\.\d{2,4}',
            r'\d{1,2}/\d{1,2}',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, segment_text)
            if match:
                try:
                    parsed_date = dateparser.parse(match.group(), settings={'PREFER_DATES_FROM': 'past'})
                    if parsed_date:
                        return parsed_date.strftime('%Y-%m-%d')
                except:
                    pass
        
        # Check for relative dates
        if 'today' in segment_text.lower():
            return datetime.now().strftime('%Y-%m-%d')
        elif 'yesterday' in segment_text.lower():
            return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Default to asana date or today
        return asana_date or datetime.now().strftime('%Y-%m-%d')
    
    def simple_fallback_segmentation(self, text: str, asana_date: str) -> List[Dict]:
        """
        Simple fallback if SpaCy is not available
        """
        logger.info("Using simple fallback segmentation")
        return [{
            'text': text,
            'date': asana_date or datetime.now().strftime('%Y-%m-%d'),
            'dateSource': 'asana_timestamp' if asana_date else 'default',
            'startIndex': 0,
            'endIndex': len(text)
        }]


class TagSuggester:
    """Intelligent tag suggestion using NLP and similarity matching"""
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
        self.segment_vectors = None
        self.segment_tags = []
        self.trained_segments = []
        
    def train_on_tagged_segments(self, tagged_segments: List[Dict]):
        """
        Train the suggester on previously tagged segments
        Format: [{'text': 'segment text', 'tags': ['tag1', 'tag2']}, ...]
        """
        if not tagged_segments:
            return
            
        self.trained_segments = tagged_segments
        self.segment_tags = [seg['tags'] for seg in tagged_segments]
        
        # Extract text from segments
        texts = [seg['text'] for seg in tagged_segments]
        
        # Fit vectorizer and transform texts
        try:
            self.segment_vectors = self.vectorizer.fit_transform(texts)
            logger.info(f"Trained tag suggester on {len(tagged_segments)} segments")
        except Exception as e:
            logger.error(f"Error training tag suggester: {e}")
    
    def suggest_tags(self, segment_text: str, top_k: int = 5) -> List[Dict]:
        """
        Suggest tags for a segment based on similarity to previously tagged segments
        Returns list of {'tag': tag_name, 'confidence': score}
        """
        if self.segment_vectors is None or len(self.trained_segments) == 0:
            return []
        
        try:
            # Transform new segment
            segment_vector = self.vectorizer.transform([segment_text])
            
            # Calculate similarities
            similarities = cosine_similarity(segment_vector, self.segment_vectors)[0]
            
            # Get top similar segments
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            # Aggregate tags from similar segments with confidence scores
            tag_scores = defaultdict(float)
            for idx in top_indices:
                similarity = similarities[idx]
                if similarity > 0.1:  # Minimum similarity threshold
                    for tag in self.segment_tags[idx]:
                        tag_scores[tag] += similarity
            
            # Normalize scores and create suggestions
            if tag_scores:
                max_score = max(tag_scores.values())
                suggestions = [
                    {
                        'tag': tag,
                        'confidence': score / max_score,  # Normalize to 0-1
                        'auto_select': (score / max_score) > 0.7
                    }
                    for tag, score in sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
                ]
                return suggestions[:top_k]
            
        except Exception as e:
            logger.error(f"Error suggesting tags: {e}")
        
        return []


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
            if 'comment' in sample and 'tags' in sample:
                tagged_segments.append({
                    'text': sample['comment'],
                    'tags': sample['tags']
                })
        
        # Also extract from tagged comments if they have segments
        for story_gid, comment_data in self.tagged_comments.items():
            if 'segments' in comment_data:
                for segment in comment_data['segments']:
                    if 'text' in segment and 'tags' in segment:
                        tagged_segments.append({
                            'text': segment['text'],
                            'tags': segment['tags']
                        })
        
        if tagged_segments:
            self.tag_suggester.train_on_tagged_segments(tagged_segments)
            logger.info(f"Trained tag suggester on {len(tagged_segments)} segments")
    
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
                        story_gid = story.get('gid')
                        
                        # Skip if already tagged
                        if tagger.is_comment_tagged(story_gid):
                            continue
                        
                        comment_text = story.get('text', '')
                        asana_date = story.get('created_at', '').split('T')[0] if story.get('created_at') else None
                        
                        # Use intelligent segmentation
                        segments = tagger.segment_comment(comment_text, asana_date)
                        
                        # Get tag suggestions for the first segment
                        if segments:
                            suggestions = tagger.suggest_tags_for_segment(segments[0]['text'])
                        else:
                            suggestions = []
                        
                        comments_to_tag.append({
                            'task_gid': task_gid,
                            'task_name': task.get('name', 'Unknown Task'),
                            'story_gid': story_gid,
                            'comment_text': comment_text,
                            'segments': segments,
                            'created_at': story.get('created_at'),
                            'created_by': story.get('created_by', {}).get('name', 'Unknown'),
                            'suggested_tags': suggestions
                        })
            
            # Count already tagged comments for stats
            total_in_project = len(comments_to_tag) + len([
                gid for gid in tagger.tagged_comments 
                if any(gid in str(story.get('gid', '')) for task in tasks 
                      for story in asana_client.get_task_stories(task.get('gid')))
            ])
            
            return jsonify({
                'success': True,
                'project': {
                    'gid': project.get('gid'),
                    'name': project.get('name')
                },
                'comments': comments_to_tag,
                'total_untagged': len(comments_to_tag),
                'total_already_tagged': total_in_project - len(comments_to_tag),
                'available_tags': tagger.tag_definitions,
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
                stats['model_accuracy'] = (correct / total) * 100
            
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
