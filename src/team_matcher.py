"""跨平台球队名称归一化与比赛匹配"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .models import MatchOdds, OddsQuote

# 通用别名（足球/网球等；勿放单城市名，以免污染 MLB/NBA）
TEAM_ALIASES: dict[str, str] = {
    "man city": "manchester city",
    "man united": "manchester united",
    "man utd": "manchester united",
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
    "novak djokovic": "djokovic",
    "carlos alcaraz": "alcaraz",
    "jannik sinner": "sinner",
    "portlandfire": "portland fire",
}

# WNBA：Kalshi 常用城市名
WNBA_ALIASES: dict[str, str] = {
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
    "seattle": "seattle storm",
    "toronto": "toronto tempo",
    "washington": "washington mystics",
}

# NBA 城市/简称
NBA_ALIASES: dict[str, str] = {
    "la lakers": "los angeles lakers",
    "la clippers": "los angeles clippers",
    "ny knicks": "new york knicks",
    "gs warriors": "golden state warriors",
    "okc thunder": "oklahoma city thunder",
    "spurs": "san antonio spurs",
    "sixers": "philadelphia 76ers",
    "76ers": "philadelphia 76ers",
}

# MLB：Kalshi 常用城市/简称 → 全称（与 Odds API / Polymarket 对齐）
MLB_ALIASES: dict[str, str] = {
    "arizona": "arizona diamondbacks",
    "atlanta": "atlanta braves",
    "baltimore": "baltimore orioles",
    "boston": "boston red sox",
    "chicago c": "chicago cubs",
    "chicago w": "chicago white sox",
    "chicago cubs": "chicago cubs",
    "chicago white sox": "chicago white sox",
    "cincinnati": "cincinnati reds",
    "cleveland": "cleveland guardians",
    "colorado": "colorado rockies",
    "detroit": "detroit tigers",
    "houston": "houston astros",
    "kansas city": "kansas city royals",
    "los angeles a": "los angeles angels",
    "los angeles d": "los angeles dodgers",
    "la angels": "los angeles angels",
    "la dodgers": "los angeles dodgers",
    "miami": "miami marlins",
    "milwaukee": "milwaukee brewers",
    "minnesota": "minnesota twins",
    "new york m": "new york mets",
    "new york y": "new york yankees",
    "ny mets": "new york mets",
    "ny yankees": "new york yankees",
    "athletics": "oakland athletics",
    "oakland": "oakland athletics",
    "as": "oakland athletics",
    "a s": "oakland athletics",
    "philadelphia": "philadelphia phillies",
    "pittsburgh": "pittsburgh pirates",
    "san diego": "san diego padres",
    "san francisco": "san francisco giants",
    "seattle": "seattle mariners",
    "st louis": "st louis cardinals",
    "tampa bay": "tampa bay rays",
    "texas": "texas rangers",
    "toronto": "toronto blue jays",
    "washington": "washington nationals",
}

# 合并时允许的开赛时间差（秒）；跨源常有 endDate/估算偏差
MERGE_TIME_TOLERANCE_SEC = 4 * 3600


def _alias_bucket(sport: str = "", league: str = "") -> str:
    s = f"{sport} {league}".lower()
    if "wnba" in s:
        return "wnba"
    if "mlb" in s or "baseball" in s:
        return "mlb"
    if "nba" in s and "wnba" not in s:
        return "nba"
    return "default"


def normalize_team(name: str, sport: str = "", league: str = "") -> str:
    """归一化球队名用于跨平台匹配"""
    if not name:
        return ""

    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    # Kalshi 标题残留 "Winner?"
    text = re.sub(r"\s*winner\??$", "", text).strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    bucket = _alias_bucket(sport, league)
    if bucket == "wnba":
        text = WNBA_ALIASES.get(text, text)
    elif bucket == "mlb":
        text = MLB_ALIASES.get(text, text)
    elif bucket == "nba":
        text = NBA_ALIASES.get(text, text)

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
            away = re.sub(r"\s*Winner\??$", "", away, flags=re.I).strip()
            home = re.sub(r"\s*Winner\??$", "", home, flags=re.I).strip()
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
            home=normalize_team(match.home_team, match.sport, match.league),
            away=normalize_team(match.away_team, match.sport, match.league),
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


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _flip_quote(q: OddsQuote) -> OddsQuote:
    """主客对调时翻转 home/away（平局不变）"""
    if q.outcome == "home":
        return replace(q, outcome="away")
    if q.outcome == "away":
        return replace(q, outcome="home")
    return q


def _is_prediction_only(match: MatchOdds) -> bool:
    pred = {"polymarket", "kalshi", "myriad"}
    if not match.quotes:
        return True
    return all(q.bookmaker in pred for q in match.quotes)


def _has_sportsbook(match: MatchOdds) -> bool:
    pred = {"polymarket", "kalshi", "myriad"}
    return any(q.bookmaker not in pred for q in match.quotes)


def merge_matches(matches_list: list[list[MatchOdds]]) -> list[MatchOdds]:
    """
    将来自不同平台的比赛赔率合并到同一 MatchOdds。

    匹配规则：
    - 归一化队名相同，或主客对调相同
    - 开赛时间差在 MERGE_TIME_TOLERANCE_SEC 内（默认 4 小时）
    主客对调时自动翻转 home/away 赔率腿；身份优先用博彩公司队名/时间。
    """
    merged: list[MatchOdds] = []

    for matches in matches_list:
        for match in matches:
            h = normalize_team(match.home_team, match.sport, match.league)
            a = normalize_team(match.away_team, match.sport, match.league)
            if not h or not a:
                continue
            t = _to_utc(match.commence_time)

            found: MatchOdds | None = None
            flipped = False
            for ex in merged:
                eh = normalize_team(ex.home_team, ex.sport, ex.league)
                ea = normalize_team(ex.away_team, ex.sport, ex.league)
                et = _to_utc(ex.commence_time)
                if abs((t - et).total_seconds()) > MERGE_TIME_TOLERANCE_SEC:
                    continue
                if eh == h and ea == a:
                    found, flipped = ex, False
                    break
                if eh == a and ea == h:
                    found, flipped = ex, True
                    break

            if found is None:
                merged.append(
                    MatchOdds(
                        sport=match.sport,
                        league=match.league,
                        home_team=match.home_team,
                        away_team=match.away_team,
                        commence_time=match.commence_time,
                        quotes=list(match.quotes),
                    )
                )
                continue

            # 已有记录全是预测盘、新来的是博彩 → 改用博彩的主客与开赛时间
            adopt = _is_prediction_only(found) and _has_sportsbook(match)
            if adopt:
                if flipped:
                    # found=A vs B，incoming=B vs A；改身份为 B vs A，旧报价需翻转
                    found.quotes = [_flip_quote(q) for q in found.quotes]
                found.home_team = match.home_team
                found.away_team = match.away_team
                found.commence_time = match.commence_time
                found.sport = match.sport
                found.league = match.league
                found.quotes.extend(match.quotes)
            else:
                quotes = (
                    [_flip_quote(q) for q in match.quotes]
                    if flipped
                    else list(match.quotes)
                )
                found.quotes.extend(quotes)

    return merged
