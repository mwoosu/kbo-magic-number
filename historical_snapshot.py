#!/usr/bin/env python3
"""Build a main.py input snapshot from historical KBO CSV files."""

import argparse
import csv
import json
import re


TEAMS = ['Samsung', 'SSG', 'Lotte', 'Kiwoom', 'Doosan', 'KIA', 'LG', 'Hanwha', 'NC', 'KT']

KR_TO_EN = {
    '삼성': 'Samsung',
    'SSG': 'SSG',
    '롯데': 'Lotte',
    '키움': 'Kiwoom',
    '두산': 'Doosan',
    'KIA': 'KIA',
    'LG': 'LG',
    '한화': 'Hanwha',
    'NC': 'NC',
    'KT': 'KT',
}

PAIR_RE = re.compile(r'^(?P<left>\w+) vs (?P<right>\w+)$')


def load_rows(path):
    with open(path, encoding='utf-8-sig') as file:
        return list(csv.DictReader(file))


def parse_triplet(value):
    value = (value or '').strip()
    if not value:
        return (0, 0, 0)
    wins, losses, draws = value.split('-')
    return int(wins), int(losses), int(draws)


def dotted_date(value):
    return value.replace('-', '.')


def dashed_date(value):
    return value.replace('.', '-')


def latest_team_rows(rows, date_value):
    team_rows = {}
    for row in rows:
        if row['날짜'] != date_value:
            continue
        team_rows[KR_TO_EN[row['팀명']]] = row
    if len(team_rows) != len(TEAMS):
        raise ValueError(f'{date_value} standings rows are incomplete: {len(team_rows)} teams found')
    return team_rows


def latest_regular_season_date(rows, year_prefix):
    dates = []
    for row in rows:
        date_value = row['날짜']
        if not date_value.startswith(year_prefix):
            continue
        if date_value not in dates:
            dates.append(date_value)

    for date_value in reversed(dates):
        try:
            latest_team_rows(rows, date_value)
            return date_value
        except ValueError:
            continue
    raise ValueError(f'could not find a complete season-end date for {year_prefix}')


def build_snapshot(date_value, standings_path, versus_path, scores_path, final_date=None, prior_year_date=None):
    standings_rows = load_rows(standings_path)
    versus_rows = load_rows(versus_path)
    score_rows = load_rows(scores_path)

    standings_date = dotted_date(date_value)
    standings = latest_team_rows(standings_rows, standings_date)

    versus_by_date = {row['날짜']: row for row in versus_rows}
    scores_by_date = {row['날짜']: row for row in score_rows}

    final_date = dotted_date(final_date) if final_date else versus_rows[-1]['날짜']
    prior_year_date = dotted_date(prior_year_date) if prior_year_date else latest_regular_season_date(
        standings_rows,
        f'{int(standings_date[:4]) - 1}.',
    )

    current_versus = versus_by_date[standings_date]
    final_versus = versus_by_date[final_date]
    current_scores = scores_by_date[standings_date]
    prior_year_rows = latest_team_rows(standings_rows, prior_year_date)

    remaining_matrix = [[0] * len(TEAMS) for _ in TEAMS]
    head_to_head_wins = [[0] * len(TEAMS) for _ in TEAMS]
    head_to_head_runs = [[0] * len(TEAMS) for _ in TEAMS]

    for column, value in current_versus.items():
        if column == '날짜':
            continue

        match = PAIR_RE.match(column)
        if not match:
            continue

        left = match.group('left')
        right = match.group('right')
        left_idx = TEAMS.index(left)
        right_idx = TEAMS.index(right)

        wins, losses, draws = parse_triplet(value)
        final_wins, final_losses, final_draws = parse_triplet(final_versus[column])

        head_to_head_wins[left_idx][right_idx] = wins
        remaining_matrix[left_idx][right_idx] = max(
            (final_wins + final_losses + final_draws) - (wins + losses + draws),
            0,
        )

        runs = (current_scores.get(column) or '').strip()
        head_to_head_runs[left_idx][right_idx] = int(runs) if runs else 0

    for left_idx, left in enumerate(TEAMS):
        for right_idx, right in enumerate(TEAMS):
            if left == right:
                continue
            if remaining_matrix[left_idx][right_idx] != remaining_matrix[right_idx][left_idx]:
                raise ValueError(
                    f'remaining matrix is asymmetric for {left} vs {right}: '
                    f'{remaining_matrix[left_idx][right_idx]} vs {remaining_matrix[right_idx][left_idx]}'
                )

    return {
        'date': dashed_date(standings_date),
        'teams': TEAMS,
        'wins': [int(standings[team]['승']) for team in TEAMS],
        'losses': [int(standings[team]['패']) for team in TEAMS],
        'draws': [int(standings[team]['무']) for team in TEAMS],
        'current_rank': [int(standings[team]['순위']) for team in TEAMS],
        'remaining_matrix': remaining_matrix,
        'head_to_head_wins': head_to_head_wins,
        'head_to_head_runs': head_to_head_runs,
        'prior_year_rank': [int(prior_year_rows[team]['순위']) for team in TEAMS],
    }


def main():
    parser = argparse.ArgumentParser(description='Build a historical KBO snapshot for main.py')
    parser.add_argument('--date', required=True, help='Historical date, e.g. 2025-10-03 or 2025.10.03')
    parser.add_argument('--output', required=True, help='Output JSON path')
    parser.add_argument('--standings', default='kbo_data22.csv', help='Standings CSV path')
    parser.add_argument('--versus', default='kbo_versus.csv', help='Head-to-head CSV path')
    parser.add_argument('--scores', default='kbo_scores.csv', help='Runs-by-matchup CSV path')
    parser.add_argument('--final-date', help='Season-end date in the versus CSV')
    parser.add_argument('--prior-year-date', help='Season-end standings date for prior-year rank')
    args = parser.parse_args()

    snapshot = build_snapshot(
        date_value=args.date,
        standings_path=args.standings,
        versus_path=args.versus,
        scores_path=args.scores,
        final_date=args.final_date,
        prior_year_date=args.prior_year_date,
    )

    with open(args.output, 'w', encoding='utf-8') as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)

    remaining_games = sum(sum(row) for row in snapshot['remaining_matrix']) // 2
    print(f'[INFO] snapshot saved: {args.output}')
    print(f'[INFO] data date: {snapshot["date"]}')
    print(f'[INFO] remaining games: {remaining_games}')


if __name__ == '__main__':
    main()
