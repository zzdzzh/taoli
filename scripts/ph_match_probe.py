"""Prediction Hunt 跨平台体育匹配探测（只读）"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

BASE = "https://www.predictionhunt.com/api/v2"


def fetch_sport(sport: str, api_key: str, retries: int = 3) -> dict | None:
    for attempt in range(1, retries + 1):
        time.sleep(1.2 if attempt == 1 else 2.0 * attempt)
        try:
            r = requests.get(
                f"{BASE}/matching-markets/sports",
                params={"sport": sport},
                headers={"X-API-Key": api_key},
                timeout=40,
            )
        except requests.RequestException as e:
            print(sport, f"ERR attempt={attempt}", e)
            continue
        print(sport, r.status_code)
        if r.status_code == 429:
            time.sleep(2.0)
            continue
        if r.status_code != 200:
            print(r.text[:400])
            return None
        return r.json()
    return None


def summarize(payload: dict, sport: str, max_events: int = 5) -> int:
    games = payload.get("games") or []
    by_event: dict[int, list] = defaultdict(list)
    for g in games:
        by_event[g.get("event_id")].append(g)

    print(
        f"\n######## {sport.upper()}  date={payload.get('date')}  "
        f"raw_rows={len(games)}  events={len(by_event)}"
    )
    shown = 0
    for _eid, rows in by_event.items():
        if shown >= max_events:
            break
        name = rows[0].get("event_name")
        date = rows[0].get("event_date")
        ml = [
            x
            for x in rows
            if (x.get("market_type") or x.get("market_class")) == "moneyline"
        ]
        if not ml:
            continue
        print(f"\n[{date}] {name}")
        for side in ml:
            team = side.get("team") or side.get("game_title")
            markets = side.get("markets") or []
            plats = ", ".join(sorted({m.get("platform", "?") for m in markets}))
            prices = " | ".join(
                f"{m.get('platform')}: ask={m.get('yes_ask')} bid={m.get('yes_bid')}"
                for m in sorted(markets, key=lambda m: m.get("platform") or "")
            )
            print(f"  - {team} ({side.get('side')})  platforms=[{plats}]")
            print(f"    {prices}")
        shown += 1
    return len(by_event)


def main() -> None:
    api_key = os.getenv("PREDICTION_HUNT_API_KEY", "")
    if not api_key:
        raise SystemExit("缺少 PREDICTION_HUNT_API_KEY")

    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)

    # 足球需用联赛码；篮球用 nba/wnba
    sports = ["wnba", "epl", "mlb"]
    for sport in sports:
        data = fetch_sport(sport, api_key)
        if not data:
            continue
        n = summarize(data, sport)
        path = out_dir / f"ph_match_{sport}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  -> saved {path.name} events={n}")


if __name__ == "__main__":
    main()
