"""
Date extraction utilities for comment segmentation
Handles detection and extraction of dates including period-separated formats
"""

import re
import logging
import dateparser
from dateparser.search import search_dates
from datetime import datetime, timedelta
from typing import Optional

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
            
        segment_lower = segment_text.lower()
        
        # Check for past/present time references first (these are reliable)
        for pattern in self.time_patterns:
            if re.search(pattern, segment_lower):
                logger.debug(f"Found time pattern '{pattern}' in segment")
                return True
        
        # Parse asana_date to use as reference
        reference_date = self.parse_reference_date(asana_date) or datetime.now()
        
        # Use dateparser's search_dates to find any dates in the text
        # This should catch period-separated dates and other formats
        try:
            dates_found = search_dates(
                segment_text,
                languages=['en'],
                settings={
                    'PREFER_DATES_FROM': 'past',
                    'RELATIVE_BASE': reference_date,
                    'DATE_ORDER': 'MDY',  # Try MDY first (common for period-separated US dates)
                }
            )
            
            if dates_found:
                # Check if any found date is in the past
                for date_string, date_value in dates_found:
                    if date_value <= reference_date:
                        logger.debug(f"search_dates found valid past date: {date_string}")
                        return True
        except Exception as e:
            logger.debug(f"search_dates failed: {e}")
        
        # Fallback to SpaCy NER if available and search_dates didn't find anything
        if nlp:
            try:
                doc = nlp(segment_text[:1000])  # Limit text length for SpaCy
                for ent in doc.ents:
                    if ent.label_ in ['DATE', 'TIME']:
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
                            if parsed_date and parsed_date <= reference_date:
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
        # Parse asana_date to use as reference
        reference_date = self.parse_reference_date(asana_date) or datetime.now()
        
        if asana_date:
            logger.debug(f"Using asana_date {asana_date} as reference: {reference_date}")
        
        segment_lower = segment_text.lower()
        
        # Check for relative date phrases using reference_date
        if 'today' in segment_lower:
            return reference_date.strftime('%Y-%m-%d')
        elif 'yesterday' in segment_lower:
            return (reference_date - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Use dateparser's search_dates to find dates including period-separated formats
        try:
            dates_found = search_dates(
                segment_text,
                languages=['en'],
                settings={
                    'PREFER_DATES_FROM': 'past',
                    'RELATIVE_BASE': reference_date,
                    'DATE_ORDER': 'MDY',  # Try MDY first for period-separated US dates
                    'PREFER_DAY_OF_MONTH': 'first',
                }
            )
            
            if dates_found:
                # Return the first valid past date found
                for date_string, date_value in dates_found:
                    if date_value.date() <= reference_date.date():
                        logger.debug(f"Extracted date '{date_string}' as {date_value.strftime('%Y-%m-%d')}")
                        return date_value.strftime('%Y-%m-%d')
        except Exception as e:
            logger.debug(f"search_dates failed in extract_segment_date: {e}")
        
        # Fallback to SpaCy NER if available
        if nlp:
            try:
                doc = nlp(segment_text[:1000])
                for ent in doc.ents:
                    if ent.label_ in ['DATE']:
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
                            if parsed_date and parsed_date.date() <= reference_date.date():
                                logger.debug(f"SpaCy extracted date '{ent.text}' as {parsed_date.strftime('%Y-%m-%d')}")
                                return parsed_date.strftime('%Y-%m-%d')
                        except Exception as e:
                            logger.debug(f"Could not parse date entity '{ent.text}': {e}")
            except Exception as e:
                logger.warning(f"SpaCy date extraction failed: {e}")
        
        # Last resort: Try dateparser on the whole segment with reference_date
        try:
            parsed_date = dateparser.parse(
                segment_text,
                settings={
                    'PREFER_DATES_FROM': 'past',
                    'STRICT_PARSING': False,  # Be less strict to catch more date formats
                    'RELATIVE_BASE': reference_date,
                    'DATE_ORDER': 'MDY'
                }
            )
            if parsed_date and parsed_date.date() <= reference_date.date():
                return parsed_date.strftime('%Y-%m-%d')
        except Exception as e:
            logger.debug(f"Dateparser fallback failed: {e}")
        
        # Default to asana date or today
        return asana_date or datetime.now().strftime('%Y-%m-%d')
