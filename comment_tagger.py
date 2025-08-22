"""
Comment tagging page handler with SpaCy NLP for intelligent segmentation
"""

import os
import json
import re
import logging
import spacy
import dateparser
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from flask import jsonify
from collections import defaultdict

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
        
    def extract_dates_and_segments(self, text: str, asana_date: str = None) -> List[Dict]:
        """
        Extract dates and create intelligent segments using NLP
        """
        if not self.nlp:
            # Fallback to simple segmentation if SpaCy not available
            return self.simple_fallback_segmentation(text, asana_date)
        
        # Parse text with SpaCy
        doc = self.nlp(text)
        
        # Extract all potential dates using dateparser
        date_results = dateparser.search.search_dates(text, 
                                                       languages=['en'],
                                                       settings={'PREFER_DATES_FROM': 'past'})
        
        if not date_results:
            # No dates found - return entire text as one segment
            return [{
                'text': text,
                'date': asana_date or datetime.now().strftime('%Y-%m-%d'),
                'dateSource': 'asana_timestamp' if asana_date else 'default',
                'startIndex': 0,
                'endIndex': len(text)
            }]
        
        # Analyze sentence structure to determine segmentation
        segments = self.create_intelligent_segments(doc, date_results, text, asana_date)
        
        return segments
    
    def create_intelligent_segments(self, doc, date_results, original_text, asana_date):
        """
        Create segments based on sentence structure and date positions
        """
        segments = []
        sentences = list(doc.sents)
        
        # Map dates to their sentence indices
        date_sentence_map = []
        for date_str, date_obj in date_results:
            date_pos = original_text.find(date_str)
            if date_pos == -1:
                continue
                
            # Find which sentence contains this date
            for sent_idx, sent in enumerate(sentences):
                if sent.start_char <= date_pos < sent.end_char:
                    date_sentence_map.append({
                        'date_str': date_str,
                        'date_obj': date_obj,
                        'position': date_pos,
                        'sentence_idx': sent_idx,
                        'sentence': sent
                    })
                    break
        
        # Determine segmentation strategy
        if len(date_sentence_map) == 1:
            # Single date - check if it's a divider or embedded
            date_info = date_sentence_map[0]
            date_pos_in_sent = date_info['position'] - date_info['sentence'].start_char
            sent_text = date_info['sentence'].text
            
            # Check if date is at the beginning of a sentence (likely a divider)
            if date_pos_in_sent < 15 and date_info['sentence_idx'] > 0:
                # Date starts a new section
                # Segment 1: Everything before this sentence
                seg1_text = original_text[:date_info['sentence'].start_char].strip()
                if seg1_text:
                    segments.append({
                        'text': seg1_text,
                        'date': asana_date or datetime.now().strftime('%Y-%m-%d'),
                        'dateSource': 'asana_timestamp',
                        'startIndex': 0,
                        'endIndex': date_info['sentence'].start_char
                    })
                
                # Segment 2: From this sentence onward
                seg2_text = original_text[date_info['sentence'].start_char:].strip()
                segments.append({
                    'text': seg2_text,
                    'date': date_info['date_obj'].strftime('%Y-%m-%d'),
                    'dateSource': 'extracted',
                    'startIndex': date_info['sentence'].start_char,
                    'endIndex': len(original_text)
                })
            else:
                # Date is embedded - treat entire text as one segment
                segments.append({
                    'text': original_text,
                    'date': date_info['date_obj'].strftime('%Y-%m-%d'),
                    'dateSource': 'extracted',
                    'startIndex': 0,
                    'endIndex': len(original_text)
                })
        
        elif len(date_sentence_map) > 1:
            # Multiple dates - check for pattern
            segments = self.segment_by_date_patterns(date_sentence_map, sentences, original_text, asana_date)
        
        else:
            # No valid dates found after parsing
            segments.append({
                'text': original_text,
                'date': asana_date or datetime.now().strftime('%Y-%m-%d'),
                'dateSource': 'asana_timestamp',
                'startIndex': 0,
                'endIndex': len(original_text)
            })
        
        return segments
    
    def segment_by_date_patterns(self, date_map, sentences, text, asana_date):
        """
        Handle multiple dates - look for patterns like date-prefixed entries
        """
        segments = []
        
        # Check if dates appear to be section headers (at sentence starts)
        section_dates = []
        for date_info in date_map:
            date_pos_in_sent = date_info['position'] - date_info['sentence'].start_char
            # Is this date at or near the start of its sentence?
            if date_pos_in_sent < 15:
                section_dates.append(date_info)
        
        if not section_dates:
            # All dates are embedded - treat as single segment with first date
            segments.append({
                'text': text,
                'date': date_map[0]['date_obj'].strftime('%Y-%m-%d'),
                'dateSource': 'extracted',
                'startIndex': 0,
                'endIndex': len(text)
            })
        else:
            # Create segments based on section dates
            for i, date_info in enumerate(section_dates):
                start_pos = date_info['sentence'].start_char
                
                # Find end position (start of next section or end of text)
                if i + 1 < len(section_dates):
                    end_pos = section_dates[i + 1]['sentence'].start_char
                else:
                    end_pos = len(text)
                
                segment_text = text[start_pos:end_pos].strip()
                if segment_text:
                    segments.append({
                        'text': segment_text,
                        'date': date_info['date_obj'].strftime('%Y-%m-%d'),
                        'dateSource': 'extracted',
                        'startIndex': start_pos,
                        'endIndex': end_pos
                    })
            
            # Check for text before first section
            if section_dates and section_dates[0]['sentence'].start_char > 20:
                prefix_text = text[:section_dates[0]['sentence'].start_char].strip()
                if prefix_text:
                    segments.insert(0, {
                        'text': prefix_text,
                        'date': asana_date or datetime.now().strftime('%Y-%m-%d'),
                        'dateSource': 'asana_timestamp',
                        'startIndex': 0,
                        'endIndex': section_dates[0]['sentence'].start_char
                    })
        
        return segments
    
    def simple_fallback_segmentation(self, text: str, asana_date: str) -> List[Dict]:
        """
        Simple fallback if SpaCy is not available
        """
        # Just return the whole text as one segment
        return [{
            'text': text,
            'date': asana_date or datetime.now().strftime('%Y-%m-%d'),
            'dateSource': 'asana_timestamp' if asana_date else 'default',
            'startIndex': 0,
            'endIndex': len(text)
        }]


