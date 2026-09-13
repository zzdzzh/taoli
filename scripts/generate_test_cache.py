"""生成合成测试缓存数据，用于验证 analyze_cache_arb.py 流程。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate_test_cache() -> dict:
    """生成包含理论套利和非套利场景的测试数据。"""
    now = datetime.now(timezone.utc)
    
    matches = [
        # 场景1: 理论套利（S < 1.0）
        {
            "sport": "soccer_epl",
            "league": "EPL",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "commence_time": (now + timedelta(hours=24)).isoformat(),
            "quotes": [
                {
                    "bookmaker": "pinnacle",
                    "platform": "sportsbook",
                    "outcome": "home",
                    "outcome_name": "Arsenal",
                    "odds": 2.15,
                    "last_update": now.isoformat(),
                },
                {
                    "bookmaker": "polymarket",
                    "platform": "prediction",
                    "outcome": "draw",
                    "outcome_name": "Draw",
                    "odds": 3.8,
                    "last_update": now.isoformat(),
                },
                {
                    "bookmaker": "kalshi",
                    "platform": "prediction",
                    "outcome": "away",
                    "outcome_name": "Chelsea",
                    "odds": 3.5,
                    "last_update": now.isoformat(),
                },
            ],
        },
        # 场景2: 交易所佣金后套利消失
        {
            "sport": "tennis_atp",
            "league": "ATP Wimbledon",
            "home_team": "Djokovic",
            "away_team": "Nadal",
            "commence_time": (now + timedelta(hours=48)).isoformat(),
            "quotes": [
                {
                    "bookmaker": "betfair_ex_uk",
                    "platform": "exchange",
                    "outcome": "home",
                    "outcome_name": "Djokovic",
                    "odds": 1.95,
                    "last_update": now.isoformat(),
                },
                {
                    "bookmaker": "smarkets",
                    "platform": "exchange",
                    "outcome": "away",
                    "outcome_name": "Nadal",
                    "odds": 2.05,
                    "last_update": now.isoformat(),
                },
            ],
        },
        # 场景3: 明显无套利
        {
            "sport": "basketball_nba",
            "league": "NBA",
            "home_team": "Lakers",
            "away_team": "Warriors",
            "commence_time": (now + timedelta(hours=72)).isoformat(),
            "quotes": [
                {
                    "bookmaker": "pinnacle",
                    "platform": "sportsbook",
                    "outcome": "home",
                    "outcome_name": "Lakers",
                    "odds": 1.85,
                    "last_update": now.isoformat(),
                },
                {
                    "bookmaker": "onexbet",
                    "platform": "sportsbook",
                    "outcome": "away",
                    "outcome_name": "Warriors",
                    "odds": 1.95,
                    "last_update": now.isoformat(),
                },
            ],
        },
        # 场景4: 小套利机会但需要多平台
        {
            "sport": "soccer_spain_la_liga",
            "league": "La Liga",
            "home_team": "Real Madrid",
            "away_team": "Barcelona",
            "commence_time": (now + timedelta(hours=96)).isoformat(),
            "quotes": [
                {
                    "bookmaker": "pinnacle",
                    "platform": "sportsbook",
                    "outcome": "home",
                    "outcome_name": "Real Madrid",
                    "odds": 2.45,
                    "last_update": now.isoformat(),
                },
                {
                    "bookmaker": "polymarket",
                    "platform": "prediction",
                    "outcome": "draw",
                    "outcome_name": "Draw",
                    "odds": 3.9,
                    "last_update": now.isoformat(),
                },
                {
                    "bookmaker": "betfair_ex_uk",
                    "platform": "exchange",
                    "outcome": "away",
                    "outcome_name": "Barcelona",
                    "odds": 3.2,
                    "last_update": now.isoformat(),
                },
            ],
        },
    ]
    
    return {
        "built_at": now.isoformat(),
        "sources": {
            "sportsbook": 2,
            "prediction": 2,
            "exchange": 2,
        },
        "matches": matches,
    }


def main() -> None:
    """生成并保存测试缓存。"""
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    
    cache_data = generate_test_cache()
    cache_path = data_dir / "test_cache.json"
    
    cache_path.write_text(
        json.dumps(cache_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    print(f"✓ 测试缓存已生成: {cache_path}")
    print(f"  包含 {len(cache_data['matches'])} 场比赛")
    print(f"  场景: 理论套利、交易所佣金测试、无套利、小套利")
    print("\n运行分析:")
    print("  python scripts/analyze_cache_arb.py")


if __name__ == "__main__":
    main()
