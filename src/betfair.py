"""Betfair Exchange API 直连拉取 Match Odds（back 最优价）

文档: https://developer.betfair.com/exchange-api/
需在开发者后台申请 App Key，并配置账号登录凭证。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .models import MatchOdds, OddsQuote
from .team_matcher import parse_vs_title

logger = logging.getLogger(__name__)

LOGIN_URL = "https://identitysso.betfair.com/api/login"
CERT_LOGIN_URL = "https://identitysso-cert.betfair.com/api/certlogin"
KEEPALIVE_URL = "https://identitysso.betfair.com/api/keepAlive"
BETTING_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"

# 官方 eventTypeId
EVENT_TYPE_IDS: dict[str, str] = {
    "soccer": "1",
    "football": "1",
    "tennis": "2",
    "basketball": "7522",
}

DRAW_NAMES = frozenset({
    "the draw", "draw", "tie", "x", "empate", "unentschieden", "平", "平局",
})

BOOKMAKER = "betfair_ex_uk"


class BetfairClient:
    """Betfair Exchange Betting API 客户端（只读盘口，不下单）"""

    def __init__(
        self,
        username: str = "",
        password: str = "",
        app_key: str = "",
        certs_dir: str = "",
        timeout: int = 30,
    ):
        self.username = (username or os.getenv("BETFAIR_USERNAME", "")).strip()
        self.password = (password or os.getenv("BETFAIR_PASSWORD", "")).strip()
        self.app_key = (app_key or os.getenv("BETFAIR_APP_KEY", "")).strip()
        self.certs_dir = (certs_dir or os.getenv("BETFAIR_CERTS_DIR", "")).strip()
        self.timeout = timeout
        self.session = requests.Session()
        self._session_token = ""

    def credentials_ready(self) -> bool:
        return bool(self.username and self.password and self.app_key)

    def fetch_soccer_matches(
        self,
        event_types: list[str] | None = None,
        days_ahead: int = 7,
        max_per_type: int = 200,
    ) -> list[MatchOdds]:
        """拉取 Match Odds（足球胜平负 / 篮球网球胜负）"""
        if not self.credentials_ready():
            logger.warning(
                "未配置 BETFAIR_USERNAME / BETFAIR_PASSWORD / BETFAIR_APP_KEY，跳过 Betfair"
            )
            return []

        types = event_types or ["soccer", "tennis", "basketball"]
        try:
            self._ensure_login()
        except Exception as e:
            logger.warning("Betfair 登录失败: %s", e)
            return []

        all_matches: list[MatchOdds] = []
        for et in types:
            et_id = EVENT_TYPE_IDS.get(et.lower().strip(), et.strip())
            if not et_id.isdigit():
                logger.warning("未知 Betfair event type: %s", et)
                continue
            try:
                catalogues = self._list_match_odds_catalogue(et_id, days_ahead, max_per_type)
                if not catalogues:
                    logger.info("Betfair %s: 0 场", et)
                    continue
                books = self._list_market_books([c["marketId"] for c in catalogues])
                book_map = {b["marketId"]: b for b in books if b.get("marketId")}
                parsed = []
                for cat in catalogues:
                    mid = cat.get("marketId")
                    m = self._parse_market(cat, book_map.get(mid or ""), et.lower())
                    if m is not None:
                        parsed.append(m)
                logger.info("Betfair %s: %d 场比赛", et, len(parsed))
                all_matches.extend(parsed)
            except Exception as e:
                logger.warning("Betfair %s 拉取失败: %s", et, e)

        return all_matches

    def _ensure_login(self) -> None:
        if self._session_token and self._keepalive():
            return
        if self.certs_dir:
            self._login_cert()
        else:
            self._login_interactive()

    def _login_interactive(self) -> None:
        resp = self.session.post(
            LOGIN_URL,
            data={"username": self.username, "password": self.password},
            headers={
                "X-Application": self.app_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "SUCCESS" or not body.get("token"):
            raise RuntimeError(f"Betfair 登录失败: {body}")
        self._session_token = body["token"]

    def _login_cert(self) -> None:
        cert_file = os.path.join(self.certs_dir, "client-2048.crt")
        key_file = os.path.join(self.certs_dir, "client-2048.key")
        if not (os.path.isfile(cert_file) and os.path.isfile(key_file)):
            raise FileNotFoundError(
                f"证书目录缺少 client-2048.crt / client-2048.key: {self.certs_dir}"
            )
        resp = self.session.post(
            CERT_LOGIN_URL,
            data={"username": self.username, "password": self.password},
            headers={
                "X-Application": self.app_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            cert=(cert_file, key_file),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        # certlogin 字段多为 loginStatus / sessionToken
        token = body.get("sessionToken") or body.get("token")
        status = body.get("loginStatus") or body.get("status")
        if status not in ("SUCCESS",) or not token:
            raise RuntimeError(f"Betfair 证书登录失败: {body}")
        self._session_token = token

    def _keepalive(self) -> bool:
        try:
            resp = self.session.get(
                KEEPALIVE_URL,
                headers={
                    "X-Application": self.app_key,
                    "X-Authentication": self._session_token,
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return False
            return resp.json().get("status") == "SUCCESS"
        except requests.RequestException:
            return False

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": f"SportsAPING/v1.0/{method}",
            "params": params,
            "id": 1,
        }
        resp = self.session.post(
            BETTING_URL,
            json=payload,
            headers={
                "X-Application": self.app_key,
                "X-Authentication": self._session_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"Betfair RPC {method} 错误: {body['error']}")
        return body.get("result")

    def _list_match_odds_catalogue(
        self,
        event_type_id: str,
        days_ahead: int,
        max_results: int,
    ) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=max(1, days_ahead))
        result = self._rpc(
            "listMarketCatalogue",
            {
                "filter": {
                    "eventTypeIds": [event_type_id],
                    "marketTypeCodes": ["MATCH_ODDS"],
                    "marketStartTime": {
                        "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                },
                "maxResults": min(max_results, 1000),
                "marketProjection": [
                    "COMPETITION",
                    "EVENT",
                    "EVENT_TYPE",
                    "MARKET_START_TIME",
                    "RUNNER_DESCRIPTION",
                ],
                "sort": "FIRST_TO_START",
            },
        )
        return result or []

    def _list_market_books(self, market_ids: list[str]) -> list[dict[str, Any]]:
        books: list[dict[str, Any]] = []
        chunk = 40
        for i in range(0, len(market_ids), chunk):
            part = market_ids[i : i + chunk]
            result = self._rpc(
                "listMarketBook",
                {
                    "marketIds": part,
                    "priceProjection": {
                        "priceData": ["EX_BEST_OFFERS"],
                        "virtualise": True,
                    },
                },
            )
            if result:
                books.extend(result)
        return books

    def _parse_market(
        self,
        catalogue: dict[str, Any],
        book: dict[str, Any] | None,
        event_type: str,
    ) -> MatchOdds | None:
        if not book or book.get("status") != "OPEN":
            return None

        event = catalogue.get("event") or {}
        event_name = (event.get("name") or "").strip()
        teams = parse_vs_title(event_name)
        if teams is None:
            return None
        home, away = teams

        competition = (catalogue.get("competition") or {}).get("name") or ""
        league = competition or (catalogue.get("eventType") or {}).get("name") or event_type
        commence = self._parse_time(
            catalogue.get("marketStartTime") or event.get("openDate")
        )

        runners_meta = {
            r.get("selectionId"): r for r in (catalogue.get("runners") or [])
        }
        quotes: list[OddsQuote] = []
        for runner in book.get("runners") or []:
            if runner.get("status") != "ACTIVE":
                continue
            sid = runner.get("selectionId")
            meta = runners_meta.get(sid) or {}
            name = (meta.get("runnerName") or "").strip()
            if not name:
                continue
            outcome = self._map_outcome(name, home, away)
            if outcome is None:
                continue
            price = self._best_back(runner)
            if price is None or price <= 1.0:
                continue
            quotes.append(
                OddsQuote(
                    bookmaker=BOOKMAKER,
                    outcome=outcome,
                    odds=float(price),
                    outcome_name=name,
                    platform="exchange",
                )
            )

        if len({q.outcome for q in quotes}) < 2:
            return None

        return MatchOdds(
            sport=f"betfair_{event_type}",
            league=league,
            home_team=home,
            away_team=away,
            commence_time=commence,
            quotes=quotes,
        )

    @staticmethod
    def _best_back(runner: dict[str, Any]) -> float | None:
        ex = runner.get("ex") or {}
        backs = ex.get("availableToBack") or []
        if not backs:
            # 无挂单时偶发有 lastPriceTraded
            last = runner.get("lastPriceTraded")
            try:
                return float(last) if last is not None else None
            except (TypeError, ValueError):
                return None
        try:
            return float(backs[0]["price"])
        except (KeyError, TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def _map_outcome(name: str, home: str, away: str) -> str | None:
        lower = name.lower().strip()
        if lower in DRAW_NAMES:
            return "draw"
        home_n = home.lower().strip()
        away_n = away.lower().strip()
        if lower == home_n or home_n in lower or lower in home_n:
            return "home"
        if lower == away_n or away_n in lower or lower in away_n:
            return "away"
        return None

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc)
