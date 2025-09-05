"""
Date extraction utilities for comment segmentation
Handles detection and extraction of dates including period-separated formats
"""

import re
import logging
import dateparser
from dateparser.search import search_dates
from datetime import datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class DateExtractor:
    """Handles date detection and extraction from text segments"""
    
    def __init__(self):
        self.time_patterns = [
            r'\btoday\b',
            r'\byesterday\b',
            r'\b\d+\s*(day|week|month|year)s?\s*ago\b',
            r'\blast\s*(week|month|year)\b',
            r'\bthis\s*(morning|afternoon|evening)\b',
            r'\bearlier\b',
            r'\bpreviously\b',
        ]
        
        # Pattern to match ordinals that should NOT be treated as dates
        self.ordinal_pattern = re.compile(r'\b(\d{1,2})(st|nd|rd|th)\b', re.IGNORECASE)
        
        # Pattern to match dates attached to text with dashes or other punctuation
        # Matches MM/DD/YYYY, MM-DD-YYYY, MM.DD.YYYY formats
        self.date_attached_pattern = re.compile(
            r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})([^\s\d])',
            re.IGNORECASE
        )
    
    def preprocess_text_for_dates(self, text: str) -> str:
        """
        Preprocess text to handle dates attached to other text
        E.g., "07/24/2024-ICF" becomes "07/24/2024 - ICF"
        """
        # Add spaces around dates that are attached to text
        processed = self.date_attached_pattern.sub(r'\1 \2', text)
        
        # Also handle cases where text is attached before the date
        reverse_pattern = re.compile(r'([^\s\d])(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})')
        processed = reverse_pattern.sub(r'\1 \2', processed)
        
        return processed
    
    def is_ordinal_context(self, text: str, match_text: str) -> bool:
        """
        Check if a potential date match is actually an ordinal reference
        like "1st and 2nd email" rather than a date
        """
        # Check if the match is just an ordinal number
        if self.ordinal_pattern.match(match_text):
            # Look for context clues that this is NOT a date
            # Common non-date ordinal contexts
            non_date_contexts = [
                r'\b(and|or|,)\s*\d+(st|nd|rd|th)\b',  # "1st and 2nd", "1st or 2nd"
                r'\d+(st|nd|rd|th)\s+(email|message|attempt|try|time|round|step|phase)',
                r'(first|second|third|fourth|fifth)\s+(and|or)\s+\d+(st|nd|rd|th)',
            ]
            
            for pattern in non_date_contexts:
                if re.search(pattern, text, re.IGNORECASE):
                    logger.debug(f"Identified '{match_text}' as ordinal, not date due to context")
                    return True
        
        return False
    
    def validate_date(self, date_value: datetime, reference_date: datetime) -> bool:
        """
        Validate that a parsed date is reasonable for an activity log
        - Should not be in the future relative to the reference date
        - Should not be more than 10 years in the past (configurable)
        """
        if date_value > reference_date:
            logger.debug(f"Rejecting future date: {date_value} > {reference_date}")
            return False
        
        # Reject dates more than 10 years in the past (likely parsing errors)
        ten_years_ago = reference_date - timedelta(days=365 * 10)
        if date_value < ten_years_ago:
            logger.debug(f"Rejecting date too far in past: {date_value}")
            return False
        
        return True
    
    def parse_reference_date(self, asana_date: str) -> Optional[datetime]:
        """Parse the Asana date string to use as reference"""
        if not asana_date:
            return None
        try:
            return dateparser.parse(asana_date)
        except Exception as e:
            logger.warning(f"Could not parse asana_date {asana_date}: {e}")
            return None
    
    def has_date_or_time_reference(self, segment_text: str, asana_date: str = None, nlp=None) -> bool:
        """
        Check if segment contains:
        - An explicit date (equal to or before asana_date)
        - Time references to present/past (today, yesterday, X days/weeks ago, etc.)
        Uses dateparser's search_dates to find dates including period-separated formats
        """
        # Quick length check - very short segments unlikely to have dates
        if len(segment_text) < 3:
            return False
        
        # Preprocess text to handle attached dates
        processed_text = self.preprocess_text_for_dates(segment_text)
        segment_lower = processed_text.lower()
        
        # Check for past/present time references first (these are reliable)
        for pattern in self.time_patterns:
            if re.search(pattern, segment_lower):
                logger.debug(f"Found time pattern '{pattern}' in segment")
                return True
        
        # Parse asana_date to use as reference
        reference_date = self.parse_reference_date(asana_date) or datetime.now()
        
        # Use dateparser's search_dates to find any dates in the text
        try:
            dates_found = search_dates(
                processed_text,
                languages=['en'],
                settings={
                    'PREFER_DATES_FROM': 'past',
                    'RELATIVE_BASE': reference_date,
                    'DATE_ORDER': 'MDY',  # Try MDY first (common for period-separated US dates)
                    'STRICT_PARSING': False,
                }
            )
            
            if dates_found:
                # Check if any found date is valid and not an ordinal
                for date_string, date_value in dates_found:
                    # Skip if this is an ordinal context
                    if self.is_ordinal_context(processed_text, date_string):
                        continue
                    
                    # Validate the date
                    if self.validate_date(date_value, reference_date):
                        logger.debug(f"search_dates found valid past date: {date_string}")
                        return True
        except Exception as e:
            logger.debug(f"search_dates failed: {e}")
        
        # Fallback to SpaCy NER if available and search_dates didn't find anything
        if nlp:
            try:
                doc = nlp(processed_text[:1000])  # Limit text length for SpaCy
                for ent in doc.ents:
                    if ent.label_ in ['DATE', 'TIME']:
                        # Skip ordinals
                        if self.is_ordinal_context(processed_text, ent.text):
                            continue
                        
                        # Try to parse the date entity with dateparser
                        try:
                            parsed_date = dateparser.parse(
                                ent.text, 
                                settings={
                                    'PREFER_DATES_FROM': 'past',
                                    'STRICT_PARSING': False,
                                    'RELATIVE_BASE': reference_date,
                                    'DATE_ORDER': 'MDY'
                                }
                            )
                            if parsed_date and self.validate_date(parsed_date, reference_date):
                                logger.debug(f"SpaCy found valid past date: {ent.text}")
                                return True
                        except Exception as e:
                            logger.debug(f"Could not parse SpaCy date entity '{ent.text}': {e}")
            except Exception as e:
                logger.warning(f"SpaCy processing failed: {e}")
        
        return False
    
    def extract_segment_date(self, segment_text: str, asana_date: str, nlp=None) -> str:
        """
        Extract the most relevant date from a segment.
        Returns YYYY-MM-DD format.
        Uses asana_date as the reference point for relative dates.
        """
        # Preprocess text to handle attached dates
        processed_text = self.preprocess_text_for_dates(segment_text)
        
        # Parse asana_date to use as reference
        reference_date = self.parse_reference_date(asana_date) or datetime.now()
        
        if asana_date:
            logger.debug(f"Using asana_date {asana_date} as reference: {reference_date}")
        
        segment_lower = processed_text.lower()
        
        # Check for relative date phrases using reference_date
        if 'today' in segment_lower:
            return reference_date.strftime('%Y-%m-%d')
        elif 'yesterday' in segment_lower:
            return (reference_date - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Use dateparser's search_dates to find dates including period-separated formats
        try:
            dates_found = search_dates(
                processed_text,
                languages=['en'],
                settings={
                    'PREFER_DATES_FROM': 'past',
                    'RELATIVE_BASE': reference_date,
                    'DATE_ORDER': 'MDY',  # Try MDY first for period-separated US dates
                    'PREFER_DAY_OF_MONTH': 'first',
                    'STRICT_PARSING': False,
                }
            )
            
            if dates_found:
                # Return the first valid date found
                for date_string, date_value in dates_found:
                    # Skip ordinals
                    if self.is_ordinal_context(processed_text, date_string):
                        continue
                    
                    # Validate date
                    if self.validate_date(date_value, reference_date):
                        logger.debug(f"Extracted date '{date_string}' as {date_value.strftime('%Y-%m-%d')}")
                        return date_value.strftime('%Y-%m-%d')
        except Exception as e:
            logger.debug(f"search_dates failed in extract_segment_date: {e}")
        
        # Fallback to SpaCy NER if available
        if nlp:
            try:
                doc = nlp(processed_text[:1000])
                for ent in doc.ents:
                    if ent.label_ in ['DATE']:
                        # Skip ordinals
                        if self.is_ordinal_context(processed_text, ent.text):
                            continue
                        
                        # Try to parse the entity with dateparser using reference_date
                        try:
                            parsed_date = dateparser.parse(
                                ent.text,
                                settings={
                                    'PREFER_DATES_FROM': 'past',
                                    'STRICT_PARSING': False,
                                    'RELATIVE_BASE': reference_date,
                                    'DATE_ORDER': 'MDY',
                                    'PREFER_DAY_OF_MONTH': 'first',
                                }
                            )
                            if parsed_date and self.validate_date(parsed_date, reference_date):
                                logger.debug(f"SpaCy extracted date '{ent.text}' as {parsed_date.strftime('%Y-%m-%d')}")
                                return parsed_date.strftime('%Y-%m-%d')
                        except Exception as e:
                            logger.debug(f"Could not parse date entity '{ent.text}': {e}")
            except Exception as e:
                logger.warning(f"SpaCy date extraction failed: {e}")
        
        # Last resort: Try dateparser on the whole segment with reference_date
        try:
            # But skip if the segment looks like it contains ordinals
            if not re.search(r'\b\d+(st|nd|rd|th)\s+(and|or|email|message|attempt)', processed_text, re.IGNORECASE):
                parsed_date = dateparser.parse(
                    processed_text,
                    settings={
                        'PREFER_DATES_FROM': 'past',
                        'STRICT_PARSING': False,
                        'RELATIVE_BASE': reference_date,
                        'DATE_ORDER': 'MDY'
                    }
                )
                if parsed_date and self.validate_date(parsed_date, reference_date):
                    return parsed_date.strftime('%Y-%m-%d')
        except Exception as e:
            logger.debug(f"Dateparser fallback failed: {e}")
        
        # Default to asana date or today
        return asana_date or datetime.now().strftime('%Y-%m-%d')
