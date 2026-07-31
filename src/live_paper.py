"""实时模拟盘：拉取真实数据 → 模拟买卖 → 生成报告"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .arbitrage import calc_arb_index, calc_profit_pct, detect_arbitrage, find_best_quotes, infer_outcomes
from .converters import utc_to_china_str
from .models import ArbitrageOpportunity, MatchOdds, OddsQuote
from .odds_api import fetch_all_odds, parse_api_keys
from .paper_trade import PaperTradeEngine
from .results import auto_settle_open_positions

logger = logging.getLogger(__name__)


@dataclass
class MatchSnapshot:
    """单场比赛实时快照"""

    home_team: str
    away_team: str
    league: str
    commence_time: str
    quote_count: int
    platform_count: int
    arb_index: float | None
    profit_pct: float
    best_home: dict[str, Any] = field(default_factory=dict)
    best_draw: dict[str, Any] = field(default_factory=dict)
    best_away: dict[str, Any] = field(default_factory=dict)
    tradeable: bool = False


@dataclass
class LivePaperReport:
    """一次实时模拟盘运行报告"""

    run_at: str
    data_sources: list[str]
    matches_scanned: int
    matches_upcoming: int
    opportunities_found: int
    positions_opened: int
    positions_settled: int
    initial_bankroll: float
    final_bankroll: float
    total_pnl: float
    roi_pct: float
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    settled_positions: list[dict[str, Any]] = field(default_factory=list)
    new_opportunities: list[dict[str, Any]] = field(default_factory=list)
    top_near_arb: list[dict[str, Any]] = field(default_factory=list)
    scan_duration_sec: float = 0.0
    data_freshness: dict[str, str] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [
            "# 实时模拟盘报告",
            "",
            f"**运行时间:** {self.run_at}",
            f"**扫描耗时:** {self.scan_duration_sec:.1f} 秒",
            f"**数据源:** {', '.join(self.data_sources)}",
            "",
            "## 扫描概况",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 扫描比赛数 | {self.matches_scanned} |",
            f"| 未开赛比赛 | {self.matches_upcoming} |",
            f"| 发现套利机会 (S<0.98) | {self.opportunities_found} |",
            f"| 本次开仓 | {self.positions_opened} |",
            f"| 本次结算 | {self.positions_settled} |",
            "",
            "## 账户盈亏",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 初始资金 | {self.initial_bankroll:,.2f} |",
            f"| 当前资金 | {self.final_bankroll:,.2f} |",
            f"| 总盈亏 | {self.total_pnl:+,.2f} |",
            f"| 收益率 | {self.roi_pct:+.2f}% |",
            "",
        ]

        if self.new_opportunities:
            lines += ["## 本次发现的套利机会", ""]
            for opp in self.new_opportunities:
                lines.append(f"### {opp['home_team']} vs {opp['away_team']}")
                lines.append(f"- 联赛: {opp['league']}")
                lines.append(f"- 开赛: {opp['commence_time']}")
                lines.append(f"- 套利指数 S: **{opp['arb_index']:.4f}**")
                lines.append(f"- 理论收益: **{opp['profit_pct']:.2f}%**")
                lines.append(f"- 是否开仓: {'是' if opp.get('opened') else '否'}")
                lines.append("")
                lines.append("| 结果 | 平台 | 赔率 | 投注 |")
                lines.append("|------|------|------|------|")
                for leg in opp.get("legs", []):
                    plat = leg.get("platform", "sportsbook")
                    if plat == "prediction":
                        tag = "预测"
                    elif plat == "exchange":
                        tag = "交易所"
                    else:
                        tag = "博彩"
                    lines.append(
                        f"| {leg['outcome_name']} | {leg['bookmaker']} ({tag}) "
                        f"| {leg['odds']:.2f} | {leg['stake']:.2f} |"
                    )
                lines.append("")

        if self.top_near_arb:
            lines += [
                "## 最接近套利的市场 (Top 10)",
                "",
                "即使 S ≥ 0.98 也列出，便于观察市场状态。",
                "",
                "| 比赛 | 联赛 | S | 理论收益% | 主胜最佳 | 平局最佳 | 客胜最佳 |",
                "|------|------|---|-----------|---------|---------|---------|",
            ]
            for m in self.top_near_arb[:10]:
                lines.append(
                    f"| {m['home_team']} vs {m['away_team']} | {m['league']} "
                    f"| {m['arb_index']:.4f} | {m['profit_pct']:.2f} "
                    f"| {m['best_home'].get('bookmaker', '-')} @{m['best_home'].get('odds', 0):.2f} "
                    f"| {m['best_draw'].get('bookmaker', '-')} @{m['best_draw'].get('odds', 0):.2f} "
                    f"| {m['best_away'].get('bookmaker', '-')} @{m['best_away'].get('odds', 0):.2f} |"
                )
            lines.append("")

        if self.open_positions:
            lines += ["## 未结算持仓", ""]
            for p in self.open_positions:
                lines.append(
                    f"- **{p['home_team']} vs {p['away_team']}** "
                    f"S={p['arb_index']:.4f} 投入={p['total_stake']:.0f} "
                    f"理论收益={p['theory_profit_pct']:.2f}%"
                )
            lines.append("")

        if self.settled_positions:
            lines += ["## 已结算记录", ""]
            lines += [
                "| 比赛 | 结果 | 净利 | 开仓时间 |",
                "|------|------|------|---------|",
            ]
            for p in self.settled_positions:
                lines.append(
                    f"| {p['home_team']} vs {p['away_team']} "
                    f"| {p['result_outcome']} | {p['net_profit']:+,.2f} "
                    f"| {p['opened_at'][:19]} |"
                )
            lines.append("")

        lines += [
            "## 数据新鲜度",
            "",
            f"| 数据源 | 最后刷新 |",
            f"|--------|---------|",
        ]
        for source, status in self.data_freshness.items():
            lines.append(f"| {source} | {status} |")
        lines.append("")

        lines += [
            "## 监控平台与扣费假设",
            "",
            "| 平台 | 类型 | 扣费（模拟盘） |",
            "|------|------|----------------|",
            "| Pinnacle | 博彩 | 盈利佣金 0% |",
            "| 1xBet (onexbet) | 博彩 | 盈利佣金 0% |",
            "| Unibet UK | 博彩 | 盈利佣金 0% |",
            "| William Hill | 博彩 | 盈利佣金 0% |",
            "| Betfair Exchange | 交易所 | 净盈利佣金 5%（表内 2%~5% 取保守） |",
            "| Smarkets | 交易所 | 净盈利佣金 2% |",
            "| Matchbook | 交易所 | 净盈利佣金 2%（表内 1%~2% 取保守） |",
            "| Polymarket | 预测 | 交易费 2%（表内 0%~2% 取保守） |",
            "| Kalshi | 预测 | 交易费约 1% |",
            "| Myriad | 预测 | 交易费约 2%（保守） |",
            "",
            "## 说明",
            "",
            "- 赔率为扫描时刻各平台 API 快照，非逐笔推送",
            "- 已扣：滑点 0.5%、预测市场手续费（Polymarket/Myriad 2% / Kalshi 1%）、"
            "交易所净盈利佣金、跨平台汇率损耗 0.3%",
            "- 博彩公司盈利佣金按 0%；充提成本未按笔建模",
            "- 仅 S < 0.98 时模拟开仓",
            "- 网页每 60 秒自动刷新；数据来自 `reports/latest.md`",
            "",
        ]
        return "\n".join(lines)


def _quote_summary(q) -> dict[str, Any]:
    if q is None:
        return {}
    return {
        "bookmaker": q.bookmaker,
        "odds": round(q.odds, 4),
        "platform": q.platform,
    }


def analyze_matches(
    matches: list[MatchOdds],
    max_arb_index: float = 0.98,
) -> list[MatchSnapshot]:
    """分析所有比赛的实时套利指数"""
    snapshots: list[MatchSnapshot] = []

    for match in matches:
        outcomes = infer_outcomes(match)
        best = find_best_quotes(match)
        s = calc_arb_index(best, outcomes)
        if s is None:
            continue

        platforms = {q.bookmaker for q in match.quotes}
        snapshots.append(
            MatchSnapshot(
                home_team=match.home_team,
                away_team=match.away_team,
                league=match.league,
                commence_time=match.commence_time.isoformat(),
                quote_count=len(match.quotes),
                platform_count=len(platforms),
                arb_index=s,
                profit_pct=calc_profit_pct(s) if s < 1 else 0.0,
                best_home=_quote_summary(best.get("home")),
                best_draw=_quote_summary(best.get("draw")),
                best_away=_quote_summary(best.get("away")),
                tradeable=s < max_arb_index,
            )
        )

    snapshots.sort(key=lambda x: x.arb_index or 999)
    return snapshots


class LivePaperRunner:
    """实时模拟盘运行器"""

    def __init__(
        self,
        config: dict[str, Any],
        api_keys: list[str] | None = None,
        bankroll: float = 100000.0,
        stake: float = 10000.0,
        max_arb_index: float = 0.98,
        slippage_pct: float = 0.5,
        fx_loss_pct: float = 0.3,
        state_path: str | Path = "data/paper_state.json",
    ):
        self.config = config
        self.api_keys = api_keys or []
        self.max_arb_index = max_arb_index
        self.engine = PaperTradeEngine(
            initial_bankroll=bankroll,
            stake_per_trade=stake,
            slippage_pct=slippage_pct,
            fx_loss_pct=fx_loss_pct,
            state_path=state_path,
        )
        self._opened_this_run: list[dict[str, Any]] = []
        self._opportunities_this_run: list[ArbitrageOpportunity] = []
        self._sportsbooks_cache: list[MatchOdds] = []
        self._last_sportsbooks_fetch: float = 0
        self._sportsbooks_cache_sec = float(config.get("sportsbooks_cache_sec", 432000))
        self._sportsbooks_fresh_this_run: bool = True
        self._cache_file = Path("data") / "sportsbooks_cache.json"
        self._load_cache_from_disk()

    def _collect_matches(self) -> tuple[list[MatchOdds], list[str], bool]:
        """拉取并合并所有平台实时数据，返回 (比赛列表, 数据源名称, 博彩是否新鲜)"""
        from datetime import datetime, timezone

        from .betfair import BetfairClient
        from .kalshi import KalshiClient
        from .myriad import MyriadClient
        from .polymarket import PolymarketClient
        from .team_matcher import merge_matches

        sources = self.config.get("sources", {})
        groups: list[list[MatchOdds]] = []
        source_names: list[str] = []
        sportsbooks_fresh = False

        if sources.get("sportsbooks", True) and self.api_keys:
            sports = self.config.get("sports", [])
            regions = self.config.get("regions", ["eu"])
            markets = self.config.get("markets", ["h2h"])
            bookmakers = self.config.get("bookmakers")

            now = time.time()
            if (now - self._last_sportsbooks_fetch) >= self._sportsbooks_cache_sec:
                groups.append(fetch_all_odds(
                    self.api_keys, sports, regions, markets, bookmakers,
                ))
                self._sportsbooks_cache = groups[-1]
                self._last_sportsbooks_fetch = now
                sportsbooks_fresh = True
                self._save_cache_to_disk()
                logger.info("博彩公司数据已刷新")
            else:
                groups.append(self._sportsbooks_cache)
                remaining = int(self._sportsbooks_cache_sec - (now - self._last_sportsbooks_fetch))
                logger.info("博彩公司数据使用缓存，距下次刷新 %ds", remaining)
            source_names.append("博彩公司(The Odds API)")

        if sources.get("polymarket", True):
            pm_leagues = sources.get("polymarket_leagues", ["fifwc", "epl", "ucl"])
            groups.append(PolymarketClient().fetch_soccer_matches(pm_leagues))
            source_names.append("Polymarket")

        if sources.get("kalshi", True):
            kalshi_leagues = sources.get("kalshi_leagues", ["worldcup", "epl"])
            groups.append(KalshiClient().fetch_soccer_matches(kalshi_leagues))
            source_names.append("Kalshi")

        if sources.get("myriad", True):
            myriad_topics = sources.get("myriad_topics", ["Sports"])
            groups.append(MyriadClient().fetch_soccer_matches(myriad_topics))
            source_names.append("Myriad")

        if sources.get("betfair", True):
            bf_types = sources.get("betfair_event_types", ["soccer", "tennis", "basketball"])
            bf_days = int(sources.get("betfair_days_ahead", 7))
            groups.append(BetfairClient().fetch_soccer_matches(bf_types, days_ahead=bf_days))
            source_names.append("Betfair")

        merged = merge_matches(groups)
        now = datetime.now(timezone.utc)
        upcoming = [m for m in merged if m.commence_time > now]
        return upcoming, source_names, sportsbooks_fresh

    def run_once(self) -> LivePaperReport:
        """执行一轮：拉实时数据 → 分析 → 模拟开仓 → 结算 → 报告"""
        t0 = time.time()
        bankroll_before = self.engine.portfolio.bankroll
        settled_before = self.engine.portfolio.settled_count

        self._opened_this_run = []
        self._opportunities_this_run = []

        upcoming, source_names, sportsbooks_fresh = self._collect_matches()
        self._sportsbooks_fresh_this_run = sportsbooks_fresh
        snapshots = analyze_matches(upcoming, self.max_arb_index)

        def on_opp(opp: ArbitrageOpportunity) -> None:
            self._opportunities_this_run.append(opp)
            pos = self.engine.try_open(opp)
            opp_data = {
                "home_team": opp.match.home_team,
                "away_team": opp.match.away_team,
                "league": opp.match.league,
                "commence_time": opp.match.commence_time.isoformat(),
                "arb_index": round(opp.arb_index, 6),
                "profit_pct": round(opp.profit_pct, 4),
                "opened": pos is not None,
                "legs": [
                    {
                        "outcome": leg.outcome,
                        "outcome_name": leg.outcome_name,
                        "bookmaker": leg.bookmaker,
                        "platform": leg.platform,
                        "odds": leg.odds,
                        "stake": round(leg.stake, 2),
                    }
                    for leg in opp.legs
                ],
            }
            if pos:
                opp_data["position_id"] = pos.id
                self._opened_this_run.append(opp_data)

        from .arbitrage import scan_matches

        opportunities = scan_matches(
            upcoming,
            total_stake=self.engine.stake_per_trade,
            max_arb_index=self.max_arb_index,
        )
        for opp in opportunities:
            on_opp(opp)

        from .notify_feishu import notify_new_opportunities

        pt = self.config.get("paper_trade") or {}
        notify_new_opportunities(
            opportunities,
            slippage_pct=float(pt.get("slippage_pct", self.engine.slippage_pct)),
            fx_loss_pct=float(pt.get("fx_loss_pct", self.engine.fx_loss_pct)),
        )

        settled_count = auto_settle_open_positions(self.engine)
        p = self.engine.portfolio

        near_arb = [
            {
                "home_team": s.home_team,
                "away_team": s.away_team,
                "league": s.league,
                "arb_index": s.arb_index,
                "profit_pct": s.profit_pct,
                "best_home": s.best_home,
                "best_draw": s.best_draw,
                "best_away": s.best_away,
                "tradeable": s.tradeable,
            }
            for s in snapshots
            if s.arb_index is not None
        ]

        report = LivePaperReport(
            run_at=utc_to_china_str(datetime.now(timezone.utc), "%Y-%m-%d %H:%M:%S CST"),
            data_sources=source_names,
            matches_scanned=len(upcoming),
            matches_upcoming=len(upcoming),
            opportunities_found=len(opportunities),
            positions_opened=len(self._opened_this_run),
            positions_settled=settled_count,
            initial_bankroll=p.initial_bankroll,
            final_bankroll=p.bankroll,
            total_pnl=p.total_pnl,
            roi_pct=p.roi_pct,
            open_positions=[
                {
                    "id": pos.id,
                    "home_team": pos.home_team,
                    "away_team": pos.away_team,
                    "arb_index": pos.arb_index,
                    "total_stake": pos.total_stake,
                    "theory_profit_pct": pos.theory_profit_pct,
                    "opened_at": pos.opened_at,
                }
                for pos in p.positions if pos.status == "open"
            ],
            settled_positions=[
                {
                    "home_team": pos.home_team,
                    "away_team": pos.away_team,
                    "result_outcome": pos.result_outcome,
                    "net_profit": pos.net_profit,
                    "opened_at": pos.opened_at,
                    "settled_at": pos.settled_at,
                }
                for pos in p.positions if pos.status == "settled"
            ],
            new_opportunities=self._opened_this_run or [
                {
                    "home_team": o.match.home_team,
                    "away_team": o.match.away_team,
                    "league": o.match.league,
                    "commence_time": o.match.commence_time.isoformat(),
                    "arb_index": round(o.arb_index, 6),
                    "profit_pct": round(o.profit_pct, 4),
                    "opened": False,
                    "legs": [
                        {
                            "outcome_name": leg.outcome_name,
                            "bookmaker": leg.bookmaker,
                            "platform": leg.platform,
                            "odds": leg.odds,
                            "stake": round(leg.stake, 2),
                        }
                        for leg in o.legs
                    ],
                }
                for o in opportunities
            ],
            top_near_arb=near_arb,
            scan_duration_sec=time.time() - t0,
            data_freshness=self._build_freshness(),
        )

        return report

    def _build_freshness(self) -> dict[str, str]:
        now = time.time()
        freshness = {}
        freshness["Polymarket"] = "实时"
        freshness["Kalshi"] = "实时"
        freshness["Myriad"] = "实时"
        freshness["Betfair"] = "实时"
        if self._last_sportsbooks_fetch > 0:
            ago = int(now - self._last_sportsbooks_fetch)
            if ago < 60:
                freshness["博彩公司"] = "实时"
            elif ago < 3600:
                freshness["博彩公司"] = f"{ago // 60} 分钟前"
            elif ago < 86400:
                freshness["博彩公司"] = f"{ago // 3600} 小时前"
            else:
                freshness["博彩公司"] = f"{ago // 86400} 天前"
        else:
            freshness["博彩公司"] = "未拉取"
        return freshness

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
        report: LivePaperReport,
        output_dir: str | Path = "reports",
    ) -> tuple[Path, Path]:
        """保存 Markdown + JSON 报告"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        md_text = report.to_markdown()

        # 始终覆盖 latest.md / latest.json
        latest_md = out / "latest.md"
        latest_json = out / "latest.json"
        latest_md.write_text(md_text, encoding="utf-8")
        with latest_json.open("w", encoding="utf-8") as f:
            json.dump(asdict(report), f, ensure_ascii=False, indent=2)

        # 仅发现套利机会时生成时间戳存档
        # 如果博彩数据是缓存的（旧数据），套利机会不可靠，不存档
        md_path = latest_md
        json_path = latest_json
        if report.opportunities_found > 0:
            has_sportsbooks = any("博彩" in s for s in report.data_sources)
            if has_sportsbooks and not getattr(self, '_sportsbooks_fresh_this_run', True):
                logger.info("博彩数据为缓存，跳过时间戳存档")
            else:
                ts = utc_to_china_str(datetime.now(timezone.utc), "%Y%m%d_%H%M%S")
                md_path = out / f"live_paper_{ts}.md"
                json_path = out / f"live_paper_{ts}.json"
                md_path.write_text(md_text, encoding="utf-8")
                with json_path.open("w", encoding="utf-8") as f:
                    json.dump(asdict(report), f, ensure_ascii=False, indent=2)

        return md_path, json_path
