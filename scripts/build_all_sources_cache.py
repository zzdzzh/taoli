"""按当前代码逻辑刷新全源缓存：Odds API（多 Key）+ Polymarket + Kalshi。

写入:
  data/sportsbooks_cache.json
  data/all_sources_cache.json
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.kalshi import KalshiClient  # noqa: E402
from src.models import MatchOdds, OddsQuote  # noqa: E402
from src.odds_api import fetch_all_odds, parse_api_keys  # noqa: E402
from src.polymarket import PolymarketClient  # noqa: E402
from src.team_matcher import merge_matches  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_all_sources")

PRED_BOOKS = frozenset({"polymarket", "kalshi"})


def _serialize(matches: list[MatchOdds]) -> list[dict]:
    return [
        {
            "sport": m.sport,
            "league": m.league,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "commence_time": m.commence_time.isoformat(),
            "quotes": [asdict(q) for q in m.quotes],
        }
        for m in matches
    ]


def _tag_prediction(matches: list[MatchOdds]) -> list[MatchOdds]:
    for m in matches:
        for q in m.quotes:
            if q.bookmaker in PRED_BOOKS:
                q.platform = "prediction"
    return matches


def _save_sportsbooks(matches: list[MatchOdds], last_fetch: float) -> Path:
    path = ROOT / "data" / "sportsbooks_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_fetch": last_fetch,
        "cache_sec": 432000,
        "matches": _serialize(matches),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _probe(url: str, timeout: float = 5.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code < 500
    except requests.RequestException:
        return False


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    sources = cfg.get("sources", {})
    api_keys = parse_api_keys(os.getenv("ODDS_API_KEY", ""))
    if not api_keys:
        raise SystemExit("缺少 ODDS_API_KEY（支持逗号分隔多 Key）")

    sports = cfg.get("sports", [])
    regions = cfg.get("regions", ["eu", "uk"])
    markets = cfg.get("markets", ["h2h"])
    bookmakers = cfg.get("bookmakers")

    logger.info(
        "刷新 Odds API 博彩盘: %d 联赛, %d Key, bookmakers=%s",
        len(sports),
        len(api_keys),
        bookmakers,
    )
    sb_matches = fetch_all_odds(api_keys, sports, regions, markets, bookmakers)
    now = time.time()
    sb_path = _save_sportsbooks(sb_matches, now)
    logger.info("Sportsbooks: %d 场 → %s", len(sb_matches), sb_path.name)

    groups: list[list[MatchOdds]] = [sb_matches]
    pm_matches: list[MatchOdds] = []
    kalshi_matches: list[MatchOdds] = []

    if sources.get("polymarket", True):
        pm_leagues = sources.get("polymarket_leagues", ["epl", "ucl"])
        if _probe("https://gamma-api.polymarket.com/sports"):
            logger.info("直连 Polymarket (%s)...", pm_leagues)
            pm_matches = _tag_prediction(
                PolymarketClient(timeout=20).fetch_soccer_matches(pm_leagues)
            )
            logger.info("Polymarket: %d 场", len(pm_matches))
            groups.append(pm_matches)
        else:
            logger.warning("Polymarket 直连不可用，跳过")

    if sources.get("kalshi", True):
        kalshi_leagues = sources.get("kalshi_leagues", ["epl", "ucl"])
        if _probe("https://api.elections.kalshi.com/trade-api/v2/exchange/status"):
            logger.info("直连 Kalshi (%s)...", kalshi_leagues)
            kalshi_matches = _tag_prediction(
                KalshiClient(timeout=20).fetch_soccer_matches(kalshi_leagues)
            )
            logger.info("Kalshi: %d 场", len(kalshi_matches))
            groups.append(kalshi_matches)
        else:
            logger.warning("Kalshi 直连不可用，跳过")

    # 直连不足时，用 Odds API us_ex 补 polymarket/kalshi
    if (sources.get("polymarket", True) and not pm_matches) or (
        sources.get("kalshi", True) and not kalshi_matches
    ):
        logger.info("预测市场直连不足，回退 Odds API us_ex...")
        pred = fetch_all_odds(
            api_keys,
            sports,
            ["us_ex"],
            markets,
            ["polymarket", "kalshi"],
        )
        pred = _tag_prediction([m for m in pred if m.quotes])
        logger.info("Odds API us_ex 预测盘: %d 场有报价", len(pred))
        if pred:
            groups.append(pred)

    merged = merge_matches(groups)
    bk = Counter()
    plat = Counter()
    for m in merged:
        for q in m.quotes:
            bk[q.bookmaker] += 1
            plat[q.platform] += 1

    print("平台报价条数:")
    for k, v in bk.most_common():
        print(f"  {k}: {v}")
    print("类型:", dict(plat))

    out = {
        "built_at": now,
        "sportsbooks_last_fetch": now,
        "sources": {
            "sportsbooks": len(sb_matches),
            "polymarket": len(pm_matches),
            "kalshi": len(kalshi_matches),
            "merged": len(merged),
        },
        "bookmakers": dict(bk),
        "matches": _serialize(merged),
    }
    out_path = ROOT / "data" / "all_sources_cache.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {out_path}")


if __name__ == "__main__":
    main()
