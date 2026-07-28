"""套利扫描器：多平台拉取 → 合并 → 检测套利 → 输出提醒"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .arbitrage import scan_matches
from .kalshi import KalshiClient
from .models import ArbitrageOpportunity, MatchOdds, OddsQuote
from .notify_feishu import notify_new_opportunities
from .odds_api import fetch_all_odds, parse_api_keys
from .polymarket import PolymarketClient
from .team_matcher import merge_matches

logger = logging.getLogger(__name__)


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


class ArbitrageScanner:
    """跨平台胜平负套利扫描器"""

    def __init__(
        self,
        config: dict[str, Any],
        api_keys: list[str] | None = None,
        total_stake: float = 10000.0,
        max_arb_index: float = 0.98,
        min_profit_pct: float = 0.0,
        on_opportunity: Callable[[ArbitrageOpportunity], None] | None = None,
    ):
        self.config = config
        self.api_keys = api_keys or []
        self.total_stake = total_stake
        self.max_arb_index = max_arb_index
        self.min_profit_pct = min_profit_pct
        self.on_opportunity = on_opportunity or self._default_alert
        self._sportsbooks_cache: list[MatchOdds] = []
        self._last_sportsbooks_fetch: float = 0
        self._sportsbooks_cache_sec = float(config.get("sportsbooks_cache_sec", 432000))
        self._cache_file = Path("data") / "sportsbooks_cache.json"
        self._load_cache_from_disk()

    def run_once(self) -> tuple[list[ArbitrageOpportunity], list[MatchOdds]]:
        """执行一次完整扫描，返回 (套利机会, 合并后的所有比赛)"""
        sources = self.config.get("sources", {})
        all_match_groups: list[list[MatchOdds]] = []

        # 1. 博彩公司 (The Odds API)
        if sources.get("sportsbooks", True) and self.api_keys:
            sports = self.config.get("sports", [])
            regions = self.config.get("regions", ["eu"])
            markets = self.config.get("markets", ["h2h"])
            bookmakers = self.config.get("bookmakers")

            now = time.time()
            if (now - self._last_sportsbooks_fetch) >= self._sportsbooks_cache_sec:
                logger.info("拉取博彩公司赔率 (%d 个联赛，%d 个 API Key)...",
                            len(sports), len(self.api_keys))
                sb_matches = fetch_all_odds(
                    self.api_keys, sports, regions, markets, bookmakers,
                )
                self._sportsbooks_cache = sb_matches
                self._last_sportsbooks_fetch = now
                self._save_cache_to_disk()
                logger.info("博彩公司: %d 场比赛（已刷新）", len(sb_matches))
            else:
                sb_matches = self._sportsbooks_cache
                remaining = int(self._sportsbooks_cache_sec - (now - self._last_sportsbooks_fetch))
                logger.info("博彩公司: %d 场比赛（缓存，距下次刷新 %ds）", len(sb_matches), remaining)
            all_match_groups.append(sb_matches)

        # 2. Polymarket
        if sources.get("polymarket", True):
            pm_config = sources.get("polymarket_leagues", ["fifwc", "epl", "ucl"])
            logger.info("拉取 Polymarket (%s)...", pm_config)
            pm_client = PolymarketClient()
            pm_matches = pm_client.fetch_soccer_matches(pm_config)
            logger.info("Polymarket: %d 场比赛", len(pm_matches))
            all_match_groups.append(pm_matches)

        # 3. Kalshi
        if sources.get("kalshi", True):
            kalshi_config = sources.get("kalshi_leagues", ["worldcup", "epl"])
            logger.info("拉取 Kalshi (%s)...", kalshi_config)
            kalshi_client = KalshiClient()
            kalshi_matches = kalshi_client.fetch_soccer_matches(kalshi_config)
            logger.info("Kalshi: %d 场比赛", len(kalshi_matches))
            all_match_groups.append(kalshi_matches)

        if not all_match_groups:
            logger.warning("未启用任何数据源")
            return [], []

        # 4. 跨平台合并
        merged = merge_matches(all_match_groups)
        logger.info("合并后共 %d 场独立比赛", len(merged))

        # 5. 过滤已开赛
        now = datetime.now(timezone.utc)
        upcoming = [m for m in merged if m.commence_time > now]
        logger.info("未开赛: %d 场", len(upcoming))

        # 6. 套利检测
        opportunities = scan_matches(
            upcoming,
            total_stake=self.total_stake,
            max_arb_index=self.max_arb_index,
            min_profit_pct=self.min_profit_pct,
        )

        if opportunities:
            logger.info("发现 %d 个套利机会", len(opportunities))
            for opp in opportunities:
                self.on_opportunity(opp)
        else:
            logger.info("未发现符合条件的套利机会")

        # 与上次扫描对比，仅对新机会推送飞书（未配置 webhook 时仅更新去重基线）
        notify_new_opportunities(opportunities)

        return opportunities, merged

    @staticmethod
    def _default_alert(opp: ArbitrageOpportunity) -> None:
        print("\n" + "=" * 60)
        print(opp.summary())
        print("=" * 60)

    def _load_cache_from_disk(self) -> None:
        if not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            self._last_sportsbooks_fetch = float(data.get("last_fetch", 0))
            self._sportsbooks_cache = [
                MatchOdds(
                    sport=m["sport"],
                    league=m["league"],
                    home_team=m["home_team"],
                    away_team=m["away_team"],
                    commence_time=datetime.fromisoformat(m["commence_time"]),
                    quotes=[OddsQuote(**q) for q in m.get("quotes", [])],
                )
                for m in data.get("matches", [])
            ]
            logger.info("已加载博彩公司缓存: %d 场比赛，距上次 %ds",
                        len(self._sportsbooks_cache),
                        int(time.time() - self._last_sportsbooks_fetch))
        except Exception as e:
            logger.warning("加载博彩缓存失败: %s", e)
            self._sportsbooks_cache = []
            self._last_sportsbooks_fetch = 0

    def _save_cache_to_disk(self) -> None:
        from dataclasses import asdict
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_fetch": self._last_sportsbooks_fetch,
                "cache_sec": self._sportsbooks_cache_sec,
                "matches": [
                    {
                        "sport": m.sport,
                        "league": m.league,
                        "home_team": m.home_team,
                        "away_team": m.away_team,
                        "commence_time": m.commence_time.isoformat(),
                        "quotes": [asdict(q) for q in m.quotes],
                    }
                    for m in self._sportsbooks_cache
                ],
            }
            self._cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("保存博彩缓存失败: %s", e)

    def save_report(
        self,
        opportunities: list[ArbitrageOpportunity],
        output_path: str | Path,
    ) -> None:
        """将套利结果保存为 JSON"""
        data = []
        for opp in opportunities:
            data.append(
                {
                    "home_team": opp.match.home_team,
                    "away_team": opp.match.away_team,
                    "league": opp.match.league,
                    "commence_time": opp.match.commence_time.isoformat(),
                    "arb_index": round(opp.arb_index, 6),
                    "implied_sum": round(opp.implied_sum, 6),
                    "profit_pct": round(opp.profit_pct, 4),
                    "total_stake": opp.total_stake,
                    "guaranteed_payout": round(opp.guaranteed_payout, 2),
                    "profit": round(opp.profit, 2),
                    "legs": [
                        {
                            "outcome": leg.outcome,
                            "outcome_name": leg.outcome_name,
                            "bookmaker": leg.bookmaker,
                            "platform": leg.platform,
                            "odds": leg.odds,
                            "raw_price": leg.raw_price,
                            "stake": round(leg.stake, 2),
                            "payout": round(leg.payout, 2),
                        }
                        for leg in opp.legs
                    ],
                }
            )

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("报告已保存: %s", path)
