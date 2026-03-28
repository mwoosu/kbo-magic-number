#!/usr/bin/env python3
"""Daily KBO dashboard updater for GitHub Actions.

Auto-detects whether the latest active KBO competition is spring training
(`시범경기`) or the regular season (`정규시즌`).

- Exhibition: publish standings only.
- Regular season: crawl live inputs, solve the model, and publish result.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

try:
    import requests
    from bs4 import BeautifulSoup
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError:  # pragma: no cover - dependency availability varies by environment
    requests = None
    BeautifulSoup = None
    webdriver = None
    Service = None
    By = None
    StaleElementReferenceException = None
    Select = None
    WebDriverWait = None

import main


KST = ZoneInfo("Asia/Seoul")
KBO_DAILY_URL = "https://www.koreabaseball.com/Record/TeamRank/TeamRankDaily.aspx"
KBO_SCHEDULE_API = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

TEAM_NAMES = main.TEAMS
TEAM_LABELS = main.TEAM_LABELS
KBO_TO_EN = {
    "삼성": "Samsung",
    "SSG": "SSG",
    "SK": "SSG",
    "롯데": "Lotte",
    "키움": "Kiwoom",
    "두산": "Doosan",
    "KIA": "KIA",
    "LG": "LG",
    "한화": "Hanwha",
    "NC": "NC",
    "KT": "KT",
}


@dataclass
class SeriesSnapshot:
    phase: str
    phase_label: str
    data_date: date
    standings: list[dict]
    versus: dict[str, str] | None = None


def parse_args():
    parser = argparse.ArgumentParser(description="Build the KBO dashboard JSON")
    parser.add_argument("--output", required=True, help="Dashboard JSON output path")
    parser.add_argument("--source-output", help="Optional raw crawl JSON output path")
    parser.add_argument(
        "--phase",
        choices=["auto", "regular", "exhibition"],
        default="auto",
        help="Force a competition phase or auto-detect it",
    )
    parser.add_argument(
        "--historical-standings",
        default="kbo_data22.csv",
        help="Historical standings CSV for prior-year rank fallback",
    )
    return parser.parse_args()


def require_live_dependencies():
    missing = []
    if requests is None:
        missing.append("requests")
    if BeautifulSoup is None:
        missing.append("beautifulsoup4")
    if (
        webdriver is None
        or Service is None
        or By is None
        or Select is None
        or WebDriverWait is None
    ):
        missing.append("selenium")
    if missing:
        raise RuntimeError(
            "live_dashboard.py requires additional packages: "
            + ", ".join(missing)
            + ". Install them first with `pip install "
            + " ".join(missing)
            + "`."
        )


def now_kst():
    return datetime.now(KST)


def normalize_kbo_date(text: str) -> date:
    match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
    if not match:
        raise ValueError(f"could not parse KBO date from {text!r}")
    return datetime.strptime(match.group(1), "%Y.%m.%d").date()


def dotted_date(value: date) -> str:
    return value.strftime("%Y.%m.%d")


def dashed_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def topic_particle(label: str) -> str:
    if not label:
        return "는"
    last = label[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return "은" if (code - 0xAC00) % 28 else "는"
    return "는"


def with_topic(label: str) -> str:
    return f"{label}{topic_particle(label)}"


def ensure_parent(path: str | None):
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def create_browser():
    options = webdriver.ChromeOptions()
    chrome_bin = os.environ.get("CHROME_BIN")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1400")
    options.add_argument("--disable-search-engine-choice-screen")
    options.add_argument(f"--user-agent={USER_AGENT}")
    if chrome_bin:
        options.binary_location = chrome_bin

    service = Service(executable_path=chromedriver_path) if chromedriver_path else Service()
    return webdriver.Chrome(service=service, options=options)


def wait_for_table(browser):
    WebDriverWait(browser, 20).until(
        lambda driver: driver.find_elements(By.CLASS_NAME, "tData") and driver.find_element(By.CLASS_NAME, "date").text
    )


def series_dropdown(browser):
    return Select(browser.find_element(By.CSS_SELECTOR, "[id$='ddlSeries']"))


def selected_series_text(browser):
    return series_dropdown(browser).first_selected_option.text.replace(" ", "")


def select_series(browser, keyword: str):
    options = [option.text.strip() for option in series_dropdown(browser).options]
    for option_text in options:
        if keyword in option_text.replace(" ", ""):
            series_dropdown(browser).select_by_visible_text(option_text)
            WebDriverWait(browser, 20).until(
                lambda driver: keyword in selected_series_text(driver)
            )
            wait_for_table(browser)
            return option_text
    raise ValueError(f"series option containing {keyword!r} not found")


def soup_from_browser(browser):
    return BeautifulSoup(browser.page_source, "html.parser")


def extract_standings(browser) -> list[dict]:
    soup = soup_from_browser(browser)
    tables = soup.select(".tData")
    if not tables:
        raise ValueError("standings table not found")

    table = tables[0]
    rows = []
    for row in table.select("tbody tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cells) < 9:
            continue
        team_name = cells[1]
        if team_name not in KBO_TO_EN:
            continue
        rows.append(
            {
                "rank": int(cells[0]),
                "team_ko": team_name,
                "team": KBO_TO_EN[team_name],
                "games": int(cells[2]),
                "wins": int(cells[3]),
                "losses": int(cells[4]),
                "draws": int(cells[5]),
                "win_pct": float(cells[6]),
                "recent": cells[8],
            }
        )
    if len(rows) != len(TEAM_NAMES):
        raise ValueError(f"expected {len(TEAM_NAMES)} standings rows, got {len(rows)}")
    rows.sort(key=lambda item: item["rank"])
    return rows


def extract_versus(browser) -> dict[str, str]:
    soup = soup_from_browser(browser)
    tables = soup.select(".tData")
    if len(tables) < 2:
        raise ValueError("team-vs-team table not found")

    table = tables[1]
    header_cells = table.select("thead th")[1:11]
    opponents = []
    for cell in header_cells:
        label = cell.get_text("\n", strip=True).split("\n")[0].strip()
        opponents.append(KBO_TO_EN.get(label, label))

    records: dict[str, str] = {}
    for row in table.select("tbody tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cells) < 11:
            continue

        home_label = cells[0]
        home_team = KBO_TO_EN.get(home_label)
        if not home_team:
            continue

        for idx, opponent in enumerate(opponents, start=1):
            value = cells[idx]
            if value == "■" or not value:
                continue
            records[f"{home_team} vs {opponent}"] = value
    return records


def crawl_series(browser, phase: str) -> SeriesSnapshot:
    keyword = "정규" if phase == "regular" else "시범"
    phase_label = "정규시즌" if phase == "regular" else "시범경기"

    select_series(browser, keyword)
    data_date = normalize_kbo_date(browser.find_element(By.CLASS_NAME, "date").text)
    standings = extract_standings(browser)
    versus = extract_versus(browser) if phase == "regular" else None
    return SeriesSnapshot(
        phase=phase,
        phase_label=phase_label,
        data_date=data_date,
        standings=standings,
        versus=versus,
    )


def crawl_series_with_retry(phase: str, attempts: int = 3) -> SeriesSnapshot:
    last_error = None
    for attempt in range(1, attempts + 1):
        browser = create_browser()
        try:
            browser.get(KBO_DAILY_URL)
            wait_for_table(browser)
            return crawl_series(browser, phase)
        except Exception as exc:
            last_error = exc
            is_stale = StaleElementReferenceException and isinstance(exc, StaleElementReferenceException)
            if not is_stale and attempt == attempts:
                raise
            if attempt == attempts:
                raise
            print(f"[WARN] {phase} crawl retry {attempt}/{attempts - 1}: {exc}")
        finally:
            browser.quit()
    raise last_error


def choose_phase(today: date, regular: SeriesSnapshot | None, exhibition: SeriesSnapshot | None, forced: str) -> str:
    if forced != "auto":
        return forced

    candidates: list[tuple[str, int]] = []
    if regular and regular.data_date.year == today.year:
        candidates.append(("regular", abs((today - regular.data_date).days)))
    if exhibition and exhibition.data_date.year == today.year:
        candidates.append(("exhibition", abs((today - exhibition.data_date).days)))

    if not candidates:
        return "offseason"

    candidates.sort(key=lambda item: (item[1], 0 if item[0] == "regular" else 1))
    if candidates[0][1] > 10:
        return "offseason"
    return candidates[0][0]


def parse_triplet(record: str) -> tuple[int, int, int]:
    wins, losses, draws = record.strip().split("-")
    return int(wins), int(losses), int(draws)


def ordered_pairs() -> Iterable[tuple[str, str]]:
    for left_idx, left in enumerate(TEAM_NAMES):
        for right in TEAM_NAMES[left_idx + 1 :]:
            yield left, right


def current_prior_year_rank(csv_path: str, previous_year: int) -> dict[str, int]:
    path = Path(csv_path)
    if not path.exists():
        return {team: index + 1 for index, team in enumerate(TEAM_NAMES)}

    with path.open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    candidate_dates = []
    for row in rows:
        value = row["날짜"]
        if value.startswith(f"{previous_year}.") and value not in candidate_dates:
            candidate_dates.append(value)

    for candidate in reversed(candidate_dates):
        day_rows = [row for row in rows if row["날짜"] == candidate]
        teams = {KBO_TO_EN.get(row["팀명"], row["팀명"]): row for row in day_rows if row["팀명"] in KBO_TO_EN}
        if len(teams) != len(TEAM_NAMES):
            continue
        return {team: int(teams[team]["순위"]) for team in TEAM_NAMES}

    return {team: index + 1 for index, team in enumerate(TEAM_NAMES)}


def _parse_play_cell(html: str):
    """KBO 스케줄 API의 play 셀 HTML을 파싱하여 (원정팀, 원정점수, 홈점수, 홈팀, 완료여부)를 반환."""
    soup = BeautifulSoup(html, "html.parser")
    spans = soup.find_all("span", recursive=False)
    if len(spans) < 2:
        spans = soup.select("em > span")
        team_spans = [s for s in soup.find_all("span", recursive=True) if s.parent.name != "em"]
        if len(team_spans) < 2:
            return None
        away_ko = team_spans[0].get_text(strip=True)
        home_ko = team_spans[-1].get_text(strip=True)
    else:
        away_ko = spans[0].get_text(strip=True)
        home_ko = spans[-1].get_text(strip=True)

    away_team = KBO_TO_EN.get(away_ko)
    home_team = KBO_TO_EN.get(home_ko)
    if not away_team or not home_team:
        return None

    score_spans = soup.select("em > span")
    # 미래 경기: <em><span>vs</span></em> → score_spans == 1개 (점수 없음)
    if len(score_spans) < 3:
        return away_team, 0, 0, home_team, False

    away_cls = score_spans[0].get("class", [])
    away_text = score_spans[0].get_text(strip=True)
    home_text = score_spans[2].get_text(strip=True)

    # win/lose 클래스가 있으면 완료된 경기, same + 0vs0이면 미완료
    completed = "win" in away_cls or "lose" in away_cls
    if not completed and away_text.isdigit() and home_text.isdigit():
        # same 클래스인데 점수가 둘 다 0이 아니면 무승부(완료)
        if int(away_text) > 0 or int(home_text) > 0:
            completed = True

    away_score = int(away_text) if away_text.isdigit() else 0
    home_score = int(home_text) if home_text.isdigit() else 0

    return away_team, away_score, home_score, home_team, completed


def crawl_schedule_snapshot(current_date: date):
    """KBO 공식 스케줄 API에서 정규시즌 경기 데이터를 크롤링."""
    remaining = {(team, other): 0 for team in TEAM_NAMES for other in TEAM_NAMES}
    runs = {(team, other): 0 for team in TEAM_NAMES for other in TEAM_NAMES}

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    year = current_date.year
    for month in range(3, 12):  # 3월~11월
        response = session.post(
            KBO_SCHEDULE_API,
            data={
                "leId": 1,
                "srIdList": "0,9,6",  # 정규시즌
                "seasonId": year,
                "gameMonth": f"{month:02d}",
                "teamId": "",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        current_game_date = None
        for row_obj in data.get("rows", []):
            cells = row_obj.get("row", [])
            for cell in cells:
                if cell.get("Class") == "day":
                    # "03.28(토)" → 날짜 파싱
                    match = re.match(r"(\d{2})\.(\d{2})", cell["Text"])
                    if match:
                        current_game_date = date(year, int(match.group(1)), int(match.group(2)))

                if cell.get("Class") == "play":
                    result = _parse_play_cell(cell["Text"])
                    if not result:
                        continue
                    away_team, away_score, home_score, home_team, completed = result

                    if completed and current_game_date and current_game_date <= current_date:
                        runs[away_team, home_team] += away_score
                        runs[home_team, away_team] += home_score
                    elif not completed or (current_game_date and current_game_date > current_date):
                        remaining[away_team, home_team] += 1
                        remaining[home_team, away_team] += 1

    remaining_matrix = [
        [0 if team == other else remaining[team, other] for other in TEAM_NAMES]
        for team in TEAM_NAMES
    ]
    runs_matrix = [
        [0 if team == other else runs[team, other] for other in TEAM_NAMES]
        for team in TEAM_NAMES
    ]
    return remaining_matrix, runs_matrix


def build_regular_snapshot(series: SeriesSnapshot, historical_csv: str):
    standings_map = {row["team"]: row for row in series.standings}
    if series.versus is None:
        raise ValueError("regular season snapshot is missing the versus table")

    remaining_matrix, runs_matrix = crawl_schedule_snapshot(series.data_date)

    h2h_wins = [[0] * len(TEAM_NAMES) for _ in TEAM_NAMES]
    for home, away in ordered_pairs():
        record = series.versus.get(f"{home} vs {away}")
        if not record:
            continue
        wins, losses, _draws = parse_triplet(record)
        home_idx = TEAM_NAMES.index(home)
        away_idx = TEAM_NAMES.index(away)
        h2h_wins[home_idx][away_idx] = wins
        h2h_wins[away_idx][home_idx] = losses

    prior_year_rank = current_prior_year_rank(historical_csv, series.data_date.year - 1)

    return {
        "date": dashed_date(series.data_date),
        "teams": TEAM_NAMES,
        "wins": [standings_map[team]["wins"] for team in TEAM_NAMES],
        "losses": [standings_map[team]["losses"] for team in TEAM_NAMES],
        "draws": [standings_map[team]["draws"] for team in TEAM_NAMES],
        "current_rank": [standings_map[team]["rank"] for team in TEAM_NAMES],
        "remaining_matrix": remaining_matrix,
        "head_to_head_wins": h2h_wins,
        "head_to_head_runs": runs_matrix,
        "prior_year_rank": [prior_year_rank[team] for team in TEAM_NAMES],
    }


def build_exhibition_output(series: SeriesSnapshot):
    leader = series.standings[0] if series.standings else None
    teams = []
    for row in series.standings:
        if leader:
            gap_from_leader = round(
                ((leader["wins"] - row["wins"]) + (row["losses"] - leader["losses"])) / 2, 1
            )
            if gap_from_leader.is_integer():
                gap_from_leader = int(gap_from_leader)
        else:
            gap_from_leader = None

        if row["rank"] == 1:
            headline = "현재 시범경기 선두권입니다."
        elif gap_from_leader == 0:
            headline = "선두와 승차 없이 붙어 있습니다."
        else:
            headline = f"선두와 {gap_from_leader}경기 차로 시범경기를 치르고 있습니다."

        notes = [
            (
                f"{with_topic(TEAM_LABELS[row['team']])} 현재 {row['rank']}위이며 "
                f"{row['wins']}승 {row['losses']}패 {row['draws']}무를 기록 중입니다."
            ),
            f"최근 흐름은 {row['recent']}입니다.",
            f"시범경기 승률은 {row['win_pct']:.3f}이고, 현재까지 {row['games']}경기를 소화했습니다.",
        ]
        teams.append(
            {
                "rank": row["rank"],
                "team": row["team"],
                "team_label": TEAM_LABELS[row["team"]],
                "current_wins": row["wins"],
                "current_losses": row["losses"],
                "current_draws": row["draws"],
                "games": row["games"],
                "win_pct": round(row["win_pct"], 4),
                "recent": row["recent"],
                "analysis": {
                    "status": "exhibition",
                    "status_label": "시범경기",
                    "headline": headline,
                    "summary": notes[0],
                    "reason": notes[1],
                    "notes": notes,
                    "gap_from_leader": gap_from_leader,
                },
            }
        )

    return {
        "phase": "exhibition",
        "phase_label": series.phase_label,
        "updated_at": now_kst().strftime("%Y-%m-%d %H:%M"),
        "data_date": dashed_date(series.data_date),
        "headline": "정규시즌 개막 전까지 시범경기 순위를 제공합니다.",
        "teams": teams,
    }


def build_offseason_output():
    return {
        "phase": "offseason",
        "phase_label": "비시즌",
        "updated_at": now_kst().strftime("%Y-%m-%d %H:%M"),
        "data_date": None,
        "headline": "현재 활성화된 KBO 경기 데이터가 없습니다.",
        "teams": [],
    }


def main_cli():
    args = parse_args()
    require_live_dependencies()
    today = now_kst().date()

    regular_snapshot = None
    exhibition_snapshot = None

    phases_to_try = ["regular", "exhibition"] if args.phase == "auto" else [args.phase]

    if "regular" in phases_to_try:
        try:
            regular_snapshot = crawl_series_with_retry("regular")
            print(f"[INFO] regular snapshot: {dashed_date(regular_snapshot.data_date)}")
        except Exception as exc:
            print(f"[WARN] regular crawl failed: {exc}")

    if "exhibition" in phases_to_try:
        try:
            exhibition_snapshot = crawl_series_with_retry("exhibition")
            print(f"[INFO] exhibition snapshot: {dashed_date(exhibition_snapshot.data_date)}")
        except Exception as exc:
            print(f"[WARN] exhibition crawl failed: {exc}")

    selected_phase = choose_phase(today, regular_snapshot, exhibition_snapshot, args.phase)
    print(f"[INFO] selected phase: {selected_phase}")

    source_payload = {}
    if selected_phase == "regular":
        if not regular_snapshot:
            raise RuntimeError("regular season was selected but the regular-season crawl did not succeed")
        source_payload = build_regular_snapshot(regular_snapshot, args.historical_standings)
        try:
            output_payload = main.run_model(data=source_payload, show_progress=False)
            output_payload["phase"] = "regular"
            output_payload["phase_label"] = regular_snapshot.phase_label
        except Exception as exc:
            print(f"[WARN] solver failed, falling back to standings-only: {exc}")
            output_payload = build_exhibition_output(regular_snapshot)
            output_payload["phase"] = "regular"
            output_payload["phase_label"] = regular_snapshot.phase_label
    elif selected_phase == "exhibition":
        if not exhibition_snapshot:
            raise RuntimeError("exhibition was selected but the exhibition crawl did not succeed")
        source_payload = {
            "phase": exhibition_snapshot.phase,
            "phase_label": exhibition_snapshot.phase_label,
            "data_date": dashed_date(exhibition_snapshot.data_date),
            "standings": exhibition_snapshot.standings,
        }
        output_payload = build_exhibition_output(exhibition_snapshot)
    else:
        output_payload = build_offseason_output()

    ensure_parent(args.output)
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(output_payload, file, ensure_ascii=False, indent=2)
    print(f"[INFO] dashboard output saved: {args.output}")

    if args.source_output:
        ensure_parent(args.source_output)
        with open(args.source_output, "w", encoding="utf-8") as file:
            json.dump(source_payload, file, ensure_ascii=False, indent=2)
        print(f"[INFO] source snapshot saved: {args.source_output}")


if __name__ == "__main__":
    main_cli()