class CommentTagger:
    """Handles comment tagging operations and pattern learning"""
    
    def __init__(self, base_path="/app/server_files/comment_tagger"):
        self.base_path = base_path
        self.ensure_directories()
        self.segmenter = CommentSegmenter()
        
        # Load or initialize data structures
        self.tag_definitions = self.load_json("tag_definitions.json", {})
        self.training_data = self.load_json("training_data.json", [])
        self.patterns = self.load_json("patterns.json", {})
        self.model_cache = self.load_json("model_cache.json", {})
        self.tagged_comments = self.load_json("tagged_comments.json", {})
        self.segmentation_training = self.load_json("segmentation_training.json", [])
        
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
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text using SpaCy if available"""
        if nlp:
            doc = nlp(text)
            # Extract nouns, verbs, and named entities
            keywords = []
            for token in doc:
                if token.pos_ in ['NOUN', 'VERB', 'PROPN'] and not token.is_stop:
                    keywords.append(token.lemma_.lower())
            
            # Add named entities
            for ent in doc.ents:
                keywords.append(ent.text.lower())
            
            return list(set(keywords))
        else:
            # Fallback to simple extraction
            words = re.findall(r'\b[a-z]+\b', text.lower())
            stopwords = {'i', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 
                        'to', 'for', 'of', 'with', 'by', 'from', 'was', 'were', 'been'}
            return [w for w in words if w not in stopwords and len(w) > 2]
    
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
            'tags': assigned_tags,
            'timestamp': datetime.now().isoformat(),
            'keywords': keywords
        })
        
        # Persist changes
        self.save_json("patterns.json", self.patterns)
        self.save_json("training_data.json", self.training_data)
    
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
                        story_gid = story.get('gid')
                        
                        # Skip if already tagged
                        if tagger.is_comment_tagged(story_gid):
                            continue
                        
                        comment_text = story.get('text', '')
                        asana_date = story.get('created_at', '').split('T')[0] if story.get('created_at') else None
                        
                        # Use intelligent segmentation
                        segments = tagger.segment_comment(comment_text, asana_date)
                        
                        # Get tag suggestions for the first segment
                        suggestions = tagger.suggest_tags(segments[0]['text'] if segments else comment_text)
                        
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
            assigned_tags = comment_data.get('assigned_tags', [])
            
            if not story_gid or not comment_text:
                return jsonify({'error': 'Missing required data'}), 400
            
            # Save segmentation training data if user modified segments
            if segments:
                tagger.save_segmentation_training(comment_text, segments)
            
            if assigned_tags:  # Only save if tags were assigned
                # Learn from the tagging
                tagger.learn_from_tagging(comment_text, assigned_tags)
                
                # Mark comment as tagged
                tagger.tagged_comments[story_gid] = {
                    'tags': assigned_tags,
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
