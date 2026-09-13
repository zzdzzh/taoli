"""Tests for team name matching logic."""

import pytest

from src.team_matcher import (
    normalize_team_name,
    teams_match,
    _remove_accents,
)


def test_normalize_team_name():
    """Test team name normalization."""
    # Basic normalization
    assert normalize_team_name("Manchester United") == "manchester united"
    assert normalize_team_name("FC Barcelona") == "barcelona"
    assert normalize_team_name("Real Madrid CF") == "real madrid"
    
    # Remove common suffixes
    assert normalize_team_name("Arsenal FC") == "arsenal"
    assert normalize_team_name("Bayern Munich e.V.") == "bayern munich"
    
    # Handle accents
    assert normalize_team_name("São Paulo") == "sao paulo"
    assert normalize_team_name("Atlético Madrid") == "atletico madrid"
    
    # Remove extra whitespace
    assert normalize_team_name("  Manchester   City  ") == "manchester city"


def test_remove_accents():
    """Test accent removal."""
    assert _remove_accents("São Paulo") == "Sao Paulo"
    assert _remove_accents("Atlético") == "Atletico"
    assert _remove_accents("Beyoğlu") == "Beyoglu"
    assert _remove_accents("Malmö") == "Malmo"
    assert _remove_accents("regular text") == "regular text"


def test_teams_match_exact():
    """Test exact team name matching."""
    assert teams_match("Arsenal", "Arsenal") is True
    assert teams_match("Manchester United", "Manchester United") is True


def test_teams_match_case_insensitive():
    """Test case-insensitive matching."""
    assert teams_match("Arsenal", "ARSENAL") is True
    assert teams_match("manchester united", "Manchester United") is True


def test_teams_match_with_suffix():
    """Test matching with different suffixes."""
    assert teams_match("Arsenal", "Arsenal FC") is True
    assert teams_match("Barcelona", "FC Barcelona") is True
    assert teams_match("Real Madrid", "Real Madrid CF") is True


def test_teams_match_with_accents():
    """Test matching with accents."""
    assert teams_match("Sao Paulo", "São Paulo") is True
    assert teams_match("Atletico Madrid", "Atlético Madrid") is True


def test_teams_match_abbreviations():
    """Test matching common abbreviations."""
    assert teams_match("Man United", "Manchester United") is True
    assert teams_match("Man City", "Manchester City") is True


def test_teams_not_match():
    """Test cases that should not match."""
    assert teams_match("Arsenal", "Chelsea") is False
    assert teams_match("Manchester United", "Manchester City") is False
    assert teams_match("Real Madrid", "Atletico Madrid") is False
