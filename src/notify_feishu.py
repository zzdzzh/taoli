"""飞书机器人通知：仅对新出现的套利机会推送（与上次扫描对比去重）"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable

import requests

from .converters import utc_to_china_str
from .models import ArbitrageOpportunity

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = ROOT / "data" / "last_notified_opps.json"

_OUTCOME_CN = {"home": "主胜", "draw": "平局", "away": "客胜"}
_PLATFORM_CN = {
    "prediction": "预测",
    "exchange": "交易所",
    "sportsbook": "博彩",
}


def opportunity_fingerprint(opp: ArbitrageOpportunity) -> str:
    """机会指纹：同场次 + 各腿平台/结果/赔率（两位小数）一致则视为同一机会。"""
    legs = sorted(
        f"{leg.outcome}:{leg.bookmaker}:{round(leg.odds, 2)}"
        for leg in opp.legs
    )
    commence = utc_to_china_str(opp.match.commence_time, "%Y-%m-%dT%H:%M")
    return (
        f"{opp.match.home_team}|{opp.match.away_team}|{commence}|{'|'.join(legs)}"
    )


def _load_last_fps(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        fps = data.get("fingerprints", data if isinstance(data, list) else [])
        return set(fps)
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning("读取上次通知记录失败，将视为首次: %s", e)
        return set()


def _save_last_fps(path: Path, fingerprints: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fingerprints": sorted(set(fingerprints))}
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _format_opp_md(opp: ArbitrageOpportunity) -> str:
    """单场套利机会的飞书 Markdown 正文。"""
    m = opp.match
    lines = [
        f"**{m.home_team} vs {m.away_team}**",
        f"{m.league} · {utc_to_china_str(m.commence_time)}",
        f"S `{opp.arb_index:.4f}` · 理论收益 **{opp.profit_pct:.2f}%**",
        (
            f"投入 `{opp.total_stake:.0f}` → 保底 `{opp.guaranteed_payout:.0f}`"
            f"（利润 `{opp.profit:.0f}`）"
        ),
        "",
        "**投注分配**",
    ]
    for leg in opp.legs:
        oc = _OUTCOME_CN.get(leg.outcome, leg.outcome)
        plat = _PLATFORM_CN.get(leg.platform, leg.platform)
        name = leg.outcome_name or oc
        lines.append(
            f"· {name}（{oc}）@{leg.bookmaker}/{plat}"
            f" · 赔率 `{leg.odds:.2f}` · 投 `{leg.stake:.0f}`"
        )
    return "\n".join(lines)


def build_feishu_card(opps: list[ArbitrageOpportunity]) -> dict[str, Any]:
    """构建飞书交互式卡片（自定义机器人 msg_type=interactive）。"""
    n = len(opps)
    max_pct = max((o.profit_pct for o in opps), default=0.0)
    # 收益越高越醒目：≥5% 红，≥2% 绿，其余橙
    if max_pct >= 5:
        template = "red"
    elif max_pct >= 2:
        template = "green"
    else:
        template = "orange"

    elements: list[dict[str, Any]] = []
    for i, opp in enumerate(opps):
        if i > 0:
            elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": _format_opp_md(opp)},
            }
        )
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "理论值，未扣手续费 / 汇率 / 限额 / 滑点",
                }
            ],
        }
    )

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"新套利机会 · {n} 个",
                },
                "template": template,
            },
            "elements": elements,
        },
    }


def send_feishu_card(
    webhook_url: str,
    payload: dict[str, Any],
    timeout: float = 10.0,
) -> bool:
    """向飞书自定义机器人 webhook 发送卡片消息。"""
    try:
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        # 飞书成功一般为 code=0；部分旧接口无 code
        if isinstance(body, dict) and body.get("code", 0) != 0:
            logger.error("飞书推送失败: %s", body)
            return False
        return True
    except requests.RequestException as e:
        logger.error("飞书推送请求异常: %s", e)
        return False


def notify_new_opportunities(
    opportunities: list[ArbitrageOpportunity],
    *,
    webhook_url: str | None = None,
    state_path: Path | str | None = None,
) -> list[ArbitrageOpportunity]:
    """
    与上次扫描结果对比，仅对新机会发飞书通知。

    - 未配置 FEISHU_WEBHOOK_URL 时静默跳过推送，但仍更新本地指纹（便于后续启用）。
    - 返回本次实际视为「新」的机会列表。
    """
    url = (webhook_url if webhook_url is not None else os.getenv("FEISHU_WEBHOOK_URL", "")).strip()
    path = Path(state_path) if state_path else DEFAULT_STATE_PATH

    current_map = {opportunity_fingerprint(o): o for o in opportunities}
    current_fps = set(current_map.keys())
    last_fps = _load_last_fps(path)
    new_fps = current_fps - last_fps
    new_opps = [current_map[fp] for fp in sorted(new_fps)]

    if new_opps and url:
        ok = send_feishu_card(url, build_feishu_card(new_opps))
        if ok:
            logger.info("已向飞书推送 %d 个新套利机会", len(new_opps))
        else:
            logger.warning("飞书推送未成功，本次不更新去重记录，下次仍会重试")
            return new_opps
    elif new_opps and not url:
        logger.debug(
            "发现 %d 个新机会，但未配置 FEISHU_WEBHOOK_URL，跳过推送",
            len(new_opps),
        )
    else:
        logger.debug("无新套利机会，跳过飞书通知")

    # 无论是否有 webhook，都把「当前扫描集合」记为上次，避免重复刷屏
    # 推送失败时已提前 return，不会走到这里
    _save_last_fps(path, current_fps)
    return new_opps
