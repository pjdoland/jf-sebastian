"""
Shared sentiment analysis for all devices.
Extracted from AnimatronicControlGenerator for reusability.
"""

import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Shared sentiment analysis utility."""

    def __init__(self):
        """Initialize sentiment analyzer."""
        self.analyzer = SentimentIntensityAnalyzer()

    def analyze(self, text: str) -> float:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            Sentiment score (-1.0 to 1.0, where positive = happy, negative = sad)
        """
        try:
            scores = self.analyzer.polarity_scores(text)
            compound_score = scores['compound']
            logger.debug(f"Sentiment: {text[:50]}... = {compound_score:.2f}")
            return compound_score
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return 0.0  # Neutral
