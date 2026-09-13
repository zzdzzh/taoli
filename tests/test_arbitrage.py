"""Tests for arbitrage calculation logic."""

from datetime import datetime, timezone

import pytest

from src.arbitrage import (
    calc_arb_index,
    calc_profit_pct,
    find_best_quotes,
    infer_outcomes,
)
from src.models import ArbitrageLeg, MatchOdds, OddsQuote


def test_calc_arb_index_3way():
    """Test arbitrage index calculation for 3-way market (soccer)."""
    # Perfect arbitrage: 1/2 + 1/3 + 1/6 = 1
    index = calc_arb_index([2.0, 3.0, 6.0])
    assert abs(index - 1.0) < 0.0001
    
    # Profitable arbitrage
    index = calc_arb_index([2.1, 3.1, 6.5])
    assert index < 1.0
    
    # No arbitrage
    index = calc_arb_index([1.8, 2.5, 4.0])
    assert index > 1.0


def test_calc_arb_index_2way():
    """Test arbitrage index calculation for 2-way market (tennis, basketball)."""
    # Perfect arbitrage: 1/2 + 1/2 = 1
    index = calc_arb_index([2.0, 2.0])
    assert abs(index - 1.0) < 0.0001
    
    # Profitable arbitrage
    index = calc_arb_index([2.1, 2.1])
    assert index < 1.0
    
    # No arbitrage
    index = calc_arb_index([1.8, 1.8])
    assert index > 1.0


def test_calc_profit_pct():
    """Test profit percentage calculation."""
    # S = 0.98 -> profit = (1/0.98 - 1) * 100 ≈ 2.04%
    profit = calc_profit_pct(0.98)
    assert 2.0 < profit < 2.1
    
    # S = 1.0 -> no profit
    profit = calc_profit_pct(1.0)
    assert abs(profit) < 0.0001
    
    # S = 1.02 -> negative profit
    profit = calc_profit_pct(1.02)
    assert profit < 0


def test_infer_outcomes_soccer():
    """Test outcome inference for soccer (3-way)."""
    match = MatchOdds(
        sport="soccer_epl",
        league="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        commence_time=datetime.now(timezone.utc),
        quotes=[
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="home",
                outcome_name="Arsenal",
                odds=2.0,
                last_update=datetime.now(timezone.utc),
            ),
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="draw",
                outcome_name="Draw",
                odds=3.5,
                last_update=datetime.now(timezone.utc),
            ),
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="away",
                outcome_name="Chelsea",
                odds=4.0,
                last_update=datetime.now(timezone.utc),
            ),
        ],
    )
    outcomes = infer_outcomes(match)
    assert outcomes == ("home", "draw", "away")


def test_infer_outcomes_tennis():
    """Test outcome inference for tennis (2-way)."""
    match = MatchOdds(
        sport="tennis_atp",
        league="ATP",
        home_team="Djokovic",
        away_team="Nadal",
        commence_time=datetime.now(timezone.utc),
        quotes=[
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="home",
                outcome_name="Djokovic",
                odds=1.8,
                last_update=datetime.now(timezone.utc),
            ),
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="away",
                outcome_name="Nadal",
                odds=2.2,
                last_update=datetime.now(timezone.utc),
            ),
        ],
    )
    outcomes = infer_outcomes(match)
    assert outcomes == ("home", "away")


def test_find_best_quotes_simple():
    """Test finding best quotes across bookmakers."""
    match = MatchOdds(
        sport="soccer_epl",
        league="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        commence_time=datetime.now(timezone.utc),
        quotes=[
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="home",
                outcome_name="Arsenal",
                odds=2.0,
                last_update=datetime.now(timezone.utc),
            ),
            OddsQuote(
                bookmaker="bet365",
                platform="sportsbook",
                outcome="home",
                outcome_name="Arsenal",
                odds=2.1,  # Better odds
                last_update=datetime.now(timezone.utc),
            ),
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="away",
                outcome_name="Chelsea",
                odds=3.0,
                last_update=datetime.now(timezone.utc),
            ),
        ],
    )
    
    best = find_best_quotes(match, ("home", "away"))
    assert "home" in best
    assert "away" in best
    assert best["home"].odds == 2.1
    assert best["home"].bookmaker == "bet365"
    assert best["away"].odds == 3.0


def test_find_best_quotes_missing_outcome():
    """Test handling of missing outcomes."""
    match = MatchOdds(
        sport="soccer_epl",
        league="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        commence_time=datetime.now(timezone.utc),
        quotes=[
            OddsQuote(
                bookmaker="pinnacle",
                platform="sportsbook",
                outcome="home",
                outcome_name="Arsenal",
                odds=2.0,
                last_update=datetime.now(timezone.utc),
            ),
            # Missing draw and away
        ],
    )
    
    best = find_best_quotes(match, ("home", "draw", "away"))
    assert "home" in best
    assert "draw" not in best
    assert "away" not in best
