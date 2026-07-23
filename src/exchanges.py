"""博彩交易所定义与佣金配置"""

from __future__ import annotations

from typing import Any

# The Odds API 支持的交易所 bookmaker key
EXCHANGE_BOOKMAKERS: frozenset[str] = frozenset({
    "betfair_ex_uk",
    "betfair_ex_eu",
    "betfair_ex_au",
    "smarkets",
    "matchbook",
})

# 默认佣金：对净盈利收取的百分比
DEFAULT_EXCHANGE_COMMISSION: dict[str, float] = {
    "betfair_ex_uk": 5.0,   # 活跃用户可降至 ~2%
    "betfair_ex_eu": 5.0,
    "betfair_ex_au": 5.0,
    "smarkets": 2.0,
    "matchbook": 1.0,       # 部分市场有封顶
    "betdaq": 2.0,          # 促销期可能 0%，Odds API 暂不支持
}


def is_exchange(bookmaker: str) -> bool:
    """判断是否为博彩交易所（非固定赔率庄家）"""
    return bookmaker in EXCHANGE_BOOKMAKERS or bookmaker.startswith("betfair_ex_")


def get_commission(bookmaker: str, config: dict[str, Any] | None = None) -> float:
    """获取交易所佣金率（净盈利 %）"""
    if config:
        exchanges = config.get("exchanges", {})
        entry = exchanges.get(bookmaker, {})
        if "commission_pct" in entry:
            return float(entry["commission_pct"])

    return DEFAULT_EXCHANGE_COMMISSION.get(bookmaker, 5.0)


def effective_exchange_odds(odds: float, commission_pct: float) -> float:
    """
    将交易所 back 赔率折算为扣佣后的有效赔率。

    佣金按净盈利收取：effective = 1 + (odds - 1) × (1 - commission%)
    """
    if odds <= 1.0:
        return odds
    return 1.0 + (odds - 1.0) * (1.0 - commission_pct / 100.0)
