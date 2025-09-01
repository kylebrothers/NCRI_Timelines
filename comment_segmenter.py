"""
Comment segmentation module using SpaCy NLP for intelligent text splitting
"""

import os
import json
import re
import logging
import spacy
from datetime import datetime
from typing import List, Dict
from date_extraction import DateExtractor

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
        self.date_extractor = DateExtractor()
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
        
        Algorithm:
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
    
    def merge_segments_without_dates(self, segments: List[Dict], doc, asana_date: str) -> List[Dict]:
        """
        Merge segments that don't contain dates/time references with the previous segment.
        Continue until all segments have dates or only one segment remains.
        """
        logger.info(f"Starting merge process with {len(segments)} segments")
        
        # First, mark which segments have dates/time references
        for i, segment in enumerate(segments):
            has_date = self.date_extractor.has_date_or_time_reference(segment['text'], asana_date, self.nlp)
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
                    prev_segment['has_date_or_time'] = self.date_extractor.has_date_or_time_reference(merged_text, asana_date, self.nlp)
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
            segment_date = self.date_extractor.extract_segment_date(segment['text'], asana_date, self.nlp)
            
            final_segments.append({
                'text': segment['text'],
                'date': segment_date,
                'dateSource': 'extracted' if segment['has_date_or_time'] else 'asana_timestamp',
                'startIndex': segment['startIndex'],
                'endIndex': segment['endIndex']
            })
        
        return final_segments
    
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
