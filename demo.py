"""
演示模式：跨平台套利计算验证。

无需 API Key，直接运行:
    python demo.py
"""

import sys
from datetime import datetime, timezone

from src.arbitrage import (
    calc_arb_index,
    calc_profit_pct,
    detect_arbitrage,
    find_best_quotes,
)
from src.converters import polymarket_price_to_odds
from src.models import MatchOdds, OddsQuote
from src.team_matcher import merge_matches

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def build_sportsbook_match() -> MatchOdds:
    """博彩公司赔率：法国 vs 西班牙"""
    commence = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    return MatchOdds(
        sport="soccer_fifa_world_cup",
        league="世界杯半决赛",
        home_team="France",
        away_team="Spain",
        commence_time=commence,
        quotes=[
            OddsQuote("pinnacle", "home", 2.60, "France"),
            OddsQuote("pinnacle", "draw", 3.50, "Draw"),
            OddsQuote("pinnacle", "away", 3.00, "Spain"),
            OddsQuote("bet365", "home", 2.40, "France"),
            OddsQuote("bet365", "draw", 3.80, "Draw"),
            OddsQuote("bet365", "away", 3.10, "Spain"),
            OddsQuote("onexbet", "home", 2.55, "France"),
            OddsQuote("onexbet", "draw", 4.20, "Draw"),
            OddsQuote("onexbet", "away", 2.90, "Spain"),
        ],
    )


def build_polymarket_match() -> MatchOdds:
    """Polymarket 真实价格（2026-07-13 快照）"""
    commence = datetime(2026, 7, 14, 19, 0, tzinfo=timezone.utc)
    # bestAsk: France 0.4125, Draw 0.30, Spain 0.2925
    return MatchOdds(
        sport="polymarket_fifwc",
        league="fifwc",
        home_team="France",
        away_team="Spain",
        commence_time=commence,
        quotes=[
            OddsQuote("polymarket", "home", polymarket_price_to_odds(0.4125), "France",
                      platform="prediction", raw_price=0.4125),
            OddsQuote("polymarket", "draw", polymarket_price_to_odds(0.30), "Draw",
                      platform="prediction", raw_price=0.30),
            OddsQuote("polymarket", "away", polymarket_price_to_odds(0.2925), "Spain",
                      platform="prediction", raw_price=0.2925),
        ],
    )


def build_kalshi_match() -> MatchOdds:
    """Kalshi 模拟价格：法国 vs 西班牙"""
    commence = datetime(2026, 7, 14, 19, 0, tzinfo=timezone.utc)
    # 模拟: France 38¢, Draw 30¢, Spain 29¢
    from src.converters import kalshi_price_to_odds
    return MatchOdds(
        sport="kalshi_worldcup",
        league="worldcup",
        home_team="France",
        away_team="Spain",
        commence_time=commence,
        quotes=[
            OddsQuote("kalshi", "home", kalshi_price_to_odds(38), "France",
                      platform="prediction", raw_price=38),
            OddsQuote("kalshi", "draw", kalshi_price_to_odds(30), "Draw",
                      platform="prediction", raw_price=30),
            OddsQuote("kalshi", "away", kalshi_price_to_odds(29), "Spain",
                      platform="prediction", raw_price=29),
        ],
    )


def main():
    total_stake = 10000.0

    print("=" * 60)
    print("演示 1：纯博彩公司套利（法国 vs 西班牙）")
    print("=" * 60)
    sb = build_sportsbook_match()
    best_sb = find_best_quotes(sb)
    s = calc_arb_index(best_sb)
    print(f"套利指数 S = {s:.4f} | 理论收益 = {calc_profit_pct(s):.2f}%")
    opp = detect_arbitrage(sb, total_stake, max_arb_index=0.98)
    if opp:
        print(opp.summary())

    print("\n" + "=" * 60)
    print("演示 2：跨平台套利（博彩 + Polymarket + Kalshi）")
    print("=" * 60)

    merged = merge_matches([
        [build_sportsbook_match()],
        [build_polymarket_match()],
        [build_kalshi_match()],
    ])
    match = merged[0]
    print(f"\n合并后比赛: {match.home_team} vs {match.away_team}")
    print(f"共 {len(match.quotes)} 条报价来自 {len(set(q.bookmaker for q in match.quotes))} 个平台")

    best = find_best_quotes(match)
    print("\n各结果最佳赔率（跨平台）:")
    for outcome, q in best.items():
        tag = " [预测市场]" if q.platform == "prediction" else ""
        print(f"  {q.outcome_name:10s} ({outcome}): {q.bookmaker:12s}{tag} @ {q.odds:.2f}")

    implied = calc_arb_index(best)
    print(f"\n套利指数 S = {implied:.4f} | 理论收益 = {calc_profit_pct(implied):.2f}%")

    cross_opp = detect_arbitrage(match, total_stake, max_arb_index=0.98)
    if cross_opp:
        print("\n→ 发现跨平台套利！\n")
        print(cross_opp.summary())
    else:
        print("\n→ 无跨平台套利")

    print("\n" + "-" * 60)
    print("价格转换参考:")
    print(f"  Polymarket 0.30 (平局 ask) → 赔率 {polymarket_price_to_odds(0.30):.2f}")
    from src.converters import kalshi_price_to_odds
    print(f"  Kalshi 30¢ (平局) → 赔率 {kalshi_price_to_odds(30):.2f}")


if __name__ == "__main__":
    main()
