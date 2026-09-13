"""Tests for price conversion logic (prediction markets to odds)."""

import pytest

from src.converters import polymarket_price_to_odds, kalshi_price_to_odds


def test_polymarket_price_to_odds():
    """Test Polymarket price (0-1) to odds conversion."""
    # Price 0.5 -> odds 2.0
    odds = polymarket_price_to_odds(0.5)
    assert abs(odds - 2.0) < 0.0001
    
    # Price 0.25 -> odds 4.0
    odds = polymarket_price_to_odds(0.25)
    assert abs(odds - 4.0) < 0.0001
    
    # Price 0.33 -> odds ~3.03
    odds = polymarket_price_to_odds(0.33)
    assert 3.0 < odds < 3.1
    
    # Edge case: very low price
    odds = polymarket_price_to_odds(0.01)
    assert odds == 100.0
    
    # Edge case: very high price
    odds = polymarket_price_to_odds(0.99)
    assert 1.0 < odds < 1.02


def test_kalshi_price_to_odds():
    """Test Kalshi price (0-100 cents) to odds conversion."""
    # Price 50 -> odds 2.0
    odds = kalshi_price_to_odds(50)
    assert abs(odds - 2.0) < 0.0001
    
    # Price 25 -> odds 4.0
    odds = kalshi_price_to_odds(25)
    assert abs(odds - 4.0) < 0.0001
    
    # Price 33 -> odds ~3.03
    odds = kalshi_price_to_odds(33)
    assert 3.0 < odds < 3.1
    
    # Edge case: very low price
    odds = kalshi_price_to_odds(1)
    assert odds == 100.0
    
    # Edge case: very high price
    odds = kalshi_price_to_odds(99)
    assert 1.0 < odds < 1.02


def test_invalid_prices():
    """Test handling of invalid prices."""
    # Polymarket: price must be > 0
    with pytest.raises((ValueError, ZeroDivisionError)):
        polymarket_price_to_odds(0.0)
    
    # Kalshi: price must be > 0
    with pytest.raises((ValueError, ZeroDivisionError)):
        kalshi_price_to_odds(0)
