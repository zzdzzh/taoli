"""Tests for exchange commission and fee calculations."""

import pytest

from src.exchanges import (
    effective_exchange_odds,
    get_commission,
    is_exchange,
)


def test_is_exchange():
    """Test exchange identification."""
    assert is_exchange("betfair_ex_uk") is True
    assert is_exchange("smarkets") is True
    assert is_exchange("matchbook") is True
    assert is_exchange("betdaq") is True
    
    assert is_exchange("pinnacle") is False
    assert is_exchange("bet365") is False
    assert is_exchange("polymarket") is False
    assert is_exchange("kalshi") is False


def test_effective_exchange_odds():
    """Test effective odds calculation after commission."""
    # 5% commission, odds 2.0
    # Effective odds = 1 + (2.0 - 1) * (1 - 0.05) = 1.95
    eff_odds = effective_exchange_odds(2.0, 5.0)
    assert abs(eff_odds - 1.95) < 0.0001
    
    # 2% commission, odds 3.0
    # Effective odds = 1 + (3.0 - 1) * (1 - 0.02) = 2.96
    eff_odds = effective_exchange_odds(3.0, 2.0)
    assert abs(eff_odds - 2.96) < 0.0001
    
    # 0% commission, odds should remain unchanged
    eff_odds = effective_exchange_odds(2.5, 0.0)
    assert abs(eff_odds - 2.5) < 0.0001
    
    # Edge case: odds = 1.0 (no profit)
    eff_odds = effective_exchange_odds(1.0, 5.0)
    assert abs(eff_odds - 1.0) < 0.0001


def test_get_commission():
    """Test commission retrieval from config."""
    config = {
        "exchanges": {
            "betfair_ex_uk": {"commission_pct": 5.0},
            "smarkets": {"commission_pct": 2.0},
            "matchbook": {"commission_pct": 2.0},
        }
    }
    
    assert get_commission("betfair_ex_uk", config) == 5.0
    assert get_commission("smarkets", config) == 2.0
    assert get_commission("matchbook", config) == 2.0
    
    # Non-exchange bookmaker should return 0
    assert get_commission("pinnacle", config) == 0.0
    assert get_commission("bet365", config) == 0.0
    
    # Unknown exchange with no config should return 0
    assert get_commission("unknown_exchange", config) == 0.0


def test_commission_edge_cases():
    """Test edge cases in commission calculation."""
    # Very high commission (100%)
    eff_odds = effective_exchange_odds(2.0, 100.0)
    assert abs(eff_odds - 1.0) < 0.0001  # All profit taken
    
    # Very low odds with commission
    eff_odds = effective_exchange_odds(1.1, 5.0)
    assert 1.0 < eff_odds < 1.1
