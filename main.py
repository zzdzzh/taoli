"""胜平负套利扫描 - 命令行入口"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.odds_api import parse_api_keys
from src.scanner import ArbitrageScanner, load_config

ROOT = Path(__file__).resolve().parent


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    load_dotenv(ROOT / ".env")

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="足球胜平负跨平台套利扫描器",
    )
    parser.add_argument("-c", "--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--stake", type=float, default=float(os.getenv("TOTAL_STAKE", "10000")))
    parser.add_argument(
        "--max-arb-index",
        type=float,
        default=None,
        help="套利指数上限 S（默认 0.98，即至少 2%% 安全边际）",
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=None,
        help="额外最低理论收益率（%%）",
    )
    parser.add_argument("--loop", action="store_true", help="循环扫描")
    parser.add_argument("--interval", type=int, default=int(os.getenv("SCAN_INTERVAL", "60")))
    parser.add_argument("-o", "--output", help="保存 JSON 报告")
    parser.add_argument("--no-sportsbooks", action="store_true", help="跳过博彩公司")
    parser.add_argument("--no-polymarket", action="store_true", help="跳过 Polymarket")
    parser.add_argument("--no-kalshi", action="store_true", help="跳过 Kalshi")
    parser.add_argument("--no-myriad", action="store_true", help="跳过 Myriad")
    parser.add_argument("--no-betfair", action="store_true", help="跳过 Betfair Exchange 直连")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    config = load_config(args.config)

    # CLI 覆盖数据源开关
    if "sources" not in config:
        config["sources"] = {}
    if args.no_sportsbooks:
        config["sources"]["sportsbooks"] = False
    if args.no_polymarket:
        config["sources"]["polymarket"] = False
    if args.no_kalshi:
        config["sources"]["kalshi"] = False
    if args.no_myriad:
        config["sources"]["myriad"] = False
    if args.no_betfair:
        config["sources"]["betfair"] = False

    api_keys = parse_api_keys(os.getenv("ODDS_API_KEY", ""))
    need_api = config["sources"].get("sportsbooks", True)
    if need_api and not api_keys:
        other_on = any(
            config["sources"].get(k)
            for k in ("polymarket", "kalshi", "myriad", "betfair")
        )
        if other_on:
            print("提示: 未设置 ODDS_API_KEY，跳过 The Odds API 博彩源")
            config["sources"]["sportsbooks"] = False
        else:
            print("错误: 请在 .env 中设置 ODDS_API_KEY，或启用其他数据源")
            print("注册地址: https://the-odds-api.com")
            return 1

    max_arb_index = args.max_arb_index
    if max_arb_index is None:
        max_arb_index = float(config.get("max_arb_index", os.getenv("MAX_ARB_INDEX", "0.98")))

    min_profit_pct = args.min_profit
    if min_profit_pct is None:
        min_profit_pct = float(config.get("min_profit_pct", os.getenv("MIN_PROFIT_PCT", "0")))

    scanner = ArbitrageScanner(
        config=config,
        api_keys=api_keys,
        total_stake=args.stake,
        max_arb_index=max_arb_index,
        min_profit_pct=min_profit_pct,
    )

    def scan_and_save():
        opps = scanner.run_once()
        if args.output and opps:
            scanner.save_report(opps, args.output)
        return opps

    if args.loop:
        print(f"循环扫描，间隔 {args.interval} 秒，Ctrl+C 停止")
        try:
            while True:
                scan_and_save()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n已停止")
    else:
        scan_and_save()

    return 0


if __name__ == "__main__":
    sys.exit(main())
