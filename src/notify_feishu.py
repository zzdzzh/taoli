"""飞书机器人通知：仅对新出现的套利机会推送（与上次扫描对比去重）"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable

import requests

from .converters import utc_to_china_str
from .models import ArbitrageOpportunity

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = ROOT / "data" / "last_notified_opps.json"


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


def _format_message(opps: list[ArbitrageOpportunity]) -> str:
    header = f"【新套利机会】共 {len(opps)} 个\n"
    bodies = [opp.summary() for opp in opps]
    return header + "\n\n".join(bodies)


def send_feishu_text(webhook_url: str, text: str, timeout: float = 10.0) -> bool:
    """向飞书自定义机器人 webhook 发送文本消息。"""
    try:
        resp = requests.post(
            webhook_url,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=timeout,
        )
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
        ok = send_feishu_text(url, _format_message(new_opps))
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
