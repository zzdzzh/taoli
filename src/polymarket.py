"""Polymarket 预测市场数据拉取"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import requests

from .converters import polymarket_price_to_odds
from .models import MatchOdds, OddsQuote
from .team_matcher import parse_vs_title

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"

# Polymarket sport code → series_id（来自 /sports 接口）
POLYMARKET_SERIES: dict[str, str] = {
    # 足球
    "epl": "10188",
    "lal": "10193",
    "bun": "10194",
    "fl1": "10195",
    "sea": "10203",
    "ucl": "10204",
    "fifwc": "11433",
    "mls": "10189",
    "nor": "10362",
    "swe": "11637",
    "bra": "10359",
    "jap": "10360",
    "ja2": "10443",
    "kor": "10444",
    "uel": "10209",
    # 篮球
    "nba": "10345",
    "wnba": "10105",
    "euroleague": "10371",
    # 网球
    "atp": "10365",
    "wta": "10366",
}

# 胜负盘（无二项平局）联赛
POLYMARKET_2WAY_CODES = frozenset({"nba", "wnba", "atp", "wta", "euroleague"})


class PolymarketClient:
    """Polymarket Gamma API 客户端"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_soccer_matches(
        self,
        series_codes: list[str] | None = None,
        limit_per_series: int = 50,
    ) -> list[MatchOdds]:
        """拉取体育胜负/胜平负市场（足球、篮球、网球等）"""
        codes = series_codes or list(POLYMARKET_SERIES.keys())
        all_matches: list[MatchOdds] = []

        for code in codes:
            series_id = POLYMARKET_SERIES.get(code)
            if not series_id:
                logger.warning("未知 Polymarket 联赛代码: %s", code)
                continue
            try:
                events = self._fetch_events(series_id, limit_per_series)
                parsed = [self._parse_event(e, code) for e in events]
                parsed = [m for m in parsed if m is not None]
                logger.info("Polymarket %s: %d 场比赛", code, len(parsed))
                all_matches.extend(parsed)
            except requests.RequestException as e:
                logger.warning("Polymarket %s 拉取失败: %s", code, e)

        return all_matches

    def search_match(self, query: str) -> MatchOdds | None:
        """按队名搜索单场比赛"""
        resp = self.session.get(
            f"{GAMMA_URL}/public-search",
            params={"q": query, "limit_per_type": 5},
            timeout=self.timeout,
        )
        resp.raise_for_status()

        for event in resp.json().get("events", []):
            title = event.get("title", "")
            if " vs. " not in title and " vs " not in title.lower():
                continue
            if any(kw in title for kw in ("Props", "Halftime", "Exact Score")):
                continue
            return self._parse_event(event, "search")

        return None

    def _fetch_events(self, series_id: str, limit: int) -> list[dict[str, Any]]:
        resp = self.session.get(
            f"{GAMMA_URL}/events",
            params={
                "series_id": series_id,
                "active": "true",
                "closed": "false",
                "limit": limit,
                "order": "startDate",
                "ascending": "true",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_event(
        self,
        event: dict[str, Any],
        league_code: str,
    ) -> MatchOdds | None:
        title = event.get("title", "")
        if not self._is_main_match_event(title):
            return None

        teams = parse_vs_title(title)
        if teams is None:
            return None
        home, away = teams

        commence = self._parse_time(event.get("endDate") or event.get("startDate"))
        quotes = self._parse_h2h_markets(event.get("markets", []), home, away)
        min_quotes = 2 if league_code in POLYMARKET_2WAY_CODES else 3
        if len(quotes) < min_quotes:
            return None

        return MatchOdds(
            sport=f"polymarket_{league_code}",
            league=event.get("seriesSlug", league_code),
            home_team=home,
            away_team=away,
            commence_time=commence,
            quotes=quotes,
        )

    @staticmethod
    def _is_main_match_event(title: str) -> bool:
        if " vs. " not in title and " vs " not in title.lower():
            return False
        skip_keywords = (
            "Props", "Halftime", "Half Time", "Exact Score",
            "First Team", "Second Half", "advance", "Winner",
            "Both Teams", "Total Goals", "O/U", "Spread",
        )
        return not any(kw.lower() in title.lower() for kw in skip_keywords)

    def _parse_h2h_markets(
        self,
        markets: list[dict[str, Any]],
        home: str,
        away: str,
    ) -> list[OddsQuote]:
        """解析胜平负三个市场（严格过滤，排除让球盘/大小球）"""
        quotes: list[OddsQuote] = []
        home_norm = home.lower().strip()
        away_norm = away.lower().strip()

        for market in markets:
            group_title = (market.get("groupItemTitle") or "").strip()
            if not group_title:
                continue

            # 排除让球盘、大小球等非胜平负市场
            if self._is_non_h2h_market(group_title):
                continue

            outcome = self._map_outcome(group_title, home_norm, away_norm)
            if outcome is None:
                continue

            ask = market.get("bestAsk")
            if ask is None:
                prices = market.get("outcomePrices")
                if prices:
                    if isinstance(prices, str):
                        prices = json.loads(prices)
                    ask = float(prices[0]) if prices else None

            if ask is None or ask <= 0:
                continue

            odds = polymarket_price_to_odds(float(ask))
            if odds <= 1.0:
                continue

            quotes.append(
                OddsQuote(
                    bookmaker="polymarket",
                    outcome=outcome,
                    odds=odds,
                    outcome_name=group_title,
                    platform="prediction",
                    raw_price=float(ask),
                )
            )

        return quotes

    @staticmethod
    def _is_non_h2h_market(title: str) -> bool:
        """判断是否为非胜平负市场"""
        lower = title.lower()
        # 让球盘: "France (-5.5)", "Spain (+1.5)"
        if re.search(r"\([+-]?\d", title):
            return True
        # 大小球、进球数等
        skip = (" goals", " score", "o/u", "over", "under", "btts", "both teams")
        return any(kw in lower for kw in skip)

    @staticmethod
    def _map_outcome(
        group_title: str,
        home_norm: str,
        away_norm: str,
    ) -> str | None:
        title_lower = group_title.lower().strip()

        if title_lower.startswith("draw") or title_lower in ("tie", "x"):
            return "draw"
        # 精确匹配队名，避免 "France (-5.5)" 被误判
        if title_lower == home_norm:
            return "home"
        if title_lower == away_norm:
            return "away"
        return None

    @staticmethod
    def _parse_time(value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
