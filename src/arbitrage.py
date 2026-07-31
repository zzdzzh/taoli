"""胜平负 / 胜负套利计算核心逻辑"""

from __future__ import annotations

from typing import Optional

from .models import ArbitrageLeg, ArbitrageOpportunity, MatchOdds, OddsQuote

# 足球胜平负
OUTCOMES_3WAY = ("home", "draw", "away")
# 篮球、网球等胜负盘
OUTCOMES_2WAY = ("home", "away")
# 向后兼容
OUTCOMES = OUTCOMES_3WAY

VALID_OUTCOMES = frozenset({"home", "draw", "away"})

# The Odds API 运动前缀 → 通常为二项盘
TWO_WAY_SPORT_PREFIXES = (
    "basketball_",
    "tennis_",
    "baseball_",
    "americanfootball_",
    "icehockey_",
    "mma_",
    "boxing_",
)

# Polymarket / Kalshi 联赛代码 → 二项盘
TWO_WAY_PLATFORM_CODES = frozenset({
    "nba", "wnba", "atp", "wta", "euroleague", "cwbb", "ncaab",
})


def infer_outcomes(match: MatchOdds) -> tuple[str, ...]:
    """
    推断比赛市场类型：胜平负 (3-way) 或胜负 (2-way)。

    优先根据已有报价判断，其次根据运动/联赛代码推断。
    """
    quote_outcomes = {q.outcome for q in match.quotes if q.outcome in VALID_OUTCOMES}
    if "draw" in quote_outcomes:
        return OUTCOMES_3WAY
    if "home" in quote_outcomes and "away" in quote_outcomes:
        if not quote_outcomes & {"draw"}:
            return OUTCOMES_2WAY

    sport = match.sport.lower()
    if any(sport.startswith(p) for p in TWO_WAY_SPORT_PREFIXES):
        return OUTCOMES_2WAY

    for prefix in ("polymarket_", "kalshi_"):
        if sport.startswith(prefix):
            code = sport[len(prefix):]
            if code in TWO_WAY_PLATFORM_CODES:
                return OUTCOMES_2WAY

    return OUTCOMES_3WAY


def find_best_quotes(match: MatchOdds) -> dict[str, OddsQuote]:
    """
    对每个结果，在所有平台中选取最高赔率。

    返回: { "home": OddsQuote, "draw": OddsQuote, "away": OddsQuote }
    若某结果无报价则不在字典中。
    """
    best: dict[str, OddsQuote] = {}

    for quote in match.quotes:
        if quote.outcome not in VALID_OUTCOMES:
            continue
        current = best.get(quote.outcome)
        if current is None or quote.odds > current.odds:
            best[quote.outcome] = quote

    return best


def calc_arb_index(
    best: dict[str, OddsQuote],
    outcomes: tuple[str, ...] | None = None,
) -> Optional[float]:
    """
    套利指数 S = sum(1/odds_i)

    S < 1 表示理论套利；专业系统通常要求 S < 0.98（至少 2% 安全边际）。
    必须所有结果都有报价才返回数值，否则返回 None。
    """
    if outcomes is None:
        if "draw" in best:
            outcomes = OUTCOMES_3WAY
        elif "home" in best and "away" in best:
            outcomes = OUTCOMES_2WAY
        else:
            return None

    if not all(o in best for o in outcomes):
        return None

    return sum(1.0 / best[o].odds for o in outcomes)


def calc_arb_index_for_match(match: MatchOdds) -> Optional[float]:
    """根据比赛推断市场类型并计算套利指数"""
    return calc_arb_index(find_best_quotes(match), infer_outcomes(match))


def calc_implied_sum(best: dict[str, OddsQuote]) -> Optional[float]:
    """calc_arb_index 的别名，保持向后兼容"""
    return calc_arb_index(best)


def calc_profit_pct(arb_index: float) -> float:
    """
    理论套利收益率（%）= (1/S - 1) × 100

    未扣除手续费、汇率损失、限额和赔率滑点。
    """
    if arb_index <= 0:
        return 0.0
    return (1.0 / arb_index - 1.0) * 100.0


def calc_stakes(
    best: dict[str, OddsQuote],
    total_stake: float,
    outcomes: tuple[str, ...],
) -> dict[str, float]:
    """
    按套利公式分配投注金额。

    stake_i = total_stake * (1/odds_i) / sum(1/odds_j)
    """
    implied = {o: 1.0 / best[o].odds for o in outcomes}
    total_implied = sum(implied.values())

    return {o: total_stake * implied[o] / total_implied for o in outcomes}


def detect_arbitrage(
    match: MatchOdds,
    total_stake: float = 10000.0,
    max_arb_index: float = 0.98,
    min_profit_pct: float = 0.0,
) -> Optional[ArbitrageOpportunity]:
    """
    检测单场比赛是否存在套利机会（支持胜平负与胜负盘）。

    条件: S = sum(1/odds_i) < max_arb_index
    默认 max_arb_index=0.98，即至少留 2% 以上安全边际。
    """
    outcomes = infer_outcomes(match)
    best = find_best_quotes(match)
    arb_index = calc_arb_index(best, outcomes)
    if arb_index is None:
        return None

    if arb_index >= max_arb_index:
        return None

    profit_pct = calc_profit_pct(arb_index)
    if profit_pct < min_profit_pct:
        return None

    stakes = calc_stakes(best, total_stake, outcomes)
    guaranteed_payout = total_stake / arb_index
    profit = guaranteed_payout - total_stake

    legs: list[ArbitrageLeg] = []
    for outcome in outcomes:
        q = best[outcome]
        stake = stakes[outcome]
        legs.append(
            ArbitrageLeg(
                outcome=outcome,
                outcome_name=q.outcome_name or outcome,
                bookmaker=q.bookmaker,
                odds=q.odds,
                stake=stake,
                payout=stake * q.odds,
                platform=q.platform,
                raw_price=q.raw_price,
            )
        )

    # 套利必须跨平台：全部腿在同一庄家（如双边都 Polymarket）视为无效
    if len({leg.bookmaker for leg in legs}) < 2:
        return None

    return ArbitrageOpportunity(
        match=match,
        legs=legs,
        total_stake=total_stake,
        guaranteed_payout=guaranteed_payout,
        profit=profit,
        profit_pct=profit_pct,
        implied_sum=arb_index,
    )


def scan_matches(
    matches: list[MatchOdds],
    total_stake: float = 10000.0,
    max_arb_index: float = 0.98,
    min_profit_pct: float = 0.0,
) -> list[ArbitrageOpportunity]:
    """批量扫描多场比赛，返回所有套利机会（按收益率降序）。"""
    opportunities: list[ArbitrageOpportunity] = []

    for match in matches:
        opp = detect_arbitrage(match, total_stake, max_arb_index, min_profit_pct)
        if opp is not None:
            opportunities.append(opp)

    opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
    return opportunities
