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
CLOB_URL = "https://clob.polymarket.com"

# 可成交价合理性：过低/过高的 ask 多为空盘口挂单，会产生假套利（如赔率 50）
MIN_EXECUTABLE_ASK = 0.05   # 对应赔率上限约 20
MAX_EXECUTABLE_ASK = 0.95   # 对应赔率下限约 1.05
# 二元 moneyline 两边 ask 之和过低 = 无真实深度
MIN_MONEYLINE_ASK_SUM = 0.90


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
    # 棒球 / 冰球 / 美式足球
    "mlb": "3",
    "nhl": "10346",
    "nfl": "10187",
    # 网球
    "atp": "10365",
    "wta": "10366",
}

# 胜负盘（无二项平局）联赛
POLYMARKET_2WAY_CODES = frozenset({
    "nba", "wnba", "atp", "wta", "euroleague", "mlb", "nhl", "nfl",
})


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
                clob_asks = self._fetch_clob_buy_prices(
                    self._collect_yes_token_ids(events)
                )
                parsed = [
                    self._parse_event(e, code, clob_asks) for e in events
                ]
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
            clob_asks = self._fetch_clob_buy_prices(
                self._collect_yes_token_ids([event])
            )
            return self._parse_event(event, "search", clob_asks)

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
        clob_asks: dict[str, float] | None = None,
    ) -> MatchOdds | None:
        title = event.get("title", "")
        if not self._is_main_match_event(title):
            return None

        teams = parse_vs_title(title)
        if teams is None:
            return None
        home, away = teams

        commence = self._parse_time(event.get("endDate") or event.get("startDate"))
        quotes = self._parse_h2h_markets(
            event.get("markets", []), home, away, clob_asks or {},
        )
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
    def _parse_token_ids(market: dict[str, Any]) -> list[str]:
        tids = market.get("clobTokenIds")
        if isinstance(tids, str):
            try:
                tids = json.loads(tids)
            except json.JSONDecodeError:
                return []
        if not isinstance(tids, list):
            return []
        return [str(t) for t in tids if t]

    @staticmethod
    def _parse_outcomes(market: dict[str, Any]) -> list[str]:
        outcomes = market.get("outcomes")
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                return []
        if not isinstance(outcomes, list):
            return []
        return [str(o) for o in outcomes]

    def _collect_yes_token_ids(self, events: list[dict[str, Any]]) -> list[str]:
        """收集需询价的 token：moneyline 取全部 outcome；其余 Yes/No 市场取 YES(=首个)"""
        ids: list[str] = []
        seen: set[str] = set()
        skip_types = {
            "spreads", "totals", "points", "rebounds", "assists",
            "soccer_exact_score", "soccer_total_goals",
        }
        for event in events:
            for market in event.get("markets") or []:
                smt = (market.get("sportsMarketType") or "").lower()
                if smt in skip_types:
                    continue
                tids = self._parse_token_ids(market)
                if not tids:
                    continue
                if smt == "moneyline":
                    wanted = tids
                else:
                    # 传统 Home/Draw/Away 独立 Yes/No 市场
                    group = (market.get("groupItemTitle") or "").strip()
                    if not group or self._is_non_h2h_market(group):
                        continue
                    wanted = tids[:1]
                for tid in wanted:
                    if tid not in seen:
                        seen.add(tid)
                        ids.append(tid)
        return ids

    def _fetch_clob_buy_prices(self, token_ids: list[str]) -> dict[str, float]:
        """
        从 CLOB 批量拉取可成交买入价（side=BUY = best ask）。
        文档: https://docs.polymarket.com/market-data/prices-order-books
        """
        result: dict[str, float] = {}
        if not token_ids:
            return result

        chunk = 100
        for i in range(0, len(token_ids), chunk):
            part = token_ids[i : i + chunk]
            payload = [{"token_id": tid, "side": "BUY"} for tid in part]
            try:
                resp = self.session.post(
                    f"{CLOB_URL}/prices",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                body = resp.json()
            except requests.RequestException as e:
                logger.warning("Polymarket CLOB /prices 失败: %s", e)
                continue

            if not isinstance(body, dict):
                continue
            for tid, sides in body.items():
                if not isinstance(sides, dict):
                    continue
                raw = sides.get("BUY")
                if raw is None:
                    continue
                try:
                    price = float(raw)
                except (TypeError, ValueError):
                    continue
                if 0 < price < 1 and MIN_EXECUTABLE_ASK <= price <= MAX_EXECUTABLE_ASK:
                    result[str(tid)] = price

        logger.info("Polymarket CLOB 买价: %d/%d", len(result), len(token_ids))
        return result

    @staticmethod
    def _is_main_match_event(title: str) -> bool:
        if " vs. " not in title and " vs " not in title.lower():
            return False
        skip_keywords = (
            "Props", "Halftime", "Half Time", "Exact Score",
            "First Team", "Second Half", "advance", "Winner",
            "Both Teams", "Total Goals", "Total Corners", "O/U", "Spread",
        )
        return not any(kw.lower() in title.lower() for kw in skip_keywords)

    def _parse_h2h_markets(
        self,
        markets: list[dict[str, Any]],
        home: str,
        away: str,
        clob_asks: dict[str, float],
    ) -> list[OddsQuote]:
        """解析胜平负/胜负盘；只用可成交买价（CLOB ask / Gamma bestAsk）"""
        home_norm = home.lower().strip()
        away_norm = away.lower().strip()

        moneyline_quotes: list[OddsQuote] = []
        group_quotes: list[OddsQuote] = []

        for market in markets:
            smt = (market.get("sportsMarketType") or "").lower()
            group_title = (market.get("groupItemTitle") or "").strip()

            # 二元 moneyline（outcomes=队名，无 groupItemTitle），如 MLB/ATP
            if smt == "moneyline" and not group_title:
                moneyline_quotes.extend(
                    self._parse_moneyline_market(market, home_norm, away_norm, clob_asks)
                )
                continue

            if smt in {
                "spreads", "totals", "points", "rebounds", "assists",
                "soccer_exact_score", "soccer_total_goals",
            }:
                continue

            # groupItemTitle 为空：若有 outcomes+token，按 moneyline 用 CLOB 询价（禁用 outcomePrices）
            if not group_title:
                if len(self._parse_outcomes(market)) >= 2 and self._parse_token_ids(market):
                    moneyline_quotes.extend(
                        self._parse_moneyline_market(
                            market, home_norm, away_norm, clob_asks,
                        )
                    )
                continue
            if self._is_non_h2h_market(group_title):
                continue

            outcome = self._map_outcome(group_title, home_norm, away_norm)
            if outcome is None:
                continue

            tids = self._parse_token_ids(market)
            ask = self._price_for_token(
                tids[0] if tids else None,
                clob_asks,
                fallback_ask=market.get("bestAsk"),
            )
            if ask is None:
                continue

            odds = polymarket_price_to_odds(ask)
            if odds <= 1.0:
                continue

            group_quotes.append(
                OddsQuote(
                    bookmaker="polymarket",
                    outcome=outcome,
                    odds=odds,
                    outcome_name=group_title,
                    platform="prediction",
                    raw_price=ask,
                )
            )

        # 新版体育盘优先用 moneyline；旧版 Home/Draw/Away 独立市场作回退
        chosen = moneyline_quotes or group_quotes
        return chosen if self._quotes_look_liquid(chosen) else []

    @staticmethod
    def _quotes_look_liquid(quotes: list[OddsQuote]) -> bool:
        """同一市场多腿 ask 之和过低 → 空盘假价，丢弃"""
        if len(quotes) < 2:
            return False
        prices = [q.raw_price for q in quotes if q.raw_price > 0]
        if len(prices) < 2:
            return True
        minimum = MIN_MONEYLINE_ASK_SUM if len(prices) == 2 else 0.92
        return sum(prices) >= minimum

    def _parse_moneyline_market(
        self,
        market: dict[str, Any],
        home_norm: str,
        away_norm: str,
        clob_asks: dict[str, float],
    ) -> list[OddsQuote]:
        """二元 moneyline：outcomes=[主,客] 对应两个 CLOB token"""
        outcomes = self._parse_outcomes(market)
        tids = self._parse_token_ids(market)
        if len(outcomes) < 2 or len(tids) < 2:
            return []

        quotes: list[OddsQuote] = []
        for idx, name in enumerate(outcomes):
            outcome = self._map_outcome(name, home_norm, away_norm)
            if outcome is None:
                continue
            # 市场级 bestAsk 通常只对应第一个 outcome，仅作首腿弱回退
            fallback = market.get("bestAsk") if idx == 0 else None
            ask = self._price_for_token(tids[idx], clob_asks, fallback_ask=fallback)
            if ask is None:
                continue
            odds = polymarket_price_to_odds(ask)
            if odds <= 1.0:
                continue
            quotes.append(
                OddsQuote(
                    bookmaker="polymarket",
                    outcome=outcome,
                    odds=odds,
                    outcome_name=name,
                    platform="prediction",
                    raw_price=ask,
                )
            )

        # 两边都有价时，ask 之和过低说明盘口无深度（假套利）
        if len(quotes) >= 2:
            ask_sum = sum(q.raw_price for q in quotes)
            if ask_sum < MIN_MONEYLINE_ASK_SUM:
                return []
        return quotes

    @staticmethod
    def _price_for_token(
        token_id: str | None,
        clob_asks: dict[str, float],
        fallback_ask: Any = None,
    ) -> float | None:
        """优先 CLOB best ask；否则 Gamma bestAsk。不用 outcomePrices。"""
        price: float | None = None
        if token_id and token_id in clob_asks:
            price = clob_asks[token_id]
        elif fallback_ask is not None:
            try:
                price = float(fallback_ask)
            except (TypeError, ValueError):
                return None
        if price is None:
            return None
        if not (MIN_EXECUTABLE_ASK <= price <= MAX_EXECUTABLE_ASK):
            return None
        return price

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
