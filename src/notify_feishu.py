"""飞书机器人通知：使用卡片模板推送新套利机会"""

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

_PLATFORM_TAG = {
    "prediction": " [预测市场]",
    "exchange": " [交易所]",
    "sportsbook": "",
}


def opportunity_fingerprint(opp: ArbitrageOpportunity) -> str:
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


def _format_leg(leg, outcome_label: str) -> str:
    platform_name = leg.outcome_name or (leg.bookmaker if leg.platform == "prediction" else "")
    tag = _PLATFORM_TAG.get(leg.platform, "")
    return (
        f"**{platform_name} ({outcome_label})**\n"
        f"@{leg.bookmaker}{tag}\n"
        f"赔率: {leg.odds:.2f}\n"
        f"投注: {leg.stake:.2f}\n"
        f"回报: {leg.payout:.2f}"
    )


def build_template_card(opp: ArbitrageOpportunity) -> dict[str, Any]:
    m = opp.match
    template_id = os.getenv("FEISHU_TEMPLATE_ID", "")

    odds_parts = ["", "", ""]
    labels = {"home": "主胜", "draw": "平局", "away": "客胜"}
    for leg in opp.legs:
        idx = {"home": 0, "draw": 1, "away": 2}.get(leg.outcome)
        if idx is not None:
            odds_parts[idx] = _format_leg(leg, labels.get(leg.outcome, leg.outcome))

    return {
        "msg_type": "interactive",
        "card": {
            "type": "template",
            "data": {
                "template_id": template_id,
                "template_version_name": "1.0.1",
                "template_variable": {
                    "team1": m.home_team,
                    "team2": m.away_team,
                    "liansai": m.league,
                    "shijian": utc_to_china_str(m.commence_time),
                    "shouru": f"{opp.profit_pct:.2f}%",
                    "odds1": odds_parts[0],
                    "odds2": odds_parts[1],
                    "odds3": odds_parts[2],
                },
            },
        },
    }


def send_feishu_card(
    webhook_url: str,
    payload: dict[str, Any],
    timeout: float = 10.0,
) -> bool:
    try:
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
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
    url = (webhook_url if webhook_url is not None else os.getenv("FEISHU_WEBHOOK_URL", "")).strip()
    template_id = os.getenv("FEISHU_TEMPLATE_ID", "").strip()
    path = Path(state_path) if state_path else DEFAULT_STATE_PATH

    if not url:
        logger.debug("未配置 FEISHU_WEBHOOK_URL，跳过飞书通知")
        return []
    if not template_id:
        logger.warning("未配置 FEISHU_TEMPLATE_ID，跳过飞书通知")
        return []

    current_map = {opportunity_fingerprint(o): o for o in opportunities}
    current_fps = set(current_map.keys())
    last_fps = _load_last_fps(path)
    new_fps = current_fps - last_fps
    new_opps = [current_map[fp] for fp in sorted(new_fps)]

    if not new_opps:
        logger.debug("无新套利机会，跳过飞书通知")
        return []

    # 每条机会单独发一张卡片
    success = True
    for opp in new_opps:
        payload = build_template_card(opp)
        ok = send_feishu_card(url, payload)
        if not ok:
            success = False

    if success:
        _save_last_fps(path, current_fps)
        logger.info("已向飞书推送 %d 个新套利机会", len(new_opps))
    else:
        logger.warning("飞书推送未全部成功，本次不更新去重记录，下次仍会重试")

    return new_opps