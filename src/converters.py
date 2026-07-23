"""预测市场价格 → 十进制赔率转换"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

CHINA_TZ = timezone(timedelta(hours=8), "CST")


def utc_to_china_str(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """UTC datetime 转为中国时间 (UTC+8) 字符串"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TZ).strftime(fmt)


def polymarket_price_to_odds(price: float) -> float:
    """
    Polymarket YES 买入价 (0~1) → 十进制赔率。

    买入价 p，胜出得 $1/份 → 赔率 = 1/p
    """
    if price <= 0 or price >= 1:
        return 0.0
    return 1.0 / price


def kalshi_price_to_odds(price_cents: int | float) -> float:
    """
    Kalshi YES 价格 (0~100 美分) → 十进制赔率。

    52¢ → 赔率 = 100/52 ≈ 1.92
    """
    if price_cents <= 0 or price_cents >= 100:
        return 0.0
    return 100.0 / float(price_cents)
