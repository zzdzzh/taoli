"""模拟盘：虚拟下单、结算、盈亏统计"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .arbitrage import calc_arb_index, calc_profit_pct, find_best_quotes, infer_outcomes
from .exchanges import effective_exchange_odds, get_commission
from .models import ArbitrageLeg, ArbitrageOpportunity, MatchOdds

# 各平台默认手续费（占投注额 %；交易所盈利佣金见 exchanges.py）
# 费率依据：盈利佣金 / 充提成本（充提并入保守估算或见 config 注释）
DEFAULT_FEE_RATES: dict[str, float] = {
    # 类型默认
    "sportsbook": 0.0,      # 博彩公司盈利佣金 0%，水位已含在赔率
    "prediction": 2.0,      # 预测市场交易费保守取上限
    # 博彩公司
    "pinnacle": 0.0,        # 盈利 0%；提现约 0~1%（未按笔扣，见 fx/人工）
    "bet365": 0.0,
    "onexbet": 0.0,         # 1xBet
    "unibet": 0.0,
    "unibet_uk": 0.0,
    "williamhill": 0.0,
    # 预测市场（交易费约 0%~2%，保守按 2%）
    "polymarket": 2.0,
    "kalshi": 1.0,          # 表未列；保留既有估算
    "myriad": 2.0,          # Myriad 交易费保守按 2%
}


@dataclass
class PaperLeg:
    """模拟盘单条腿（已扣滑点）"""

    outcome: str
    outcome_name: str
    bookmaker: str
    platform: str
    odds: float           # 原始赔率
    exec_odds: float      # 执行赔率（含滑点）
    stake: float
    fee: float            # 手续费
    expected_payout: float


@dataclass
class PaperPosition:
    """模拟盘持仓"""

    id: str
    home_team: str
    away_team: str
    league: str
    commence_time: str
    arb_index: float
    theory_profit_pct: float
    total_stake: float
    total_fees: float
    legs: list[PaperLeg]
    status: str = "open"          # open / settled
    result_outcome: str = ""      # home / draw / away
    gross_payout: float = 0.0
    net_profit: float = 0.0
    opened_at: str = ""
    settled_at: str = ""


@dataclass
class PaperPortfolio:
    """模拟盘账户"""

    initial_bankroll: float
    bankroll: float
    slippage_pct: float = 0.5       # 赔率滑点 %
    fx_loss_pct: float = 0.3        # 跨平台汇率损耗 %
    positions: list[PaperPosition] = field(default_factory=list)
    created_at: str = ""

    @property
    def total_pnl(self) -> float:
        return self.bankroll - self.initial_bankroll

    @property
    def roi_pct(self) -> float:
        if self.initial_bankroll <= 0:
            return 0.0
        return self.total_pnl / self.initial_bankroll * 100.0

    @property
    def open_count(self) -> int:
        return sum(1 for p in self.positions if p.status == "open")

    @property
    def settled_count(self) -> int:
        return sum(1 for p in self.positions if p.status == "settled")

    def win_rate(self) -> float:
        settled = [p for p in self.positions if p.status == "settled"]
        if not settled:
            return 0.0
        wins = sum(1 for p in settled if p.net_profit > 0)
        return wins / len(settled) * 100.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fee_rate(leg: ArbitrageLeg) -> float:
    """按平台/庄家取投注额手续费%；交易所盈利佣金已折入有效赔率。"""
    if leg.platform == "exchange":
        return 0.0
    if leg.bookmaker in DEFAULT_FEE_RATES:
        return DEFAULT_FEE_RATES[leg.bookmaker]
    if leg.platform == "prediction":
        return DEFAULT_FEE_RATES["prediction"]
    return DEFAULT_FEE_RATES.get("sportsbook", 0.0)


def _exec_odds(leg: ArbitrageLeg, slippage_pct: float) -> float:
    """计算含滑点与佣金的执行赔率"""
    if leg.platform == "exchange":
        comm = get_commission(leg.bookmaker)
        odds = effective_exchange_odds(leg.odds, comm)
    else:
        odds = leg.odds
    return odds * (1.0 - slippage_pct / 100.0)


def apply_execution_costs(
    opp: ArbitrageOpportunity,
    slippage_pct: float = 0.5,
    fx_loss_pct: float = 0.3,
) -> tuple[list[PaperLeg], float, float]:
    """
    将理论套利转为可执行模拟单，扣除滑点和手续费。

    返回: (legs, total_cost, adjusted_arb_index)
    """
    paper_legs: list[PaperLeg] = []
    total_fees = 0.0

    for leg in opp.legs:
        exec_odds = _exec_odds(leg, slippage_pct)
        fee = leg.stake * _fee_rate(leg) / 100.0
        total_fees += fee

        paper_legs.append(
            PaperLeg(
                outcome=leg.outcome,
                outcome_name=leg.outcome_name,
                bookmaker=leg.bookmaker,
                platform=leg.platform,
                odds=leg.odds,
                exec_odds=exec_odds,
                stake=leg.stake,
                fee=fee,
                expected_payout=leg.stake * exec_odds,
            )
        )

    # 跨平台汇率损耗（按总投入计）
    fx_cost = opp.total_stake * fx_loss_pct / 100.0
    total_fees += fx_cost

    # 用执行赔率重算套利指数
    adjusted_s = sum(1.0 / lg.exec_odds for lg in paper_legs)

    return paper_legs, total_fees, adjusted_s


class PaperTradeEngine:
    """模拟盘引擎"""

    def __init__(
        self,
        initial_bankroll: float = 100000.0,
        stake_per_trade: float = 10000.0,
        slippage_pct: float = 0.5,
        fx_loss_pct: float = 0.3,
        state_path: str | Path = "data/paper_state.json",
    ):
        self.stake_per_trade = stake_per_trade
        self.slippage_pct = slippage_pct
        self.fx_loss_pct = fx_loss_pct
        self.state_path = Path(state_path)
        self.portfolio = self._load_or_create(initial_bankroll)

    def _load_or_create(self, initial_bankroll: float) -> PaperPortfolio:
        if self.state_path.exists():
            with self.state_path.open(encoding="utf-8") as f:
                data = json.load(f)
            positions = []
            for p in data.get("positions", []):
                legs = [PaperLeg(**lg) for lg in p.pop("legs")]
                positions.append(PaperPosition(**p, legs=legs))
            return PaperPortfolio(
                initial_bankroll=data["initial_bankroll"],
                bankroll=data["bankroll"],
                slippage_pct=data.get("slippage_pct", self.slippage_pct),
                fx_loss_pct=data.get("fx_loss_pct", self.fx_loss_pct),
                positions=positions,
                created_at=data.get("created_at", _now_iso()),
            )

        return PaperPortfolio(
            initial_bankroll=initial_bankroll,
            bankroll=initial_bankroll,
            slippage_pct=self.slippage_pct,
            fx_loss_pct=self.fx_loss_pct,
            created_at=_now_iso(),
        )

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "initial_bankroll": self.portfolio.initial_bankroll,
            "bankroll": self.portfolio.bankroll,
            "slippage_pct": self.portfolio.slippage_pct,
            "fx_loss_pct": self.portfolio.fx_loss_pct,
            "created_at": self.portfolio.created_at,
            "positions": [
                {**asdict(p), "legs": [asdict(lg) for lg in p.legs]}
                for p in self.portfolio.positions
            ],
        }
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def reset(self, initial_bankroll: float | None = None) -> None:
        br = initial_bankroll or self.portfolio.initial_bankroll
        self.portfolio = PaperPortfolio(
            initial_bankroll=br,
            bankroll=br,
            slippage_pct=self.slippage_pct,
            fx_loss_pct=self.fx_loss_pct,
            created_at=_now_iso(),
        )
        self.save()

    def _match_key(self, home: str, away: str, commence: datetime) -> str:
        return f"{home}|{away}|{commence.strftime('%Y-%m-%d')}"

    def has_open_position(self, opp: ArbitrageOpportunity) -> bool:
        key = self._match_key(
            opp.match.home_team,
            opp.match.away_team,
            opp.match.commence_time,
        )
        for p in self.portfolio.positions:
            if p.status != "open":
                continue
            pkey = self._match_key(p.home_team, p.away_team,
                                   datetime.fromisoformat(p.commence_time))
            if pkey == key:
                return True
        return False

    def try_open(self, opp: ArbitrageOpportunity) -> Optional[PaperPosition]:
        """尝试开仓，资金不足或已有持仓则跳过"""
        if self.has_open_position(opp):
            return None

        paper_legs, total_fees, adjusted_s = apply_execution_costs(
            opp, self.slippage_pct, self.fx_loss_pct,
        )

        total_cost = opp.total_stake + total_fees
        if total_cost > self.portfolio.bankroll:
            return None

        # 扣费后仍须满足安全边际
        if adjusted_s >= 1.0:
            return None

        self.portfolio.bankroll -= total_cost

        pos = PaperPosition(
            id=str(uuid.uuid4())[:8],
            home_team=opp.match.home_team,
            away_team=opp.match.away_team,
            league=opp.match.league,
            commence_time=opp.match.commence_time.isoformat(),
            arb_index=opp.arb_index,
            theory_profit_pct=opp.profit_pct,
            total_stake=opp.total_stake,
            total_fees=total_fees,
            legs=paper_legs,
            opened_at=_now_iso(),
        )
        self.portfolio.positions.append(pos)
        self.save()
        return pos

    def settle(self, position_id: str, result_outcome: str) -> PaperPosition:
        """按比赛结果结算"""
        pos = next(p for p in self.portfolio.positions if p.id == position_id)
        if pos.status == "settled":
            return pos

        winning = next(lg for lg in pos.legs if lg.outcome == result_outcome)
        gross_payout = winning.stake * winning.exec_odds
        net_profit = gross_payout - pos.total_stake - pos.total_fees

        pos.status = "settled"
        pos.result_outcome = result_outcome
        pos.gross_payout = gross_payout
        pos.net_profit = net_profit
        pos.settled_at = _now_iso()

        self.portfolio.bankroll += gross_payout
        self.save()
        return pos

    def settle_by_match(
        self,
        home: str,
        away: str,
        result_outcome: str,
        date: str | None = None,
    ) -> list[PaperPosition]:
        """按队名结算所有匹配持仓"""
        settled = []
        for pos in self.portfolio.positions:
            if pos.status != "open":
                continue
            if pos.home_team != home or pos.away_team != away:
                continue
            if date and not pos.commence_time.startswith(date):
                continue
            settled.append(self.settle(pos.id, result_outcome))
        return settled

    def report(self) -> str:
        """生成模拟盘报告"""
        p = self.portfolio
        lines = [
            "=" * 60,
            "模拟盘报告",
            "=" * 60,
            f"初始资金: {p.initial_bankroll:,.2f}",
            f"当前资金: {p.bankroll:,.2f}",
            f"总盈亏:   {p.total_pnl:+,.2f} ({p.roi_pct:+.2f}%)",
            f"持仓:     开仓 {p.open_count} | 已结算 {p.settled_count}",
            f"胜率:     {p.win_rate():.1f}%",
            f"滑点:     {p.slippage_pct}% | 汇率损耗: {p.fx_loss_pct}%",
        ]

        open_pos = [x for x in p.positions if x.status == "open"]
        if open_pos:
            lines.append("\n--- 未结算持仓 ---")
            for pos in open_pos:
                lines.append(
                    f"  [{pos.id}] {pos.home_team} vs {pos.away_team} "
                    f"S={pos.arb_index:.4f} 投入={pos.total_stake:.0f} "
                    f"理论收益={pos.theory_profit_pct:.2f}%"
                )

        settled = [x for x in p.positions if x.status == "settled"]
        if settled:
            lines.append("\n--- 已结算记录 ---")
            for pos in settled[-10:]:
                lines.append(
                    f"  [{pos.id}] {pos.home_team} vs {pos.away_team} "
                    f"结果={pos.result_outcome} "
                    f"净利={pos.net_profit:+,.2f}"
                )

        return "\n".join(lines)


def simulate_scenario(
    match: MatchOdds,
    result_outcome: str,
    stake: float = 10000.0,
    max_arb_index: float = 0.98,
    slippage_pct: float = 0.5,
    fx_loss_pct: float = 0.3,
) -> dict[str, Any]:
    """
    单次场景模拟：检测套利 → 模拟下单 → 按结果结算。

    用于回测验证「扣费后是否仍赚钱」。
    """
    from .arbitrage import detect_arbitrage

    opp = detect_arbitrage(match, stake, max_arb_index)
    if opp is None:
        best = find_best_quotes(match)
        s = calc_arb_index(best, infer_outcomes(match))
        return {
            "tradeable": False,
            "arb_index": s,
            "reason": (f"S={s:.4f}，不满足开仓条件" if s is not None else "没有平台互异的完整推荐组合"),
        }

    paper_legs, total_fees, adjusted_s = apply_execution_costs(
        opp, slippage_pct, fx_loss_pct,
    )
    winning = next(lg for lg in paper_legs if lg.outcome == result_outcome)
    gross_payout = winning.stake * winning.exec_odds
    net_profit = gross_payout - opp.total_stake - total_fees
    theory_profit = opp.profit

    return {
        "tradeable": True,
        "match": f"{match.home_team} vs {match.away_team}",
        "arb_index": opp.arb_index,
        "adjusted_s": adjusted_s,
        "theory_profit_pct": opp.profit_pct,
        "theory_profit": theory_profit,
        "total_fees": total_fees,
        "result": result_outcome,
        "gross_payout": gross_payout,
        "net_profit": net_profit,
        "net_profit_pct": net_profit / opp.total_stake * 100,
        "profitable": net_profit > 0,
        "legs": [
            {
                "outcome": lg.outcome,
                "bookmaker": lg.bookmaker,
                "odds": lg.odds,
                "exec_odds": round(lg.exec_odds, 4),
                "stake": round(lg.stake, 2),
                "fee": round(lg.fee, 2),
            }
            for lg in paper_legs
        ],
    }
