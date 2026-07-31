"""跨平台球队名称归一化与比赛匹配"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from .models import MatchOdds

# 常见别名映射（可扩展）
TEAM_ALIASES: dict[str, str] = {
    "man city": "manchester city",
    "man united": "manchester united",
    "man utd": "manchester united",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "inter milan": "inter",
    "ac milan": "milan",
    "atletico madrid": "atletico",
    "athletic bilbao": "athletic club",
    "borussia dortmund": "dortmund",
    "bayern munich": "bayern",
    "rb leipzig": "leipzig",
    "real sociedad": "sociedad",
    "west ham united": "west ham",
    "wolverhampton": "wolves",
    "wolverhampton wanderers": "wolves",
    "newcastle united": "newcastle",
    "nottingham forest": "nottingham",
    "la lakers": "los angeles lakers",
    "la clippers": "los angeles clippers",
    "ny knicks": "new york knicks",
    "gs warriors": "golden state warriors",
    "okc thunder": "oklahoma city thunder",
    "spurs": "san antonio spurs",
    "sixers": "philadelphia 76ers",
    "76ers": "philadelphia 76ers",
    "novak djokovic": "djokovic",
    "carlos alcaraz": "alcaraz",
    "jannik sinner": "sinner",
    # WNBA 城市名 → 完整队名（Kalshi 只返回城市名，Polymarket 返回完整队名）
    "atlanta": "atlanta dream",
    "chicago": "chicago sky",
    "connecticut": "connecticut sun",
    "dallas": "dallas wings",
    "golden state": "golden state valkyries",
    "indiana": "indiana fever",
    "las vegas": "las vegas aces",
    "los angeles": "los angeles sparks",
    "minnesota": "minnesota lynx",
    "new york": "new york liberty",
    "phoenix": "phoenix mercury",
    "portland": "portland fire",
    "portlandfire": "portland fire",
    "seattle": "seattle storm",
    "toronto": "toronto tempo",
    "washington": "washington mystics",
}


def normalize_team(name: str) -> str:
    """归一化球队名用于跨平台匹配"""
    if not name:
        return ""

    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return TEAM_ALIASES.get(text, text)


def parse_vs_title(title: str) -> tuple[str, str] | None:
    """
    从标题解析主客队，支持:
    - "France vs. Spain"
    - "France vs Spain"
    - "England v Argentina"
    - "Geneva Open: Cameron Norrie vs Mariano Navone"
    """
    text = title.strip()
    # 去掉赛事名前缀（冒号须出现在 vs 之前）
    vs_m = re.search(r"\s+vs\.?\s+|\s+v\s+", text, re.IGNORECASE)
    colon = text.find(":")
    if vs_m and colon >= 0 and colon < vs_m.start():
        text = text[colon + 1:].strip()

    patterns = [
        r"^(.+?)\s+vs\.?\s+(.+?)$",
        r"^(.+?)\s+v\s+(.+?)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, text, re.IGNORECASE)
        if m:
            home = m.group(1).strip()
            away = m.group(2).strip()
            # 去掉后缀如 " - Who will advance?"
            away = re.split(r"\s+-\s+", away)[0].strip()
            home = re.split(r"\s+-\s+", home)[0].strip()
            if home and away:
                return home, away
    return None


@dataclass(frozen=True)
class MatchKey:
    """比赛唯一键（用于跨平台合并）"""

    home: str
    away: str

    @classmethod
    def from_match(cls, match: MatchOdds) -> MatchKey:
        return cls(
            home=normalize_team(match.home_team),
            away=normalize_team(match.away_team),
        )

    @classmethod
    def from_teams(
        cls,
        home: str,
        away: str,
        commence_time: datetime = None,
    ) -> MatchKey:
        return cls(
            home=normalize_team(home),
            away=normalize_team(away),
        )


def merge_matches(matches_list: list[list[MatchOdds]]) -> list[MatchOdds]:
    """
    将来自不同平台的比赛赔率合并到同一 MatchOdds。

    按 (归一化主队, 归一化客队, 开赛小时) 匹配，跨来源同时间同队名的比赛合并。
    """
    merged: dict[tuple, MatchOdds] = {}

    for matches in matches_list:
        for match in matches:
            home = normalize_team(match.home_team)
            away = normalize_team(match.away_team)
            hour = match.commence_time.strftime("%Y-%m-%dT%H")
            key = (home, away, hour)

            existing = merged.get(key)
            if existing is None:
                merged[key] = MatchOdds(
                    sport=match.sport,
                    league=match.league,
                    home_team=match.home_team,
                    away_team=match.away_team,
                    commence_time=match.commence_time,
                    quotes=list(match.quotes),
                )
            else:
                existing.quotes.extend(match.quotes)
                if match.commence_time < existing.commence_time:
                    existing.commence_time = match.commence_time

    return list(merged.values())
