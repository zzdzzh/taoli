"""比赛结果获取（用于模拟盘结算）"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from .team_matcher import normalize_team, parse_vs_title

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"


def fetch_polymarket_result(home: str, away: str) -> str | None:
    """
    从 Polymarket 已结算市场获取胜平负结果。

    返回: "home" / "draw" / "away" 或 None
    """
    query = f"{home} vs {away}"
    try:
        resp = requests.get(
            f"{GAMMA_URL}/public-search",
            params={"q": query, "limit_per_type": 5},
            timeout=30,
        )
        resp.raise_for_status()
        events = resp.json().get("events", [])
    except requests.RequestException as e:
        logger.warning("Polymarket 搜索结果获取失败: %s", e)
        return None

    home_norm = normalize_team(home)
    away_norm = normalize_team(away)

    for event in events:
        title = event.get("title", "")
        if not event.get("closed"):
            continue
        teams = parse_vs_title(title)
        if teams is None:
            continue
        eh, ea = normalize_team(teams[0]), normalize_team(teams[1])
        if {eh, ea} != {home_norm, away_norm}:
            continue

        return _parse_h2h_result(event.get("markets", []), teams[0], teams[1])

    return None


def _parse_h2h_result(
    markets: list[dict[str, Any]],
    home: str,
    away: str,
) -> str | None:
    """从已关闭市场的 outcomePrices 判断胜者"""
    home_norm = home.lower().strip()
    away_norm = away.lower().strip()

    for market in markets:
        title = (market.get("groupItemTitle") or "").strip()
        if not title or re.search(r"\([+-]?\d", title):
            continue

        prices = market.get("outcomePrices")
        if not prices:
            continue
        if isinstance(prices, str):
            prices = json.loads(prices)

        yes_won = float(prices[0]) >= 0.99
        if not yes_won:
            continue

        lower = title.lower()
        if lower.startswith("draw") or lower == "tie":
            return "draw"
        if lower == home_norm:
            return "home"
        if lower == away_norm:
            return "away"

    return None


def auto_settle_open_positions(engine) -> int:
    """自动结算所有可获取结果的持仓，返回结算笔数"""
    count = 0
    for pos in list(engine.portfolio.positions):
        if pos.status != "open":
            continue
        result = fetch_polymarket_result(pos.home_team, pos.away_team)
        if result is None:
            continue
        engine.settle(pos.id, result)
        count += 1
        logger.info(
            "已结算 %s vs %s → %s，净利 %+.2f",
            pos.home_team, pos.away_team, result, pos.net_profit,
        )
    return count
