"""从 data/arb_cost_analysis.json 生成 Markdown 报告。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    analysis_path = ROOT / "data" / "arb_cost_analysis.json"
    if not analysis_path.exists():
        raise SystemExit(f"缺少分析结果: {analysis_path}，请先运行 scripts/analyze_cache_arb.py")

    d = json.loads(analysis_path.read_text(encoding="utf-8"))
    a = d["assumptions"]
    s = d["summary"]
    fetched = a.get("fetched_at")
    fetched_str = (
        datetime.fromtimestamp(fetched, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if fetched
        else "N/A"
    )

    lines: list[str] = []
    lines.append("# Sportsbooks 缓存套利分析（含成本）")
    lines.append("")
    lines.append("- 数据源: `data/sportsbooks_cache.json`")
    lines.append(f"- 缓存拉取时间: {fetched_str}")
    lines.append(
        f"- 缓存比赛: {a['cache_matches']} 场 · 可计算: {a['scored']} 场"
    )
    lines.append("- 分析脚本: `scripts/analyze_cache_arb.py`")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append("**扣成本后无可执行净套利。**")
    lines.append("")
    lines.append(
        f"- 裸盘理论套利（S_raw < 1）: **{s['raw_arb']}** 场"
        f"（最高理论收益 {s['best_raw_pct']:+.2f}%）"
    )
    lines.append(f"- 扣交易所佣金后（S_comm < 1）: **{s['comm_arb']}** 场")
    lines.append(
        f"- 扣佣金 + 滑点 + 汇率后净利 > 0: **{s['net_arb']}** 场"
        f"（最佳净收益 {s['best_net_pct']:+.2f}%）"
    )
    lines.append(
        f"- 其中「交易所虚高」导致理论套利但净利为负: "
        f"{s['exchange_looks_arb_but_net_fail']} 场"
    )
    lines.append("")
    lines.append("## 成本假设")
    lines.append("")
    lines.append("| 项目 | 取值 |")
    lines.append("|------|------|")
    lines.append(f"| 每场总投入 | {a['stake']:.0f} |")
    lines.append(f"| 赔率滑点 | {a['slippage_pct']}% |")
    lines.append(f"| 跨平台汇率损耗 | {a['fx_loss_pct']}% |")
    for k, v in a["commissions"].items():
        lines.append(f"| {k} 佣金（净盈利） | {v}% |")
    lines.append("")
    lines.append("有效赔率计算：")
    lines.append("")
    lines.append("```")
    lines.append("交易所有效赔率 = 1 + (odds - 1) × (1 - 佣金%)")
    lines.append("执行赔率       = 有效赔率 × (1 - 滑点%)")
    lines.append("净收益率       = (1/S_slip - 1 - 汇率损耗%) × 100")
    lines.append("```")
    lines.append("")
    lines.append("每个结果按**执行赔率最高**重选最优腿（不是按裸盘最高赔）。")
    lines.append("")
    lines.append("## 套利指数分布")
    lines.append("")
    lines.append(
        f"- S_raw: min={s['s_raw_min']:.4f} · median={s['s_raw_median']:.4f}"
    )
    lines.append(
        f"- S_slip（扣佣+滑点）: min={s['s_slip_min']:.4f} · "
        f"median={s['s_slip_median']:.4f}"
    )
    lines.append("")
    lines.append("| S 区间 | 裸盘场数 | 扣佣+滑点后场数 |")
    lines.append("|--------|----------|-----------------|")
    for hr, hs in zip(d["hist_raw"], d["hist_slip"]):
        lines.append(f"| {hr['bucket']} | {hr['count']} | {hs['count']} |")
    lines.append("")
    lines.append("## 最接近套利 TOP20（按净收益）")
    lines.append("")
    lines.append(
        "| # | 比赛 | 联赛 | S_raw | 理论% | S_comm | 扣佣% | 净% |"
    )
    lines.append("|---|------|------|-------|-------|--------|-------|-----|")
    for i, r in enumerate(d["top"], 1):
        tag = ""
        if r["net_arb"]:
            tag = " NET+"
        elif r["raw_arb"]:
            tag = " RAW+"
        lines.append(
            f"| {i}{tag} | {r['home']} vs {r['away']} | {r['league']} | "
            f"{r['s_raw']:.4f} | {r['p_raw']:+.2f}% | "
            f"{r['s_comm']:.4f} | {r['p_comm']:+.2f}% | {r['p_net']:+.2f}% |"
        )
    lines.append("")
    lines.append("## TOP 明细（腿分配）")
    lines.append("")
    for i, r in enumerate(d["top"][:10], 1):
        lines.append(f"### {i}. {r['home']} vs {r['away']}（{r['league']}）")
        lines.append("")
        lines.append(f"- 开赛: {r['commence']}")
        lines.append(
            f"- S_raw={r['s_raw']:.4f}（{r['p_raw']:+.2f}%）→ "
            f"S_comm={r['s_comm']:.4f}（{r['p_comm']:+.2f}%）→ "
            f"净 {r['p_net']:+.2f}%"
        )
        lines.append(f"- 裸盘最优平台: {', '.join(r['platforms_raw'])}")
        lines.append(f"- 扣成本后最优平台: {', '.join(r['platforms_net'])}")
        lines.append("")
        lines.append("| 结果 | 平台 | 裸盘赔率 | 执行赔率 | 佣金 | 建议投注 |")
        lines.append("|------|------|----------|----------|------|----------|")
        for lg in r["legs"]:
            comm = f"{lg['comm_pct']:.0f}%" if lg["comm_pct"] else "-"
            lines.append(
                f"| {lg['name']} ({lg['outcome']}) | {lg['bookmaker']} | "
                f"{lg['raw']:.3f} | {lg['eff']:.3f} | {comm} | {lg['stake']:.2f} |"
            )
        lines.append("")

    lines.append("## 实务含义")
    lines.append("")
    lines.append(
        "1. 当前缓存仅含博彩公司/交易所，**不能**作为跨庄净套利下单依据。"
    )
    lines.append(
        "2. 6 场理论套利全部依赖交易所高赔，扣佣后即失效；"
        "扫描器若只用裸盘 S，会误报。"
    )
    lines.append(
        "3. 若要提高可执行性：纳入 Polymarket/Kalshi 价差、使用更低佣金档、"
        "或要求 S 明显低于 0.98 且腿尽量落在固定赔率庄家。"
    )
    lines.append("")

    out = ROOT / "reports" / "arb_cost_analysis.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()