"""The Odds API 数据拉取与标准化，支持多 API Key 自动轮换"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from .exchanges import is_exchange
from .models import MatchOdds, OddsQuote

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"

# API 返回的 outcome name 映射到 home/draw/away
DRAW_NAMES = {"draw", "tie", "x", "平", "平局"}


def parse_api_keys(keys_str: str) -> list[str]:
    """解析逗号分隔的 API Key 列表，过滤空值。"""
    keys = [k.strip() for k in keys_str.replace("，", ",").split(",")]
    return [k for k in keys if k and k != "your_api_key_here"]


class OddsAPIClient:
    """The Odds API 客户端，支持多 Key 自动轮换"""

    def __init__(self, api_keys: list[str], timeout: int = 30):
        if not api_keys:
            raise ValueError("至少需要一个 API Key")
        self.api_keys = api_keys
        self._key_index = 0
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def current_key(self) -> str:
        return self.api_keys[self._key_index]

    def _rotate_key(self) -> bool:
        """切换到下一个可用 Key，全部轮完则返回 False。"""
        if self._key_index + 1 >= len(self.api_keys):
            logger.warning("所有 API Key 均已耗尽配额")
            return False
        self._key_index += 1
        logger.info("切换到下一个 API Key (index=%d)", self._key_index)
        return True

    def _request(self, url: str, params: dict[str, Any]) -> requests.Response:
        """带 Key 轮换的 HTTP 请求"""
        for attempt in range(len(self.api_keys)):
            params["apiKey"] = self.current_key
            resp = self.session.get(url, params=params, timeout=self.timeout)

            if resp.status_code == 401:
                remaining = resp.headers.get("x-requests-remaining", "0")
                logger.warning(
                    "API Key %d 配额已耗尽 (剩余 %s)，尝试轮换",
                    self._key_index, remaining,
                )
                if not self._rotate_key():
                    resp.raise_for_status()
                continue

            if resp.status_code == 429:
                logger.warning("API Key %d 请求过频，尝试轮换", self._key_index)
                if not self._rotate_key():
                    resp.raise_for_status()
                continue

            resp.raise_for_status()
            return resp

        raise RuntimeError("所有 API Key 均已失效")

    def get_sports(self) -> list[dict[str, Any]]:
        """获取可用运动/联赛列表"""
        resp = self._request(f"{BASE_URL}/sports", {})
        return resp.json()

    def get_odds(
        self,
        sport: str,
        regions: list[str],
        markets: list[str],
        bookmakers: list[str] | None = None,
    ) -> list[MatchOdds]:
        """
        拉取指定联赛的胜平负赔率。

        sport: 如 soccer_epl
        regions: 如 ["eu", "uk"]
        markets: 如 ["h2h"]
        bookmakers: 可选，限制博彩公司
        """
        url = f"{BASE_URL}/sports/{sport}/odds"
        params: dict[str, Any] = {
            "apiKey": self.current_key,
            "regions": ",".join(regions),
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)

        resp = self._request(url, params)

        remaining = resp.headers.get("x-requests-remaining")
        used = resp.headers.get("x-requests-used")
        if remaining is not None:
            logger.info(
                "Odds API 配额 (Key %d): 剩余 %s, 已用 %s",
                self._key_index, remaining, used,
            )

        return [self._parse_event(sport, event) for event in resp.json()]

    def _parse_event(self, sport: str, event: dict[str, Any]) -> MatchOdds:
        home = event["home_team"]
        away = event["away_team"]
        commence = datetime.fromisoformat(
            event["commence_time"].replace("Z", "+00:00")
        )

        quotes: list[OddsQuote] = []

        for bookmaker in event.get("bookmakers", []):
            bk_key = bookmaker.get("key", "unknown")
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = float(outcome["price"])
                    outcome_key = self._map_outcome(name, home, away)
                    if outcome_key is None:
                        continue
                    quotes.append(
                        OddsQuote(
                            bookmaker=bk_key,
                            outcome=outcome_key,
                            odds=price,
                            outcome_name=name,
                            platform="exchange" if is_exchange(bk_key) else "sportsbook",
                        )
                    )

        return MatchOdds(
            sport=sport,
            league=event.get("sport_title", sport),
            home_team=home,
            away_team=away,
            commence_time=commence,
            quotes=quotes,
        )

    @staticmethod
    def _map_outcome(name: str, home: str, away: str) -> str | None:
        lower = name.strip().lower()
        if lower in DRAW_NAMES:
            return "draw"
        if name == home:
            return "home"
        if name == away:
            return "away"
        return None


def fetch_all_odds(
    api_keys: list[str],
    sports: list[str],
    regions: list[str],
    markets: list[str],
    bookmakers: list[str] | None = None,
) -> list[MatchOdds]:
    """拉取多个联赛的全部赔率，支持多 Key 自动轮换"""
    client = OddsAPIClient(api_keys)
    all_matches: list[MatchOdds] = []

    for sport in sports:
        try:
            matches = client.get_odds(sport, regions, markets, bookmakers)
            logger.info("联赛 %s: 获取 %d 场比赛", sport, len(matches))
            all_matches.extend(matches)
        except requests.HTTPError as e:
            logger.warning("联赛 %s 拉取失败: %s", sport, e)
        except requests.RequestException as e:
            logger.warning("联赛 %s 网络错误: %s", sport, e)

    return all_matches
