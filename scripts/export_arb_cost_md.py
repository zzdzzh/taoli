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
        raise SystemExit("缺少 data/arb_cost_analysis.json，请先运行 analyze_cache_arb.py")

    d = json.loads(analysis_path.read_text(encoding="utf-8"))
    a = d["assumptions"]
    s = d["summary"]
    fetched = a.get("fetched_at")
    fetched_str = (
        datetime.fromtimestamp(fetched, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if fetched
        else "N/A"
    )
    cache_file = a.get("cache_file", "all_sources_cache.json")
    pred_fee = a.get("prediction_fee_pct", 1.0)
    bookmakers = a.get("bookmakers") or {}
    source_counts = a.get("source_counts") or {}

    lines: list[str] = [
        "# 全平台缓存套利分析（含成本）",
        "",
        f"- 数据源: `data/{cache_file}`",
        f"- 构建时间: {fetched_str}",
        f"- 合并比赛: {a['cache_matches']} 场 · 可计算: {a['scored']} 场",
    ]
    if source_counts:
        parts = [f"{k}={v}" for k, v in source_counts.items()]
        lines.append(f"- 分源场数: {', '.join(parts)}")
    lines += ["- API: The Odds API（多 Key）+ Polymarket/Kalshi 直连", ""]

    if bookmakers:
        lines += ["## 包含平台", "", "| 平台 | 报价条数 |", "|------|----------|"]
        for name, n in sorted(bookmakers.items(), key=lambda x: -x[1]):
            lines.append(f"| {name} | {n} |")
        lines.append("")

    lines.append("## 结论")
    lines.append("")
    if s["net_arb"] > 0:
        lines.append(
            f"**全成本后有 {s['net_arb']} 场净套利**"
            f"（最佳净收益 {s['best_net_pct']:+.2f}%）。"
        )
    else:
        lines.append("**扣成本后无可执行净套利。**")
    lines.append("")
    lines.append(
        f"- 裸盘理论套利（S_raw < 1）: **{s['raw_arb']}** 场"
        f"（最高 {s['best_raw_pct']:+.2f}%）"
    )
    lines.append(f"- 扣佣/手续费后（S_comm < 1）: **{s['comm_arb']}** 场")
    lines.append(
        f"- 全成本净利 > 0: **{s['net_arb']}** 场"
        f"（最佳 {s['best_net_pct']:+.2f}%）"
    )
    lines.append("")
    lines += ["## 成本假设", "", "| 项目 | 取值 |", "|------|------|"]
    lines.append(f"| 每场总投入 | {a['stake']:.0f} |")
    lines.append(f"| 赔率滑点 | {a['slippage_pct']}% |")
    lines.append(f"| 跨平台汇率损耗 | {a['fx_loss_pct']}% |")
    for k, v in a["commissions"].items():
        label = "手续费" if k in ("polymarket", "kalshi") else "佣金（净盈利）"
        lines.append(f"| {k} {label} | {v}% |")
    lines += [
        "",
        "```",
        "交易所有效赔率 = 1 + (odds - 1) × (1 - 佣金%)",
        f"预测市场执行赔率 = odds × (1 - 滑点%) / (1 + {pred_fee}%)",
        "净收益率 = (1/S_slip - 1 - 汇率损耗%) × 100",
        "```",
        "",
        "## 套利指数分布",
        "",
        f"- S_raw: min={s['s_raw_min']:.4f} · median={s['s_raw_median']:.4f}",
        f"- S_slip: min={s['s_slip_min']:.4f} · median={s['s_slip_median']:.4f}",
        "",
        "| S 区间 | 裸盘场数 | 扣费+滑点后 |",
        "|--------|----------|-------------|",
    ]
    for hr, hs in zip(d["hist_raw"], d["hist_slip"]):
        lines.append(f"| {hr['bucket']} | {hr['count']} | {hs['count']} |")
    lines += [
        "",
        "## 最接近套利 TOP20",
        "",
        "| # | 比赛 | 联赛 | S_raw | 理论% | S_comm | 扣费% | 净% |",
        "|---|------|------|-------|-------|--------|-------|-----|",
    ]
    for i, r in enumerate(d["top"], 1):
        tag = " NET+" if r["net_arb"] else (" RAW+" if r["raw_arb"] else "")
        lines.append(
            f"| {i}{tag} | {r['home']} vs {r['away']} | {r['league']} | "
            f"{r['s_raw']:.4f} | {r['p_raw']:+.2f}% | "
            f"{r['s_comm']:.4f} | {r['p_comm']:+.2f}% | {r['p_net']:+.2f}% |"
        )
    lines += ["", "## TOP 明细（腿分配）", ""]
    for i, r in enumerate(d["top"][:10], 1):
        lines.append(f"### {i}. {r['home']} vs {r['away']}（{r['league']}）")
        lines.append("")
        lines.append(
            f"- S_raw={r['s_raw']:.4f}（{r['p_raw']:+.2f}%）→ "
            f"S_comm={r['s_comm']:.4f}（{r['p_comm']:+.2f}%）→ 净 {r['p_net']:+.2f}%"
        )
        lines.append(f"- 扣成本后平台: {', '.join(r['platforms_net'])}")
        lines.append("")
        lines.append("| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |")
        lines.append("|------|------|------|------|------|-----|------|")
        for lg in r["legs"]:
            fee = f"{lg['comm_pct']:.0f}%" if lg["comm_pct"] else "-"
            lines.append(
                f"| {lg['name']} | {lg['bookmaker']} | {lg.get('platform', '')} | "
                f"{lg['raw']:.3f} | {lg['eff']:.3f} | {fee} | {lg['stake']:.2f} |"
            )
        lines.append("")

    out = ROOT / "reports" / "arb_cost_analysis.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
