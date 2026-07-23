"""
模拟盘入口

用法:
    python simulate.py live          # 实时数据模拟盘 + 生成报告（推荐）
    python simulate.py demo          # 场景回测（无需 API）
    python simulate.py run           # 扫描并模拟开仓
    python simulate.py settle        # 自动结算已结束比赛
    python simulate.py report        # 查看盈亏报告
    python simulate.py reset         # 重置模拟盘
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def cmd_live(args: argparse.Namespace) -> int:
    """实时数据模拟盘 + 生成报告"""
    import logging

    from src.live_paper import LivePaperRunner
    from src.odds_api import parse_api_keys
    from src.scanner import load_config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    load_dotenv(ROOT / ".env")
    config = load_config(args.config)

    if args.reset:
        from src.paper_trade import PaperTradeEngine
        PaperTradeEngine(
            initial_bankroll=args.bankroll,
            state_path=args.state,
        ).reset(args.bankroll)
        print(f"模拟盘已重置，初始资金: {args.bankroll:,.2f}")

    if args.no_sportsbooks:
        config.setdefault("sources", {})["sportsbooks"] = False

    api_keys = parse_api_keys(os.getenv("ODDS_API_KEY", ""))
    if not api_keys:
        config.setdefault("sources", {})["sportsbooks"] = False
        print("提示: 未配置 ODDS_API_KEY，仅使用 Polymarket + Kalshi 实时数据")

    max_arb_index = float(config.get("max_arb_index", args.max_arb_index))

    runner = LivePaperRunner(
        config=config,
        api_keys=api_keys,
        bankroll=args.bankroll,
        stake=args.stake,
        max_arb_index=max_arb_index,
        slippage_pct=args.slippage,
        fx_loss_pct=args.fx_loss,
        state_path=args.state,
    )

    print("正在拉取实时数据并运行模拟盘...")
    if args.loop:
        print(f"循环扫描，间隔 {args.interval} 秒，Ctrl+C 停止")
        try:
            while True:
                report = runner.run_once()
                md_path, _ = runner.save_report(report, args.output)
                print(f"\n[{report.run_at}] 扫描 {report.matches_upcoming} 场比赛 | "
                      f"套利 {report.opportunities_found} 个 | 开仓 {report.positions_opened} 笔 | "
                      f"余额 {report.final_bankroll:,.2f}")
                print(f"报告: {md_path}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n已停止")
    else:
        report = runner.run_once()
        md_path, json_path = runner.save_report(report, args.output)
        print("\n" + report.to_markdown())
        print(f"\n报告已保存: {md_path} / {json_path}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """场景回测：用已知赔率和结果验证扣费后能否赚钱"""
    from datetime import datetime, timezone

    from src.arbitrage import calc_arb_index, calc_profit_pct, find_best_quotes
    from src.models import MatchOdds, OddsQuote
    from src.paper_trade import simulate_scenario

    print("=" * 60)
    print("模拟盘场景回测")
    print("=" * 60)
    print(f"参数: 投入={args.stake} | 滑点={args.slippage}% | 汇率损耗={args.fx_loss}%")
    print(f"      预测市场手续费=1% | 安全边际 S<{args.max_arb_index}")
    print()

    scenarios = _build_demo_scenarios()

    total_profit = 0.0
    traded = 0
    wins = 0

    for i, (match, result, label) in enumerate(scenarios, 1):
        print(f"--- 场景 {i}: {label} ---")
        best = find_best_quotes(match)
        s = calc_arb_index(best)
        print(f"  套利指数 S = {s:.4f} | 理论收益 = {calc_profit_pct(s):.2f}%")

        r = simulate_scenario(
            match, result,
            stake=args.stake,
            max_arb_index=args.max_arb_index,
            slippage_pct=args.slippage,
            fx_loss_pct=args.fx_loss,
        )

        if not r["tradeable"]:
            print(f"  → 不开仓: {r['reason']}")
            print()
            continue

        traded += 1
        total_profit += r["net_profit"]
        if r["profitable"]:
            wins += 1

        icon = "✓ 盈利" if r["profitable"] else "✗ 亏损"
        print(f"  结果: {result} | 扣费后 S'={r['adjusted_s']:.4f}")
        print(f"  理论利润: {r['theory_profit']:+.2f} | 手续费: {r['total_fees']:.2f}")
        print(f"  实际净利: {r['net_profit']:+.2f} ({r['net_profit_pct']:+.2f}%) → {icon}")
        print()

    print("=" * 60)
    print("回测汇总")
    print("=" * 60)
    print(f"开仓笔数: {traded}")
    print(f"盈利笔数: {wins} | 亏损笔数: {traded - wins}")
    if traded:
        print(f"胜率:     {wins/traded*100:.0f}%")
    print(f"累计净利: {total_profit:+,.2f}")
    if traded:
        print(f"笔均收益: {total_profit/traded:+,.2f}")
    print()

    if total_profit > 0:
        print("结论: 扣费后整体盈利，策略在以上场景下可行。")
    elif traded == 0:
        print("结论: 无满足条件的套利机会。")
    else:
        print("结论: 扣费后整体亏损，需提高安全边际或降低交易成本。")

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """扫描市场并模拟开仓"""
    from src.odds_api import parse_api_keys
    from src.paper_trade import PaperTradeEngine
    from src.scanner import ArbitrageScanner, load_config

    load_dotenv(ROOT / ".env")
    config = load_config(args.config)

    if args.no_sportsbooks:
        config.setdefault("sources", {})["sportsbooks"] = False

    api_keys = parse_api_keys(os.getenv("ODDS_API_KEY", ""))
    if not api_keys:
        config.setdefault("sources", {})["sportsbooks"] = False

    engine = PaperTradeEngine(
        initial_bankroll=args.bankroll,
        stake_per_trade=args.stake,
        slippage_pct=args.slippage,
        fx_loss_pct=args.fx_loss,
        state_path=args.state,
    )

    max_arb_index = float(config.get("max_arb_index", args.max_arb_index))

    def on_opp(opp):
        pos = engine.try_open(opp)
        if pos:
            print(f"\n[开仓] {pos.home_team} vs {pos.away_team}")
            print(f"  S={pos.arb_index:.4f} 理论收益={pos.theory_profit_pct:.2f}%")
            print(f"  投入={pos.total_stake:.0f} 手续费={pos.total_fees:.2f}")
            print(f"  余额={engine.portfolio.bankroll:,.2f}")

    scanner = ArbitrageScanner(
        config=config,
        api_keys=api_keys,
        total_stake=args.stake,
        max_arb_index=max_arb_index,
        on_opportunity=on_opp,
    )

    if args.loop:
        print(f"模拟盘循环扫描，间隔 {args.interval}s，Ctrl+C 停止")
        print(f"初始资金: {engine.portfolio.bankroll:,.2f}")
        try:
            while True:
                scanner.run_once()
                from src.results import auto_settle_open_positions
                n = auto_settle_open_positions(engine)
                if n:
                    print(f"[结算] {n} 笔")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n已停止")
    else:
        scanner.run_once()
        from src.results import auto_settle_open_positions
        auto_settle_open_positions(engine)

    print("\n" + engine.report())
    return 0


def cmd_settle(args: argparse.Namespace) -> int:
    """结算持仓"""
    from src.paper_trade import PaperTradeEngine
    from src.results import auto_settle_open_positions

    engine = PaperTradeEngine(state_path=args.state)

    if args.home and args.away and args.result:
        settled = engine.settle_by_match(args.home, args.away, args.result, args.date)
        print(f"手动结算 {len(settled)} 笔")
    else:
        n = auto_settle_open_positions(engine)
        print(f"自动结算 {n} 笔")

    print(engine.report())
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from src.paper_trade import PaperTradeEngine

    engine = PaperTradeEngine(state_path=args.state)
    print(engine.report())
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    from src.paper_trade import PaperTradeEngine

    engine = PaperTradeEngine(state_path=args.state)
    engine.reset(args.bankroll)
    print(f"模拟盘已重置，初始资金: {engine.portfolio.bankroll:,.2f}")
    return 0


def _build_demo_scenarios() -> list:
    """构造回测场景：(match, result_outcome, label)"""
    from src.converters import polymarket_price_to_odds
    from src.models import MatchOdds, OddsQuote

    t = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)

    # 场景1: 用户经典案例 — 大套利空间
    case1 = MatchOdds(
        sport="demo", league="世界杯半决赛",
        home_team="France", away_team="Spain",
        commence_time=t,
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

    # 场景2: 跨平台 — 博彩 + Polymarket
    case2 = MatchOdds(
        sport="demo", league="世界杯半决赛",
        home_team="France", away_team="Spain",
        commence_time=t,
        quotes=[
            OddsQuote("pinnacle", "home", 2.60, "France"),
            OddsQuote("onexbet", "draw", 4.20, "Draw"),
            OddsQuote("bet365", "away", 3.10, "Spain"),
            OddsQuote("polymarket", "home", polymarket_price_to_odds(0.4125), "France",
                      platform="prediction"),
            OddsQuote("polymarket", "draw", polymarket_price_to_odds(0.30), "Draw",
                      platform="prediction"),
            OddsQuote("polymarket", "away", polymarket_price_to_odds(0.2925), "Spain",
                      platform="prediction"),
        ],
    )

    # 场景3: 边际套利 — S≈0.975，扣费后可能由盈转亏
    case3 = MatchOdds(
        sport="demo", league="英超",
        home_team="Arsenal", away_team="Chelsea",
        commence_time=t,
        quotes=[
            OddsQuote("pinnacle", "home", 2.26, "Arsenal"),
            OddsQuote("bet365", "draw", 3.66, "Draw"),
            OddsQuote("onexbet", "away", 3.89, "Chelsea"),
        ],
    )

    # 场景4: 无套利
    case4 = MatchOdds(
        sport="demo", league="英超",
        home_team="Liverpool", away_team="Man City",
        commence_time=t,
        quotes=[
            OddsQuote("pinnacle", "home", 2.80, "Liverpool"),
            OddsQuote("pinnacle", "draw", 3.40, "Draw"),
            OddsQuote("pinnacle", "away", 2.50, "Man City"),
        ],
    )

    return [
        (case1, "home", "经典三平台套利 (S≈0.945)"),
        (case1, "draw", "经典三平台套利 — 平局结果"),
        (case1, "away", "经典三平台套利 — 客胜结果"),
        (case2, "draw", "跨平台套利 (博彩+Polymarket)"),
        (case3, "home", "边际套利 (S≈0.972，扣费考验)"),
        (case3, "draw", "边际套利 — 平局结果"),
        (case4, "home", "无套利 (S>1，不应开仓)"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="套利模拟盘")
    sub = parser.add_subparsers(dest="command")

    # live - 实时模拟盘
    p_live = sub.add_parser("live", help="实时数据模拟盘并生成报告")
    p_live.add_argument("-c", "--config", default=str(ROOT / "config.yaml"))
    p_live.add_argument("--bankroll", type=float, default=100000)
    p_live.add_argument("--stake", type=float, default=10000)
    p_live.add_argument("--max-arb-index", type=float, default=0.98)
    p_live.add_argument("--slippage", type=float, default=0.5)
    p_live.add_argument("--fx-loss", type=float, default=0.3)
    p_live.add_argument("--state", default=str(ROOT / "data" / "paper_state.json"))
    p_live.add_argument("--output", default=str(ROOT / "reports"))
    p_live.add_argument("--no-sportsbooks", action="store_true")
    p_live.add_argument("--reset", action="store_true", help="运行前重置模拟盘")
    p_live.add_argument("--loop", action="store_true", help="循环扫描")
    p_live.add_argument("--interval", type=int, default=60, help="循环间隔秒数")

    # demo
    p_demo = sub.add_parser("demo", help="场景回测")
    p_demo.add_argument("--stake", type=float, default=10000)
    p_demo.add_argument("--max-arb-index", type=float, default=0.98)
    p_demo.add_argument("--slippage", type=float, default=0.5)
    p_demo.add_argument("--fx-loss", type=float, default=0.3)

    # run
    p_run = sub.add_parser("run", help="扫描并模拟开仓")
    p_run.add_argument("-c", "--config", default=str(ROOT / "config.yaml"))
    p_run.add_argument("--bankroll", type=float, default=100000)
    p_run.add_argument("--stake", type=float, default=10000)
    p_run.add_argument("--max-arb-index", type=float, default=0.98)
    p_run.add_argument("--slippage", type=float, default=0.5)
    p_run.add_argument("--fx-loss", type=float, default=0.3)
    p_run.add_argument("--state", default=str(ROOT / "data" / "paper_state.json"))
    p_run.add_argument("--no-sportsbooks", action="store_true")
    p_run.add_argument("--loop", action="store_true")
    p_run.add_argument("--interval", type=int, default=120)

    # settle
    p_settle = sub.add_parser("settle", help="结算持仓")
    p_settle.add_argument("--state", default=str(ROOT / "data" / "paper_state.json"))
    p_settle.add_argument("--home", help="手动结算主队")
    p_settle.add_argument("--away", help="手动结算客队")
    p_settle.add_argument("--result", choices=["home", "draw", "away"])
    p_settle.add_argument("--date", help="比赛日期 YYYY-MM-DD")

    # report
    p_report = sub.add_parser("report", help="查看报告")
    p_report.add_argument("--state", default=str(ROOT / "data" / "paper_state.json"))

    # reset
    p_reset = sub.add_parser("reset", help="重置模拟盘")
    p_reset.add_argument("--bankroll", type=float, default=100000)
    p_reset.add_argument("--state", default=str(ROOT / "data" / "paper_state.json"))

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    cmds = {
        "live": cmd_live,
        "demo": cmd_demo,
        "run": cmd_run,
        "settle": cmd_settle,
        "report": cmd_report,
        "reset": cmd_reset,
    }
    return cmds[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
