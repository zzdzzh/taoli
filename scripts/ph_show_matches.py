"""打印已保存的 Prediction Hunt 匹配结果"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def show(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    games = data.get("games") or []
    by_event: dict = defaultdict(list)
    for g in games:
        by_event[g.get("event_id")].append(g)

    print(f"\n== {path.name} date={data.get('date')} events={len(by_event)} ==")
    for rows in by_event.values():
        ml = [
            x
            for x in rows
            if (x.get("market_type") or x.get("market_class")) == "moneyline"
        ]
        if not ml:
            continue
        print(rows[0].get("event_name"))
        for side in ml:
            markets = sorted(
                side.get("markets") or [],
                key=lambda m: m.get("platform") or "",
            )
            parts = [
                f"{m.get('platform')} ask={m.get('yes_ask')} bid={m.get('yes_bid')}"
                for m in markets
            ]
            print(f"  {side.get('team')}: {' | '.join(parts)}")


def main() -> None:
    for name in ("ph_match_wnba.json", "ph_match_mlb.json", "ph_match_epl.json"):
        path = ROOT / "reports" / name
        if path.exists():
            show(path)


if __name__ == "__main__":
    main()
