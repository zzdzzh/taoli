"""Pytest configuration and shared fixtures."""

from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def root_dir():
    """返回项目根目录路径。"""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_config():
    """返回示例配置字典。"""
    return {
        "sources": {
            "sportsbooks": True,
            "polymarket": True,
            "kalshi": True,
            "myriad": True,
            "betfair": True,
        },
        "bookmakers": ["pinnacle", "onexbet", "betfair_ex_uk"],
        "exchanges": {
            "betfair_ex_uk": {"commission_pct": 5.0},
            "smarkets": {"commission_pct": 2.0},
            "matchbook": {"commission_pct": 2.0},
        },
        "max_arb_index": 0.98,
        "min_profit_pct": 0.0,
        "paper_trade": {
            "initial_bankroll": 100000,
            "stake_per_trade": 10000,
            "slippage_pct": 0.5,
            "fx_loss_pct": 0.3,
        },
    }


@pytest.fixture
def sample_timestamp():
    """返回示例时间戳。"""
    return datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
