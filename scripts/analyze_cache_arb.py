"""分析 sportsbooks_cache.json：含交易所佣金 / 滑点 / 汇率损耗的套利可能性。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.arbitrage import calc_profit_pct, infer_outcomes  # noqa: E402
from src.exchanges import effective_exchange_odds, get_commission, is_exchange  # noqa: E402
from src.models import MatchOdds, OddsQuote  # noqa: E402


@dataclass
class EffQuote:
    bookmaker: str
    outcome: str
    outcome_name: str
    platform: str
    raw_odds: float
    after_comm: float
    after_all: float
    commission_pct: float


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    pt = cfg.get("paper_trade", {})
    slippage = float(pt.get("slippage_pct", 0.5))
    fx_loss = float(pt.get("fx_loss_pct", 0.3))
    stake = float(pt.get("stake_per_trade", 10000.0))

    data = json.loads((ROOT / "data" / "sportsbooks_cache.json").read_text(encoding="utf-8"))
    matches: list[MatchOdds] = []
    for m in data.get("matches", []):
        matches.append(
            MatchOdds(
                sport=m["sport"],
                league=m["league"],
                home_team=m["home_team"],
                away_team=m["away_team"],
                commence_time=datetime.fromisoformat(m["commence_time"]),
                quotes=[OddsQuote(**q) for q in m.get("quotes", [])],
            )
        )

    def to_eff(q: OddsQuote) -> EffQuote:
        use_comm = is_exchange(q.bookmaker) or q.platform == "exchange"
        comm = get_commission(q.bookmaker, cfg) if use_comm else 0.0
        after_comm = effective_exchange_odds(q.odds, comm) if comm else q.odds
        after_all = after_comm * (1.0 - slippage / 100.0)
        return EffQuote(
            q.bookmaker,
            q.outcome,
            q.outcome_name,
            q.platform,
            q.odds,
            after_comm,
            after_all,
            comm,
        )

    def best_by(quotes: list[EffQuote], attr: str) -> dict[str, EffQuote]:
        best: dict[str, EffQuote] = {}
        for q in quotes:
            cur = best.get(q.outcome)
            if cur is None or getattr(q, attr) > getattr(cur, attr):
                best[q.outcome] = q
        return best

    def s_of(best: dict[str, EffQuote], outcomes: tuple[str, ...], attr: str) -> float | None:
        if not all(o in best for o in outcomes):
            return None
        return sum(1.0 / getattr(best[o], attr) for o in outcomes)

    rows: list[dict] = []
    for m in matches:
        outcomes = infer_outcomes(m)
        eq = [to_eff(q) for q in m.quotes if q.outcome in outcomes]
        if not eq:
            continue
        b_raw = best_by(eq, "raw_odds")
        b_comm = best_by(eq, "after_comm")
        b_net = best_by(eq, "after_all")
        s_raw = s_of(b_raw, outcomes, "raw_odds")
        s_comm = s_of(b_comm, outcomes, "after_comm")
        s_slip = s_of(b_net, outcomes, "after_all")
        if s_raw is None:
            continue

        p_raw = calc_profit_pct(s_raw)
        p_comm = calc_profit_pct(s_comm) if s_comm else None
        p_slip = calc_profit_pct(s_slip) if s_slip else None
        p_net = (
            (1.0 / s_slip - 1.0 - fx_loss / 100.0) * 100.0
            if s_slip and s_slip > 0
            else None
        )

        legs_net: list[dict] = []
        if s_slip and all(o in b_net for o in outcomes):
            implied = {o: 1.0 / b_net[o].after_all for o in outcomes}
            tot = sum(implied.values())
            for o in outcomes:
                q = b_net[o]
                st = stake * implied[o] / tot
                legs_net.append(
                    {
                        "outcome": o,
                        "name": q.outcome_name or o,
                        "bookmaker": q.bookmaker,
                        "platform": q.platform,
                        "raw": round(q.raw_odds, 3),
                        "eff": round(q.after_all, 3),
                        "comm_pct": q.commission_pct,
                        "stake": round(st, 2),
                    }
                )

        rows.append(
            {
                "home": m.home_team,
                "away": m.away_team,
                "league": m.league,
                "sport": m.sport,
                "commence": m.commence_time.isoformat(),
                "n_way": len(outcomes),
                "s_raw": round(s_raw, 6),
                "p_raw": round(p_raw, 4),
                "s_comm": round(s_comm, 6) if s_comm else None,
                "p_comm": round(p_comm, 4) if p_comm is not None else None,
                "s_slip": round(s_slip, 6) if s_slip else None,
                "p_slip": round(p_slip, 4) if p_slip is not None else None,
                "p_net": round(p_net, 4) if p_net is not None else None,
                "raw_arb": s_raw < 1.0,
                "comm_arb": s_comm is not None and s_comm < 1.0,
                "net_arb": p_net is not None and p_net > 0,
                "legs": legs_net,
                "platforms_raw": sorted({b_raw[o].bookmaker for o in outcomes if o in b_raw}),
                "platforms_net": sorted({b_net[o].bookmaker for o in outcomes if o in b_net}),
            }
        )

    rows.sort(key=lambda r: r["p_net"] if r["p_net"] is not None else -999, reverse=True)

    s_raws = [r["s_raw"] for r in rows]
    s_nets = [r["s_slip"] for r in rows if r["s_slip"]]

    print("=== 成本假设 ===")
    print("交易所佣金: betfair_ex_uk 5%, smarkets 2%, matchbook 1%")
    print(f"滑点: {slippage}% | 汇率损耗: {fx_loss}% | 总投入/场: {stake}")
    print(f"可计算比赛: {len(rows)}")
    print()
    print("=== 汇总 ===")
    print(f"理论套利(S_raw<1): {sum(1 for r in rows if r['raw_arb'])}")
    print(f"扣佣后套利(S_comm<1): {sum(1 for r in rows if r['comm_arb'])}")
    print(f"扣佣+滑点+汇率后净利>0: {sum(1 for r in rows if r['net_arb'])}")
    print(f"S_raw: min={min(s_raws):.4f} median={median(s_raws):.4f} max={max(s_raws):.4f}")
    print(
        f"S_after_slip: min={min(s_nets):.4f} median={median(s_nets):.4f} max={max(s_nets):.4f}"
    )
    print()
    print("=== 最接近套利 TOP15（按净收益排序）===")
    for i, r in enumerate(rows[:15], 1):
        if r["net_arb"]:
            flag = "NET+"
        elif r["comm_arb"]:
            flag = "COMM+"
        elif r["raw_arb"]:
            flag = "RAW+"
        else:
            flag = "near"
        print(f"{i:2d}. [{flag}] {r['home']} vs {r['away']} | {r['league']}")
        print(
            f"    S_raw={r['s_raw']:.4f}({r['p_raw']:+.2f}%) | "
            f"S_comm={r['s_comm']:.4f}({r['p_comm']:+.2f}%) | "
            f"net={r['p_net']:+.2f}%"
        )
        print(f"    raw平台={r['platforms_raw']} | net平台={r['platforms_net']}")
        for lg in r["legs"]:
            c = f" 佣{lg['comm_pct']}%" if lg["comm_pct"] else ""
            print(
                f"      {lg['outcome']:5s} {lg['bookmaker']:14s} "
                f"raw={lg['raw']:.3f} eff={lg['eff']:.3f}{c} stake={lg['stake']:.0f}"
            )

    bins = [
        (0, 0.98),
        (0.98, 0.99),
        (0.99, 1.00),
        (1.00, 1.01),
        (1.01, 1.02),
        (1.02, 1.03),
        (1.03, 1.05),
        (1.05, 1.10),
        (1.10, 99),
    ]
    labels = [
        "S<0.98",
        "0.98–0.99",
        "0.99–1.00",
        "1.00–1.01",
        "1.01–1.02",
        "1.02–1.03",
        "1.03–1.05",
        "1.05–1.10",
        "S≥1.10",
    ]

    def hist(vals: list[float]) -> list[dict]:
        return [
            {"bucket": lab, "count": sum(1 for v in vals if a <= v < b)}
            for (a, b), lab in zip(bins, labels)
        ]

    exchange_keys = {"betfair_ex_uk", "smarkets", "matchbook"}
    ex_inflated = 0
    for r in rows:
        if exchange_keys & set(r["platforms_raw"]):
            if r["p_raw"] > 0 and not r["net_arb"]:
                ex_inflated += 1

    out = {
        "assumptions": {
            "stake": stake,
            "slippage_pct": slippage,
            "fx_loss_pct": fx_loss,
            "commissions": {
                "betfair_ex_uk": 5.0,
                "smarkets": 2.0,
                "matchbook": 1.0,
            },
            "cache_matches": len(matches),
            "scored": len(rows),
            "fetched_at": data.get("last_fetch"),
        },
        "summary": {
            "raw_arb": sum(1 for r in rows if r["raw_arb"]),
            "comm_arb": sum(1 for r in rows if r["comm_arb"]),
            "net_arb": sum(1 for r in rows if r["net_arb"]),
            "s_raw_min": round(min(s_raws), 6),
            "s_raw_median": round(median(s_raws), 6),
            "s_slip_min": round(min(s_nets), 6),
            "s_slip_median": round(median(s_nets), 6),
            "best_net_pct": rows[0]["p_net"] if rows else None,
            "best_raw_pct": max(r["p_raw"] for r in rows) if rows else None,
            "exchange_looks_arb_but_net_fail": ex_inflated,
        },
        "top": rows[:20],
        "hist_raw": hist(s_raws),
        "hist_slip": hist(s_nets),
    }

    out_path = ROOT / "data" / "arb_cost_analysis.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"已写入 {out_path}")


if __name__ == "__main__":
    main()