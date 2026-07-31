"""Kalshi 预测市场数据拉取"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .converters import polymarket_price_to_odds
from .models import MatchOdds, OddsQuote

logger = logging.getLogger(__name__)

KALSHI_URL = "https://external-api.kalshi.com/trade-api/v2"

# 与 Polymarket 一致：过滤空盘口极端 ask
MIN_EXECUTABLE_ASK = 0.05
MAX_EXECUTABLE_ASK = 0.95

# Kalshi 体育 series ticker
KALSHI_SOCCER_SERIES: dict[str, str] = {
    # 足球
    "epl": "KXEPLGAME",
    "laliga": "KXLALIGAGAME",
    "bundesliga": "KXBUNDESLIGAGAME",
    "seriea": "KXSERIEAGAME",
    "ligue1": "KXLIGUE1GAME",
    "ucl": "KXUCLGAME",
    "worldcup": "KXWCGAME",
    "mls": "KXMLSGAME",
    "uel": "KXUELGAME",
    # 篮球
    "nba": "KXNBAGAME",
    "wnba": "KXWNBAGAME",
    # 棒球 / 冰球 / 美式足球
    "mlb": "KXMLBGAME",
    "nhl": "KXNHLGAME",
    "nfl": "KXNFLGAME",
    # 网球
    "atp": "KXATPMATCH",
    "wta": "KXWTAMATCH",
}

# 胜负盘（无平局）联赛
KALSHI_2WAY_CODES = frozenset({"nba", "wnba", "atp", "wta", "mlb", "nhl", "nfl"})


class KalshiClient:
    """Kalshi 公开 API 客户端（无需认证）"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_soccer_matches(
        self,
        series_codes: list[str] | None = None,
        limit_per_series: int = 200,
    ) -> list[MatchOdds]:
        """拉取体育胜负/胜平负市场（足球、篮球、网球等）"""
        codes = series_codes or list(KALSHI_SOCCER_SERIES.keys())
        all_matches: list[MatchOdds] = []

        for code in codes:
            series_ticker = KALSHI_SOCCER_SERIES.get(code)
            if not series_ticker:
                continue
            try:
                markets = self._fetch_markets(series_ticker, limit_per_series)
                matches = self._group_into_matches(markets, code)
                logger.info("Kalshi %s: %d 场比赛", code, len(matches))
                all_matches.extend(matches)
            except requests.RequestException as e:
                logger.warning("Kalshi %s 拉取失败: %s", code, e)
            time.sleep(1)

        return all_matches

    def _fetch_markets(
        self,
        series_ticker: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        all_markets: list[dict[str, Any]] = []
        cursor = ""

        while len(all_markets) < limit:
            params: dict[str, Any] = {
                "status": "open",
                "series_ticker": series_ticker,
                "limit": min(200, limit - len(all_markets)),
            }
            if cursor:
                params["cursor"] = cursor

            resp = self.session.get(
                f"{KALSHI_URL}/markets",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("markets", [])
            all_markets.extend(batch)

            cursor = data.get("cursor", "")
            if not cursor or not batch:
                break

        return all_markets

    def _group_into_matches(
        self,
        markets: list[dict[str, Any]],
        league_code: str,
    ) -> list[MatchOdds]:
        """将 Kalshi 的二元市场按 event 分组为胜平负"""
        events: dict[str, list[dict[str, Any]]] = {}

        for market in markets:
            event_ticker = market.get("event_ticker", "")
            if event_ticker:
                events.setdefault(event_ticker, []).append(market)

        matches: list[MatchOdds] = []

        for event_ticker, event_markets in events.items():
            match = self._parse_event(event_ticker, event_markets, league_code)
            if match is not None:
                matches.append(match)

        return matches

    def _parse_event(
        self,
        event_ticker: str,
        markets: list[dict[str, Any]],
        league_code: str,
    ) -> MatchOdds | None:
        is_2way = league_code in KALSHI_2WAY_CODES
        min_markets = 2 if is_2way else 3
        min_quotes = 2 if is_2way else 3

        if len(markets) < min_markets:
            return None

        # 从 event_ticker 或 title 解析队名
        # 例: KXWCGAME-26JUL15ENGARG → England vs Argentina
        home, away = self._parse_teams_from_markets(markets)
        if not home or not away:
            return None

        quotes: list[OddsQuote] = []
        close_time = None

        for market in markets:
            subtitle = (
                market.get("yes_sub_title")
                or market.get("subtitle")
                or market.get("title", "")
            )
            outcome = self._map_outcome(subtitle, home, away, market.get("ticker", ""))
            if outcome is None:
                continue

            price = self._get_yes_ask(market)
            if price is None or price <= 0:
                continue

            odds = polymarket_price_to_odds(price)
            if odds <= 1.0:
                continue

            quotes.append(
                OddsQuote(
                    bookmaker="kalshi",
                    outcome=outcome,
                    odds=odds,
                    outcome_name=subtitle,
                    platform="prediction",
                    raw_price=price,
                )
            )

            if market.get("close_time"):
                close_time = market["close_time"]

        if len(quotes) < min_quotes:
            return None

        # 同事件多腿 ask 之和过低 → 空盘假价
        priced = [q.raw_price for q in quotes if q.raw_price > 0]
        if len(priced) >= 2:
            min_sum = 0.90 if len(priced) == 2 else 0.92
            if sum(priced) < min_sum:
                return None

        # 优先用 occurrence_datetime（实际比赛结束时间），估算开始时间，其次 close_time
        game_time = markets[0].get("occurrence_datetime") or close_time
        commence = self._parse_close_time(game_time)
        # 将结束时间减去 3 小时估算为开始时间，统一与 Polymarket endDate 对齐
        commence = commence - timedelta(hours=3)

        return MatchOdds(
            sport=f"kalshi_{league_code}",
            league=league_code,
            home_team=home,
            away_team=away,
            commence_time=commence,
            quotes=quotes,
        )

    def _get_yes_ask(self, market: dict[str, Any]) -> float | None:
        """
        获取 YES 可成交买入价（美元 0~1）。

        优先级：
        1) 市场字段 yes_ask / yes_ask_dollars（实时最优卖单）
        2) orderbook：yes_ask ≈ 1 - best_no_bid
        不用 last_price（成交价，非可成交盘口，会虚高理论收益）
        """
        for key in ("yes_ask_dollars", "yes_ask"):
            raw = market.get(key)
            if raw is None or raw == "" or raw == 0:
                continue
            try:
                price = float(raw)
            except (TypeError, ValueError):
                continue
            # dollars 字段已是 0~1；美分字段常为 1~99
            if price > 1:
                price = price / 100.0
            if MIN_EXECUTABLE_ASK <= price <= MAX_EXECUTABLE_ASK:
                return price

        ticker = market.get("ticker", "")
        if not ticker:
            return None

        try:
            resp = self.session.get(
                f"{KALSHI_URL}/markets/{ticker}/orderbook",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            ofp = data.get("orderbook_fp") or data.get("orderbook") or {}
            no_bids = ofp.get("no_dollars") or ofp.get("no") or []
            if no_bids:
                # Kalshi 盘口各边一般为升序 bids；最优在末尾
                best_no_bid = float(no_bids[-1][0])
                if best_no_bid > 1:
                    best_no_bid = best_no_bid / 100.0
                yes_ask = 1.0 - best_no_bid
                if MIN_EXECUTABLE_ASK <= yes_ask <= MAX_EXECUTABLE_ASK:
                    return yes_ask
        except (requests.RequestException, TypeError, ValueError, IndexError):
            pass

        return None

    @staticmethod
    def _parse_teams_from_markets(
        markets: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """从市场数据推断主客队"""
        home, away = "", ""

        def _clean(name: str) -> str:
            name = re.sub(r"^Reg Time:\s*", "", name, flags=re.I).strip()
            name = re.sub(r"\s*Winner\??$", "", name, flags=re.I).strip()
            return name

        # 优先用 yes_sub_title（城市/队名干净，避免标题里的 Winner?）
        teams: list[str] = []
        for market in markets:
            subtitle = (
                market.get("yes_sub_title")
                or market.get("subtitle")
                or ""
            )
            team = _clean(subtitle)
            if not team or team.lower() in ("tie", "draw"):
                continue
            if team not in teams:
                teams.append(team)
        if len(teams) >= 2:
            return teams[0], teams[1]

        title = markets[0].get("title", "")

        # 网球: "Will Quentin Halys win the Cina vs Halys: Round Of 32 match?"
        m = re.search(r"win the (.+?) vs\.?\s+(.+?)\s*:", title, re.I)
        if m:
            return _clean(m.group(1)), _clean(m.group(2))

        # NFL/NBA 等: "Will Seattle win the Dallas vs Seattle Pro Football game?"
        m = re.search(
            r"win the (.+?) vs\.?\s+(.+?)(?:\s+(?:women's|men's|professional|pro|game).*)?$",
            title, re.I,
        )
        if m:
            return _clean(m.group(1)), _clean(m.group(2))

        # 常规 "TeamA vs TeamB" 格式
        m = re.search(
            r"^(.+?)\s+(?:vs\.?|v)\s+(.+?)(?:\s+(?:women's|men's|professional|pro).*)?$",
            title, re.I,
        )
        if m:
            home = _clean(m.group(1))
            away = _clean(m.group(2))

        if not home or not away:
            rules = markets[0].get("rules_primary", "")
            m = re.search(
                r"(.+?)\s+vs\.?\s+(.+?)(?:\s+(?:women's|men's|professional|pro).*)?$",
                rules, re.I,
            )
            if m:
                home = _clean(m.group(1))
                away = _clean(m.group(2))

        return home, away

    @staticmethod
    def _map_outcome(
        subtitle: str,
        home: str,
        away: str,
        ticker: str,
    ) -> str | None:
        text = subtitle.lower().strip()
        suffix = ticker.rsplit("-", 1)[-1].upper() if ticker else ""

        if suffix in ("TIE", "DRAW") or "tie" in text or text == "draw":
            return "draw"
        if suffix == home[:3].upper() or home.lower() in text:
            return "home"
        if suffix == away[:3].upper() or away.lower() in text:
            return "away"

        # 按队名匹配
        team = re.sub(r"^reg time:\s*", "", subtitle).strip().lower()
        if team == home.lower():
            return "home"
        if team == away.lower():
            return "away"
        if "tie" in team or "draw" in team:
            return "draw"

        return None

    @staticmethod
    def _parse_close_time(value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
