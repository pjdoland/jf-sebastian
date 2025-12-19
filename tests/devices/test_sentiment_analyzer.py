"""
Tests for shared SentimentAnalyzer utility.
"""

import pytest
from jf_sebastian.devices.shared.sentiment_analyzer import SentimentAnalyzer


def test_sentiment_analyzer_initialization():
    """Test SentimentAnalyzer initialization."""
    analyzer = SentimentAnalyzer()
    assert analyzer.analyzer is not None


def test_sentiment_analyzer_positive_sentiment():
    """Test analysis of positive text."""
    analyzer = SentimentAnalyzer()

    positive_texts = [
        "I am so happy and excited!",
        "This is absolutely wonderful and amazing!",
        "What a great and fantastic day!",
        "I love this so much!"
    ]

    for text in positive_texts:
        score = analyzer.analyze(text)
        assert isinstance(score, float)
        assert score > 0.0, f"Expected positive sentiment for: {text}"
        assert -1.0 <= score <= 1.0


def test_sentiment_analyzer_negative_sentiment():
    """Test analysis of negative text."""
    analyzer = SentimentAnalyzer()

    negative_texts = [
        "I am so sad and disappointed.",
        "This is terrible and awful.",
        "What a horrible and dreadful situation.",
        "I hate this so much."
    ]

    for text in negative_texts:
        score = analyzer.analyze(text)
        assert isinstance(score, float)
        assert score < 0.0, f"Expected negative sentiment for: {text}"
        assert -1.0 <= score <= 1.0


def test_sentiment_analyzer_neutral_sentiment():
    """Test analysis of neutral text."""
    analyzer = SentimentAnalyzer()

    neutral_texts = [
        "The cat is on the mat.",
        "It is raining today.",
        "The meeting is at 3 PM.",
        "There are five apples."
    ]

    for text in neutral_texts:
        score = analyzer.analyze(text)
        assert isinstance(score, float)
        assert -0.3 <= score <= 0.3, f"Expected neutral sentiment for: {text}"
        assert -1.0 <= score <= 1.0


def test_sentiment_analyzer_empty_string():
    """Test analysis of empty string."""
    analyzer = SentimentAnalyzer()
    score = analyzer.analyze("")

    assert isinstance(score, float)
    assert -1.0 <= score <= 1.0


def test_sentiment_analyzer_special_characters():
    """Test analysis with special characters."""
    analyzer = SentimentAnalyzer()

    texts = [
        "Great!!! :)",
        "Terrible... :(",
        "Okay, I guess.",
    ]

    for text in texts:
        score = analyzer.analyze(text)
        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0


def test_sentiment_analyzer_error_handling():
    """Test error handling in sentiment analysis."""
    analyzer = SentimentAnalyzer()

    # Test with None (should handle gracefully or error)
    try:
        score = analyzer.analyze(None)
        # If it doesn't error, should return neutral
        assert score == 0.0
    except (TypeError, AttributeError):
        # It's okay if it errors on None
        pass


def test_sentiment_analyzer_consistent_results():
    """Test that analyzer returns consistent results for same input."""
    analyzer = SentimentAnalyzer()

    text = "This is a wonderful and amazing experience!"
    score1 = analyzer.analyze(text)
    score2 = analyzer.analyze(text)

    # Should return same score for same input
    assert score1 == score2


def test_sentiment_analyzer_range():
    """Test that all scores are in valid range."""
    analyzer = SentimentAnalyzer()

    test_texts = [
        "extremely happy and joyful and wonderful!",
        "very sad and terrible and awful.",
        "neutral statement about weather",
        "mixed feelings: good but also bad",
    ]

    for text in test_texts:
        score = analyzer.analyze(text)
        assert -1.0 <= score <= 1.0, f"Score out of range for: {text}"
