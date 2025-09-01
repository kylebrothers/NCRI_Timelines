"""
Tag suggestion module using NLP and similarity matching
"""

import logging
import numpy as np
from typing import List, Dict
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


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
            logger.warning(f"No training data available: vectors={self.segment_vectors is not None}, segments={len(self.trained_segments)}")
            return []
        
        try:
            # Transform new segment
            segment_vector = self.vectorizer.transform([segment_text])
            
            # Calculate similarities
            similarities = cosine_similarity(segment_vector, self.segment_vectors)[0]
            
            # Get top similar segments
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            # Log similarity scores for debugging
            logger.debug(f"Top similarity scores: {[float(similarities[i]) for i in top_indices]}")
            
            # Aggregate tags from similar segments with confidence scores
            tag_scores = defaultdict(float)
            for idx in top_indices:
                similarity = float(similarities[idx])  # Convert to native Python float
                if similarity > 0.05:  # Lowered threshold from 0.1 to 0.05 for more suggestions
                    for tag in self.segment_tags[idx]:
                        tag_scores[tag] += similarity
            
            # Log found tags
            logger.debug(f"Found tags from similar segments: {list(tag_scores.keys())}")
            
            # Normalize scores and create suggestions
            if tag_scores:
                max_score = max(tag_scores.values())
                suggestions = [
                    {
                        'tag': tag,
                        'confidence': float(score / max_score),  # Convert to native Python float
                        'auto_select': bool((score / max_score) > 0.7)  # Convert to native Python bool
                    }
                    for tag, score in sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
                ]
                logger.info(f"Returning {len(suggestions)} tag suggestions")
                return suggestions[:top_k]
            else:
                logger.info("No tags found above similarity threshold")
            
        except Exception as e:
            logger.error(f"Error suggesting tags: {e}")
        
        return []
