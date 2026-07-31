"""Myriad Markets 预测市场数据拉取

API 文档: https://docs.myriad.markets/builders/myriad-api-reference
站点: https://myriad.markets/markets
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from .converters import polymarket_price_to_odds
from .models import MatchOdds, OddsQuote
from .team_matcher import parse_vs_title

logger = logging.getLogger(__name__)

MYRIAD_API = "https://api-v2.myriadprotocol.com"

DRAW_NAMES = {"draw", "tie", "x", "平", "平局"}

# 与 Polymarket/Kalshi 一致：过滤空盘极端价
MIN_EXECUTABLE_ASK = 0.05
MAX_EXECUTABLE_ASK = 0.95
MIN_ASK_SUM = 0.90


class MyriadClient:
    """Myriad Protocol REST API 客户端（公开可读，可选 API Key 提高限额）"""

    def __init__(self, api_key: str = "", timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        key = (api_key or os.getenv("MYRIAD_API_KEY", "")).strip()
        if key:
            self.session.headers["x-api-key"] = key

    def fetch_soccer_matches(
        self,
        topics: list[str] | None = None,
        limit: int = 100,
    ) -> list[MatchOdds]:
        """拉取胜平负 moneyline 体育市场（标题形如 A vs. B: Who wins?）"""
        topic_list = topics or ["Sports"]
        all_matches: list[MatchOdds] = []

        for topic in topic_list:
            try:
                markets = self._fetch_moneyline_markets(topic, limit)
                parsed = [self._parse_market(m, topic) for m in markets]
                parsed = [m for m in parsed if m is not None]
                logger.info("Myriad %s: %d 场比赛", topic, len(parsed))
                all_matches.extend(parsed)
            except requests.RequestException as e:
                logger.warning("Myriad %s 拉取失败: %s", topic, e)

        return all_matches

    def _fetch_moneyline_markets(self, topic: str, limit: int) -> list[dict[str, Any]]:
        """分页拉取 open + moneyline 市场"""
        results: list[dict[str, Any]] = []
        page = 1
        page_limit = min(limit, 50)

        while len(results) < limit:
            resp = self.session.get(
                f"{MYRIAD_API}/markets",
                params={
                    "state": "open",
                    "moneyline": "true",
                    "topics": topic,
                    "sort": "expires_at",
                    "order": "asc",
                    "limit": page_limit,
                    "page": page,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            batch = payload.get("data") or []
            if not batch:
                break
            results.extend(batch)
            pag = payload.get("pagination") or {}
            if not pag.get("hasNext"):
                break
            page += 1

        return results[:limit]

    def _parse_market(self, market: dict[str, Any], topic: str) -> MatchOdds | None:
        raw_title = market.get("title") or market.get("shortName") or ""
        title = self._clean_title(raw_title)
        teams = parse_vs_title(title)
        if teams is None:
            return None
        home, away = teams

        commence = self._parse_time(
            market.get("expiresAt") or market.get("resolvesAt") or market.get("publishedAt")
        )
        quotes = self._parse_outcomes(market.get("outcomes") or [], home, away)
        if len(quotes) < 2:
            return None

        return MatchOdds(
            sport=f"myriad_{topic.lower()}",
            league=topic,
            home_team=home,
            away_team=away,
            commence_time=commence,
            quotes=quotes,
        )

    @staticmethod
    def _clean_title(title: str) -> str:
        # "A vs. B: Who wins?" → "A vs. B"
        text = re.sub(r":\s*Who wins\??\s*$", "", title.strip(), flags=re.IGNORECASE)
        return text.strip()

    def _parse_outcomes(
        self,
        outcomes: list[dict[str, Any]],
        home: str,
        away: str,
    ) -> list[OddsQuote]:
        quotes: list[OddsQuote] = []
        home_norm = home.lower().strip()
        away_norm = away.lower().strip()

        for oc in outcomes:
            name = (oc.get("title") or "").strip()
            if not name:
                continue
            outcome_key = self._map_outcome(name, home_norm, away_norm)
            if outcome_key is None:
                continue

            # 优先可执行买入价 bestAsk；AMM 常为空则用 mid price（仍受合理区间约束）
            raw = oc.get("bestAsk")
            if raw is None:
                raw = oc.get("price")
            try:
                price = float(raw)
            except (TypeError, ValueError):
                continue
            if not (MIN_EXECUTABLE_ASK <= price <= MAX_EXECUTABLE_ASK):
                continue
            odds = polymarket_price_to_odds(price)
            if odds <= 1.0:
                continue

            quotes.append(
                OddsQuote(
                    bookmaker="myriad",
                    outcome=outcome_key,
                    odds=odds,
                    outcome_name=name,
                    platform="prediction",
                    raw_price=price,
                )
            )

        # 多腿价之和过低 → 假盘
        priced = [q.raw_price for q in quotes if q.raw_price > 0]
        if len(priced) >= 2 and sum(priced) < (MIN_ASK_SUM if len(priced) == 2 else 0.92):
            return []
        return quotes

    @staticmethod
    def _map_outcome(name: str, home_norm: str, away_norm: str) -> str | None:
        lower = name.lower().strip()
        if lower in DRAW_NAMES:
            return "draw"
        if lower == home_norm or home_norm in lower or lower in home_norm:
            return "home"
        if lower == away_norm or away_norm in lower or lower in away_norm:
            return "away"
        return None

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        if isinstance(value, (int, float)):
            # unix seconds
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc)
