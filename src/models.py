"""数据模型"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .converters import utc_to_china_str


@dataclass
class OddsQuote:
    """单条赔率报价"""

    bookmaker: str
    outcome: str  # home / draw / away
    odds: float
    outcome_name: str = ""  # 显示用，如 "France"
    platform: str = "sportsbook"  # sportsbook / exchange / prediction
    raw_price: float = 0.0  # 原始价格（预测市场概率）


@dataclass
class MatchOdds:
    """一场比赛在各平台的赔率"""

    sport: str
    league: str
    home_team: str
    away_team: str
    commence_time: datetime
    quotes: list[OddsQuote] = field(default_factory=list)


@dataclass
class ArbitrageLeg:
    """套利组合中的一条腿"""

    outcome: str
    outcome_name: str
    bookmaker: str
    odds: float
    stake: float
    payout: float
    platform: str = "sportsbook"
    raw_price: float = 0.0


@dataclass
class ArbitrageOpportunity:
    """套利机会"""

    match: MatchOdds
    legs: list[ArbitrageLeg]
    total_stake: float
    guaranteed_payout: float
    profit: float
    profit_pct: float
    implied_sum: float  # 套利指数 S = 1/o1 + 1/o2 + 1/o3

    @property
    def arb_index(self) -> float:
        return self.implied_sum

    def summary(self) -> str:
        lines = [
            f"【套利】{self.match.home_team} vs {self.match.away_team}",
            f"  联赛: {self.match.league} | 开赛: {utc_to_china_str(self.match.commence_time)}",
            f"  套利指数 S: {self.arb_index:.4f} | 理论收益: {self.profit_pct:.2f}%",
            f"  总投入: {self.total_stake:.2f} → 保底回报: {self.guaranteed_payout:.2f} (利润 {self.profit:.2f})",
            f"  ※ 理论值，未扣手续费/汇率/限额/滑点",
        ]
        for leg in self.legs:
            if leg.platform == "prediction":
                platform_tag = " [预测市场]"
            elif leg.platform == "exchange":
                platform_tag = " [交易所]"
            else:
                platform_tag = ""
            lines.append(
                f"  · {leg.outcome_name} ({leg.outcome}) @ {leg.bookmaker}{platform_tag}: "
                f"赔率 {leg.odds:.2f} | 投注 {leg.stake:.2f} | 回报 {leg.payout:.2f}"
            )
        return "\n".join(lines)
