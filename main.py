#!/usr/bin/env python3
"""KBO 포스트시즌 매직넘버 계산기

Kim et al. (2024) "Improving South Korea's Crystal Ball for Baseball
Postseason Clinching and Elimination" 기반 MILP 모델.

Usage:
    python main.py                          # 콘솔 출력
    python main.py --output docs/data/result.json  # JSON 저장
    python main.py --team Samsung           # 특정 팀만 계산
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB


# ============================================================
# Gurobi 환경 설정 (WLS 자동 감지)
# ============================================================

def load_wls_credentials_from_file():
    """현재 작업 디렉터리 또는 GRB_LICENSE_FILE의 gurobi.lic에서 WLS 자격증명을 읽는다."""
    candidates = []

    env_path = os.environ.get('GRB_LICENSE_FILE')
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / 'gurobi.lic')

    for path in candidates:
        if not path.exists():
            continue

        values = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()

        if {'WLSACCESSID', 'WLSSECRET', 'LICENSEID'} <= values.keys():
            return values

    return None


def create_gurobi_env():
    """WLS 환경변수가 있으면 WLS 라이선스, 아니면 로컬 라이선스 사용."""
    wls_access_id = os.environ.get('GRB_WLSACCESSID')
    wls_secret = os.environ.get('GRB_WLSSECRET')
    license_id = os.environ.get('GRB_LICENSEID')

    if not (wls_access_id and wls_secret and license_id):
        file_values = load_wls_credentials_from_file()
        if file_values:
            wls_access_id = file_values['WLSACCESSID']
            wls_secret = file_values['WLSSECRET']
            license_id = file_values['LICENSEID']

    env = gp.Env(empty=True)

    if wls_access_id and wls_secret and license_id:
        print("[INFO] Gurobi WLS 라이선스 사용")
        env.setParam('WLSACCESSID', wls_access_id)
        env.setParam('WLSSECRET', wls_secret)
        env.setParam('LICENSEID', int(license_id))

    env.start()
    return env


# ============================================================
# 데이터 정의 (더미 데이터 — 추후 크롤러 JSON으로 교체)
# ============================================================

# fmt: off
TEAMS = ['Samsung', 'SSG', 'Lotte', 'Kiwoom', 'Doosan', 'KIA', 'LG', 'Hanwha', 'NC', 'KT']

TEAM_LABELS = {
    'Samsung': '삼성', 'SSG': 'SSG', 'Lotte': '롯데', 'Kiwoom': '키움',
    'Doosan': '두산', 'KIA': 'KIA', 'LG': 'LG', 'Hanwha': '한화',
    'NC': 'NC', 'KT': 'KT',
}

N_PLAYOFF = 5  # 포스트시즌 진출 팀 수

DEFAULT_DATA = {
    "date": "2025-08-15",
    "teams": TEAMS,
    "wins":   [49, 38, 56, 67, 58, 59, 62, 31, 63, 62],
    "losses": [60, 74, 51, 48, 49, 49, 47, 78, 42, 47],
    "draws":  [2,  1,  1,  1,  4,  0,  3,  2,  3,  1],
    "remaining_matrix": [
        [0, 6, 3, 1, 2, 2, 3, 4, 8, 4],
        [6, 0, 4, 5, 3, 3, 3, 0, 3, 4],
        [3, 4, 0, 0, 2, 3, 6, 5, 7, 6],
        [1, 5, 0, 0, 8, 5, 0, 3, 3, 3],
        [2, 3, 2, 8, 0, 4, 1, 9, 0, 4],
        [2, 3, 3, 5, 4, 0, 4, 6, 5, 4],
        [3, 3, 6, 0, 1, 4, 0, 1, 7, 7],
        [4, 0, 5, 3, 9, 6, 1, 0, 3, 2],
        [8, 3, 7, 3, 0, 5, 7, 3, 0, 0],
        [4, 4, 6, 3, 4, 4, 7, 2, 0, 0],
    ],
    "head_to_head_wins": None,   # 10x10, None이면 0으로 초기화
    "head_to_head_runs": None,   # 10x10, None이면 0으로 초기화
    "prior_year_rank": [2, 8, 7, 9, 6, 1, 3, 10, 5, 4],
}
# fmt: on


def normalize_data(data):
    """JSON 호환 입력(dict)을 solver 내부 포맷으로 변환."""
    teams = data['teams']
    n = len(teams)

    w_hat = dict(zip(teams, data['wins']))
    l_hat = dict(zip(teams, data['losses']))
    i_hat = dict(zip(teams, data['draws']))

    g = {}
    for i_idx, i_team in enumerate(teams):
        for j_idx, j_team in enumerate(teams):
            g[i_team, j_team] = data['remaining_matrix'][i_idx][j_idx]

    w_data = {}
    h2h = data.get('head_to_head_wins')
    for i_idx, t in enumerate(teams):
        for j_idx, tp in enumerate(teams):
            w_data[t, tp] = h2h[i_idx][j_idx] if h2h else 0

    r_hat = {}
    h2r = data.get('head_to_head_runs')
    for i_idx, t in enumerate(teams):
        for j_idx, tp in enumerate(teams):
            r_hat[t, tp] = h2r[i_idx][j_idx] if h2r else 0

    p = dict(zip(teams, data.get('prior_year_rank', list(range(1, n + 1)))))

    return {
        'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
        'teams': teams,
        'w_hat': w_hat, 'l_hat': l_hat, 'i_hat': i_hat,
        'g': g, 'w_data': w_data, 'r_hat': r_hat, 'p': p,
    }


def load_data(input_path=None):
    """입력 데이터 로드. JSON 파일이 있으면 읽고, 없으면 DEFAULT_DATA 사용."""
    if input_path and os.path.exists(input_path):
        print(f"[INFO] 입력 데이터: {input_path}")
        with open(input_path) as f:
            data = json.load(f)
    else:
        print("[INFO] 기본 더미 데이터 사용")
        data = DEFAULT_DATA.copy()

    return normalize_data(data)


# ============================================================
# 매직넘버 계산 (단일 팀)
# ============================================================

def solve_magic_number(env, data, target_team, verbose=False):
    """target_team의 포스트시즌 진출 최소 승수(매직넘버) 계산.

    Returns:
        dict with keys: team, magic_number, min_wins, eliminated, current_wins,
                        final_standings (list of dicts)
    """
    teams = data['teams']
    k = target_team
    T_k = [t for t in teams if t != k]
    pairs = [(teams[i], teams[j]) for i in range(len(teams)) for j in range(i + 1, len(teams))]
    team_index = {team: idx for idx, team in enumerate(teams)}

    def ordered_pair(team_a, team_b):
        if team_index[team_a] < team_index[team_b]:
            return (team_a, team_b)
        return (team_b, team_a)

    w_hat = data['w_hat']
    l_hat = data['l_hat']
    i_hat = data['i_hat']
    g = data['g']
    w_data = data['w_data']
    r_hat = data['r_hat']
    p = data['p']

    R = [1, 2, 3]
    max_draws = 20
    i_bar = 14
    n_playoff = N_PLAYOFF

    # --- 모델 생성 ---
    model = gp.Model(env=env)
    model.Params.NonConvex = 2
    model.Params.DualReductions = 0
    model.Params.OutputFlag = 1 if verbose else 0

    # --- 변수 ---
    N = model.addVars(teams, vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name='N')
    X = model.addVars(teams, teams, vtype=GRB.INTEGER, lb=0, name='X')
    Y = model.addVars(teams, teams, vtype=GRB.INTEGER, lb=0, name='Y')
    A = model.addVars(teams, teams, vtype=GRB.INTEGER, lb=0, name='A')
    W = model.addVars(teams, vtype=GRB.INTEGER, name='W')
    L = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='L')
    I = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='I')
    G = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='G')
    R_var = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='R')
    alpha = model.addVars(teams, teams, vtype=GRB.BINARY, name='alpha')
    beta = model.addVars(teams, teams, vtype=GRB.BINARY, name='beta')
    omega = model.addVars(teams, teams, vtype=GRB.BINARY, name='omega')
    I_hat_0 = model.addVar(vtype=GRB.BINARY, name='I_hat_0')
    I_hat_1 = model.addVar(vtype=GRB.BINARY, name='I_hat_1')
    T_crit = model.addVars(teams, teams, R, vtype=GRB.BINARY, name='T')
    tau = model.addVars(teams, max_draws, vtype=GRB.BINARY, name='tau')
    Z = model.addVars(teams, vtype=GRB.BINARY, name='Z')
    Z_hat = model.addVars(teams, teams, vtype=GRB.BINARY, name='Z_hat')

    # === A.1 목적함수 ===
    model.setObjective(W[k], GRB.MINIMIZE)

    # === A.2 Games and Results ===
    model.addConstrs((X[i, j] + X[j, i] + Y[i, j] == g[i, j] for (i, j) in pairs), name="A.2a")
    model.addConstrs((W[i] == w_hat[i] + gp.quicksum(X[i, j] for j in teams if i != j) for i in teams), name="A.2b")
    model.addConstrs((L[i] == l_hat[i] + gp.quicksum(X[j, i] for j in teams if i != j) for i in teams), name="A.2c")
    model.addConstrs((I[i] == i_hat[i] + gp.quicksum(Y[i, j] for j in teams if i != j) for i in teams), name="A.2d")
    model.addConstrs((Y[i, j] == Y[j, i] for (i, j) in pairs), name="A.2e")

    # === A.3 Win Percentage ===
    model.addConstrs((N[i] * (W[i] + L[i]) == W[i] for i in teams), name="A.3")

    # === A.4 Drawn Games ===
    model.addConstrs((I[i] == gp.quicksum(j * tau[i, j] for j in range(max_draws)) for i in teams), name="A.4a")
    model.addConstrs((gp.quicksum(tau[i, j] for j in range(max_draws)) == 1 for i in teams), name="A.4b")
    model.addConstrs((I[i] <= max(i_bar, i_hat[i]) for i in teams), name="A.4c")

    # === A.5 Tie Indicators ===
    T_k_size = len(T_k)
    model.addConstr(I_hat_0 + I_hat_1 <= 1, name="A.5a")
    model.addConstr(2 * (1 - I_hat_0) - I_hat_1 <= gp.quicksum(Z[t] for t in T_k), name="A.5b")
    model.addConstr(gp.quicksum(Z[t] for t in T_k) <= T_k_size - (T_k_size - 1) * I_hat_1, name="A.5c")
    model.addConstr(gp.quicksum(Z[t] for t in T_k) <= T_k_size * (1 - I_hat_0), name="A.5d")

    # === A.6 Ties in the Standings ===
    m = 1 / (144 * 143)
    model.addConstrs((alpha[t, k] + alpha[k, t] == Z[t] for t in T_k), name="A.6a")
    model.addConstrs((T_crit[t, k, r] + T_crit[k, t, r] <= 1 for t in T_k for r in R), name="A.6b")
    model.addConstrs((1 - Z[t] >= N[t] - N[k] for t in T_k), name="A.6c1")
    model.addConstrs((1 - Z[t] >= N[k] - N[t] for t in T_k), name="A.6c2")
    model.addConstrs((m - (N[t] - N[k]) <= Z[t] + (1 + m) * beta[k, t] for t in T_k), name="A.6d")
    model.addConstrs((m - (N[k] - N[t]) <= Z[t] + (1 + m) * beta[t, k] for t in T_k), name="A.6e")
    model.addConstrs((m - (N[k] - N[t]) <= Z[t] + (1 + m) * (1 - beta[k, t]) for t in T_k), name="A.6f")
    model.addConstrs((m - (N[t] - N[k]) <= Z[t] + (1 + m) * (1 - beta[t, k]) for t in T_k), name="A.6g")
    model.addConstrs((Z[t] + beta[k, t] + beta[t, k] == 1 for t in T_k), name="A.6h")
    model.addConstrs((Z_hat[i, i] == 0 for i in teams), name="A.6i_diag")
    model.addConstrs((Z_hat[i, j] == Z_hat[j, i] for (i, j) in pairs), name="A.6i_sym")
    model.addConstrs((Z[i] + Z[j] <= Z_hat[i, j] + 1 for (i, j) in pairs), name="A.6i")
    model.addConstrs((2 * Z_hat[i, j] + beta[k, i] + beta[i, k] + beta[k, j] + beta[j, k] <= 2 for (i, j) in pairs), name="A.6j")

    # === A.7 + A.14a~d 타이브레이크 기준1 (상대 다승) ===
    M_G = {t: sum(w_data[t, tp] + g[t, tp] for tp in teams if tp != t) for t in teams}
    M_G_pair = {(t, tp): M_G[t] + M_G[tp] + 1 for t in teams for tp in teams if t != tp}

    model.addConstr(G[k] == gp.quicksum((w_data[k, t] + X[k, t]) * Z[t] for t in T_k), name="A.14a")
    model.addConstrs((G[t] == (w_data[t, k] + X[t, k]) * Z[t] + gp.quicksum((w_data[t, tp] + X[t, tp]) * Z_hat[ordered_pair(t, tp)] for tp in T_k if tp != t) for t in T_k), name="A.14b")
    model.addConstr(G[k] <= gp.quicksum(w_data[k, t] + g[k, t] for t in T_k), name="A.14c")
    model.addConstrs((G[t] <= M_G[t] * Z[t] for t in T_k), name="A.14d")

    model.addConstrs((
        G[t] - G[tp] >= 1 - M_G_pair[t, tp] * (1 - T_crit[t, tp, 1]) - M_G_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.7b_lb")
    model.addConstrs((
        G[t] - G[tp] <= M_G_pair[t, tp] * T_crit[t, tp, 1] + M_G_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.7b_ub")

    # === A.8 + A.14 변형 타이브레이크 기준2 (상대 다득점) ===
    M_R = {t: sum(r_hat[t, tp] for tp in teams if tp != t) + 1000 for t in teams}
    M_R_pair = {(t, tp): M_R[t] + M_R[tp] + 1 for t in teams for tp in teams if t != tp}

    model.addConstr(R_var[k] == gp.quicksum((r_hat[k, t] + A[k, t]) * Z[t] for t in T_k), name="A.14a_R")
    model.addConstrs((R_var[t] == (r_hat[t, k] + A[t, k]) * Z[t] + gp.quicksum((r_hat[t, tp] + A[t, tp]) * Z_hat[ordered_pair(t, tp)] for tp in T_k if tp != t) for t in T_k), name="A.14b_R")
    model.addConstr(R_var[k] <= gp.quicksum(r_hat[k, t] + 1000 for t in T_k), name="A.14c_R")
    model.addConstrs((R_var[t] <= M_R[t] * Z[t] for t in T_k), name="A.14d_R")

    model.addConstrs((
        R_var[t] - R_var[tp] >= 1 - M_R_pair[t, tp] * (1 - T_crit[t, tp, 2]) - M_R_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.8b_lb")
    model.addConstrs((
        R_var[t] - R_var[tp] <= M_R_pair[t, tp] * T_crit[t, tp, 2] + M_R_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.8b_ub")

    # === A.9 완결 시리즈 고정 ===
    F = [(t, tp) for (t, tp) in pairs if g[t, tp] == 0]
    for (t, tp) in F:
        if w_data[t, tp] > w_data[tp, t]:
            model.addConstr(T_crit[t, tp, 1] == 1, name=f"A.9a_{t}_{tp}")
        elif w_data[t, tp] < w_data[tp, t]:
            model.addConstr(T_crit[tp, t, 1] == 1, name=f"A.9a_{tp}_{t}")
        else:
            model.addConstr(T_crit[t, tp, 1] == 0, name=f"A.9b1_{t}_{tp}")
            model.addConstr(T_crit[tp, t, 1] == 0, name=f"A.9b2_{t}_{tp}")

        if r_hat[t, tp] > r_hat[tp, t]:
            model.addConstr(T_crit[t, tp, 2] == 1, name=f"A.9c_{t}_{tp}")
        elif r_hat[t, tp] < r_hat[tp, t]:
            model.addConstr(T_crit[tp, t, 2] == 1, name=f"A.9c_{tp}_{t}")
        else:
            model.addConstr(T_crit[t, tp, 2] == 0, name=f"A.9d1_{t}_{tp}")
            model.addConstr(T_crit[tp, t, 2] == 0, name=f"A.9d2_{t}_{tp}")

    # === A.10a~c 기준 위계 ===
    R_size = len(R)

    for (t, tp) in pairs:
        if p[t] < p[tp]:
            model.addConstr(T_crit[t, tp, 3] == 1, name=f"A.10c_{t}_{tp}")
            model.addConstr(T_crit[tp, t, 3] == 0, name=f"A.10c_{tp}_{t}")
        else:
            model.addConstr(T_crit[tp, t, 3] == 1, name=f"A.10c_{tp}_{t}")
            model.addConstr(T_crit[t, tp, 3] == 0, name=f"A.10c_{t}_{tp}")

    model.addConstrs((
        2 ** (R_size + 1) * (1 - Z[t])
        + gp.quicksum(2 ** (R_size - r) * T_crit[t, k, r] for r in R)
        + 2 ** R_size * alpha[k, t]
        >= gp.quicksum(2 ** (R_size - r) * T_crit[k, t, r] for r in R)
        for t in T_k), name="A.10a")

    model.addConstrs((
        2 ** (R_size + 1) * (1 - Z[t])
        + gp.quicksum(2 ** (R_size - r) * T_crit[k, t, r] for r in R)
        + 2 ** R_size * alpha[t, k]
        >= gp.quicksum(2 ** (R_size - r) * T_crit[t, k, r] for r in R)
        for t in T_k), name="A.10b")

    # === A.11 Team Ordering ===
    model.addConstrs((omega[i, j] + omega[j, i] == 1 for (i, j) in pairs), name="A.11")

    # === A.12 Postseason Elimination ===
    model.addConstr(gp.quicksum(beta[t, k] for t in T_k) <= n_playoff - 1, name="A.12a")
    model.addConstrs((N[k] + omega[t, k] >= N[t] + alpha[t, k] for t in T_k), name="A.12b")
    model.addConstrs((N[t] + omega[k, t] >= N[k] + alpha[k, t] for t in T_k), name="A.12b_rev")
    model.addConstr(gp.quicksum(omega[t, k] for t in T_k) <= n_playoff - 1 + I_hat_1, name="A.12c")

    # === 최적화 ===
    model.optimize()

    # === 결과 정리 ===
    result = {
        'team': k,
        'team_label': TEAM_LABELS.get(k, k),
        'current_wins': w_hat[k],
        'current_losses': l_hat[k],
        'current_draws': i_hat[k],
        'remaining_games': sum(g[k, j] for j in teams if j != k),
    }

    if model.status == GRB.INFEASIBLE:
        result['eliminated'] = True
        result['min_wins'] = None
        result['magic_number'] = None
    elif model.status == GRB.OPTIMAL:
        result['eliminated'] = False
        result['min_wins'] = int(round(W[k].X))
        result['magic_number'] = int(round(W[k].X)) - w_hat[k]
        result['win_pct'] = round(N[k].X, 4)
    else:
        result['eliminated'] = None
        result['min_wins'] = None
        result['magic_number'] = None
        result['solver_status'] = model.status

    model.dispose()
    return result


def solve_clinch_number(env, data, target_team, verbose=False):
    """target_team의 포스트시즌 확정(clinch)에 필요한 추가 승수 계산.

    원리: W[k]를 MAXIMIZE하면서 "k가 5위 밖으로 밀려나는" 시나리오를 찾음.
    - Infeasible → k를 밀어낼 방법이 없음 → 이미 확정!
    - Optimal W[k] = w* → w*승까지 해도 탈락 가능 → (w*+1)승 하면 확정
      → clinch_number = w* + 1 - 현재승

    Returns:
        dict with keys: clinched, clinch_number, clinch_wins
    """
    teams = data['teams']
    k = target_team
    T_k = [t for t in teams if t != k]
    pairs = [(teams[i], teams[j]) for i in range(len(teams)) for j in range(i + 1, len(teams))]
    team_index = {team: idx for idx, team in enumerate(teams)}

    def ordered_pair(team_a, team_b):
        if team_index[team_a] < team_index[team_b]:
            return (team_a, team_b)
        return (team_b, team_a)

    w_hat = data['w_hat']
    l_hat = data['l_hat']
    i_hat = data['i_hat']
    g = data['g']
    w_data = data['w_data']
    r_hat = data['r_hat']
    p = data['p']

    R = [1, 2, 3]
    max_draws = 20
    i_bar = 14
    n_playoff = N_PLAYOFF

    model = gp.Model(env=env)
    model.Params.NonConvex = 2
    model.Params.DualReductions = 0
    model.Params.OutputFlag = 1 if verbose else 0

    # --- 변수 (탈락 모델과 동일) ---
    N = model.addVars(teams, vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name='N')
    X = model.addVars(teams, teams, vtype=GRB.INTEGER, lb=0, name='X')
    Y = model.addVars(teams, teams, vtype=GRB.INTEGER, lb=0, name='Y')
    A = model.addVars(teams, teams, vtype=GRB.INTEGER, lb=0, name='A')
    W = model.addVars(teams, vtype=GRB.INTEGER, name='W')
    L = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='L')
    I = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='I')
    G = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='G')
    R_var = model.addVars(teams, vtype=GRB.INTEGER, lb=0, name='R')
    alpha = model.addVars(teams, teams, vtype=GRB.BINARY, name='alpha')
    beta = model.addVars(teams, teams, vtype=GRB.BINARY, name='beta')
    omega = model.addVars(teams, teams, vtype=GRB.BINARY, name='omega')
    I_hat_0 = model.addVar(vtype=GRB.BINARY, name='I_hat_0')
    I_hat_1 = model.addVar(vtype=GRB.BINARY, name='I_hat_1')
    T_crit = model.addVars(teams, teams, R, vtype=GRB.BINARY, name='T')
    tau = model.addVars(teams, max_draws, vtype=GRB.BINARY, name='tau')
    Z = model.addVars(teams, vtype=GRB.BINARY, name='Z')
    Z_hat = model.addVars(teams, teams, vtype=GRB.BINARY, name='Z_hat')

    # === 목적함수: MAXIMIZE W[k] (최대한 많이 이기고도 탈락하는 시나리오) ===
    model.setObjective(W[k], GRB.MAXIMIZE)

    # === A.2~A.4 (게임 제약 — 동일) ===
    model.addConstrs((X[i, j] + X[j, i] + Y[i, j] == g[i, j] for (i, j) in pairs), name="A.2a")
    model.addConstrs((W[i] == w_hat[i] + gp.quicksum(X[i, j] for j in teams if i != j) for i in teams), name="A.2b")
    model.addConstrs((L[i] == l_hat[i] + gp.quicksum(X[j, i] for j in teams if i != j) for i in teams), name="A.2c")
    model.addConstrs((I[i] == i_hat[i] + gp.quicksum(Y[i, j] for j in teams if i != j) for i in teams), name="A.2d")
    model.addConstrs((Y[i, j] == Y[j, i] for (i, j) in pairs), name="A.2e")
    model.addConstrs((N[i] * (W[i] + L[i]) == W[i] for i in teams), name="A.3")
    model.addConstrs((I[i] == gp.quicksum(j * tau[i, j] for j in range(max_draws)) for i in teams), name="A.4a")
    model.addConstrs((gp.quicksum(tau[i, j] for j in range(max_draws)) == 1 for i in teams), name="A.4b")
    model.addConstrs((I[i] <= max(i_bar, i_hat[i]) for i in teams), name="A.4c")

    # === A.5~A.6 (동률 제약 — 동일) ===
    T_k_size = len(T_k)
    model.addConstr(I_hat_0 + I_hat_1 <= 1, name="A.5a")
    model.addConstr(2 * (1 - I_hat_0) - I_hat_1 <= gp.quicksum(Z[t] for t in T_k), name="A.5b")
    model.addConstr(gp.quicksum(Z[t] for t in T_k) <= T_k_size - (T_k_size - 1) * I_hat_1, name="A.5c")
    model.addConstr(gp.quicksum(Z[t] for t in T_k) <= T_k_size * (1 - I_hat_0), name="A.5d")

    m = 1 / (144 * 143)
    model.addConstrs((alpha[t, k] + alpha[k, t] == Z[t] for t in T_k), name="A.6a")
    model.addConstrs((T_crit[t, k, r] + T_crit[k, t, r] <= 1 for t in T_k for r in R), name="A.6b")
    model.addConstrs((1 - Z[t] >= N[t] - N[k] for t in T_k), name="A.6c1")
    model.addConstrs((1 - Z[t] >= N[k] - N[t] for t in T_k), name="A.6c2")
    model.addConstrs((m - (N[t] - N[k]) <= Z[t] + (1 + m) * beta[k, t] for t in T_k), name="A.6d")
    model.addConstrs((m - (N[k] - N[t]) <= Z[t] + (1 + m) * beta[t, k] for t in T_k), name="A.6e")
    model.addConstrs((m - (N[k] - N[t]) <= Z[t] + (1 + m) * (1 - beta[k, t]) for t in T_k), name="A.6f")
    model.addConstrs((m - (N[t] - N[k]) <= Z[t] + (1 + m) * (1 - beta[t, k]) for t in T_k), name="A.6g")
    model.addConstrs((Z[t] + beta[k, t] + beta[t, k] == 1 for t in T_k), name="A.6h")
    model.addConstrs((Z_hat[i, i] == 0 for i in teams), name="A.6i_diag")
    model.addConstrs((Z_hat[i, j] == Z_hat[j, i] for (i, j) in pairs), name="A.6i_sym")
    model.addConstrs((Z[i] + Z[j] <= Z_hat[i, j] + 1 for (i, j) in pairs), name="A.6i")
    model.addConstrs((2 * Z_hat[i, j] + beta[k, i] + beta[i, k] + beta[k, j] + beta[j, k] <= 2 for (i, j) in pairs), name="A.6j")

    # === A.7~A.10 (타이브레이크 — 동일) ===
    M_G = {t: sum(w_data[t, tp] + g[t, tp] for tp in teams if tp != t) for t in teams}
    M_G_pair = {(t, tp): M_G[t] + M_G[tp] + 1 for t in teams for tp in teams if t != tp}
    model.addConstr(G[k] == gp.quicksum((w_data[k, t] + X[k, t]) * Z[t] for t in T_k), name="A.14a")
    model.addConstrs((G[t] == (w_data[t, k] + X[t, k]) * Z[t] + gp.quicksum((w_data[t, tp] + X[t, tp]) * Z_hat[ordered_pair(t, tp)] for tp in T_k if tp != t) for t in T_k), name="A.14b")
    model.addConstr(G[k] <= gp.quicksum(w_data[k, t] + g[k, t] for t in T_k), name="A.14c")
    model.addConstrs((G[t] <= M_G[t] * Z[t] for t in T_k), name="A.14d")
    model.addConstrs((
        G[t] - G[tp] >= 1 - M_G_pair[t, tp] * (1 - T_crit[t, tp, 1]) - M_G_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.7b_lb")
    model.addConstrs((
        G[t] - G[tp] <= M_G_pair[t, tp] * T_crit[t, tp, 1] + M_G_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.7b_ub")

    M_R = {t: sum(r_hat[t, tp] for tp in teams if tp != t) + 1000 for t in teams}
    M_R_pair = {(t, tp): M_R[t] + M_R[tp] + 1 for t in teams for tp in teams if t != tp}
    model.addConstr(R_var[k] == gp.quicksum((r_hat[k, t] + A[k, t]) * Z[t] for t in T_k), name="A.14a_R")
    model.addConstrs((R_var[t] == (r_hat[t, k] + A[t, k]) * Z[t] + gp.quicksum((r_hat[t, tp] + A[t, tp]) * Z_hat[ordered_pair(t, tp)] for tp in T_k if tp != t) for t in T_k), name="A.14b_R")
    model.addConstr(R_var[k] <= gp.quicksum(r_hat[k, t] + 1000 for t in T_k), name="A.14c_R")
    model.addConstrs((R_var[t] <= M_R[t] * Z[t] for t in T_k), name="A.14d_R")
    model.addConstrs((
        R_var[t] - R_var[tp] >= 1 - M_R_pair[t, tp] * (1 - T_crit[t, tp, 2]) - M_R_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.8b_lb")
    model.addConstrs((
        R_var[t] - R_var[tp] <= M_R_pair[t, tp] * T_crit[t, tp, 2] + M_R_pair[t, tp] * (1 - Z_hat[ordered_pair(t, tp)])
        for t in teams for tp in teams if tp != t
    ), name="A.8b_ub")

    F = [(t, tp) for (t, tp) in pairs if g[t, tp] == 0]
    for (t, tp) in F:
        if w_data[t, tp] > w_data[tp, t]:
            model.addConstr(T_crit[t, tp, 1] == 1, name=f"A.9a_{t}_{tp}")
        elif w_data[t, tp] < w_data[tp, t]:
            model.addConstr(T_crit[tp, t, 1] == 1, name=f"A.9a_{tp}_{t}")
        else:
            model.addConstr(T_crit[t, tp, 1] == 0, name=f"A.9b1_{t}_{tp}")
            model.addConstr(T_crit[tp, t, 1] == 0, name=f"A.9b2_{t}_{tp}")
        if r_hat[t, tp] > r_hat[tp, t]:
            model.addConstr(T_crit[t, tp, 2] == 1, name=f"A.9c_{t}_{tp}")
        elif r_hat[t, tp] < r_hat[tp, t]:
            model.addConstr(T_crit[tp, t, 2] == 1, name=f"A.9c_{tp}_{t}")
        else:
            model.addConstr(T_crit[t, tp, 2] == 0, name=f"A.9d1_{t}_{tp}")
            model.addConstr(T_crit[tp, t, 2] == 0, name=f"A.9d2_{t}_{tp}")

    R_size = len(R)
    for (t, tp) in pairs:
        if p[t] < p[tp]:
            model.addConstr(T_crit[t, tp, 3] == 1, name=f"A.10c_{t}_{tp}")
            model.addConstr(T_crit[tp, t, 3] == 0, name=f"A.10c_{tp}_{t}")
        else:
            model.addConstr(T_crit[tp, t, 3] == 1, name=f"A.10c_{tp}_{t}")
            model.addConstr(T_crit[t, tp, 3] == 0, name=f"A.10c_{t}_{tp}")

    model.addConstrs((
        2 ** (R_size + 1) * (1 - Z[t])
        + gp.quicksum(2 ** (R_size - r) * T_crit[t, k, r] for r in R)
        + 2 ** R_size * alpha[k, t]
        >= gp.quicksum(2 ** (R_size - r) * T_crit[k, t, r] for r in R)
        for t in T_k), name="A.10a")
    model.addConstrs((
        2 ** (R_size + 1) * (1 - Z[t])
        + gp.quicksum(2 ** (R_size - r) * T_crit[k, t, r] for r in R)
        + 2 ** R_size * alpha[t, k]
        >= gp.quicksum(2 ** (R_size - r) * T_crit[t, k, r] for r in R)
        for t in T_k), name="A.10b")

    # === A.11 Team Ordering (동일) ===
    model.addConstrs((omega[i, j] + omega[j, i] == 1 for (i, j) in pairs), name="A.11")

    # === 실제 순위와 ordering 변수를 연결 ===
    model.addConstrs((N[k] + omega[t, k] >= N[t] + alpha[t, k] for t in T_k), name="A.12b")
    model.addConstrs((N[t] + omega[k, t] >= N[k] + alpha[k, t] for t in T_k), name="A.12b_rev")

    # === 핵심 차이: k가 포스트시즌에 들지 못하는 제약 ===
    # 탈락 모델(A.12)에서는 "k가 5위 안에 든다"를 강제했지만,
    # 확정 모델에서는 "k가 5위 밖으로 밀려난다"를 강제합니다.
    # → n_playoff팀 이상이 k보다 위에 있어야 함
    model.addConstr(gp.quicksum(omega[t, k] for t in T_k) >= n_playoff, name="Clinch_not_in_PS")

    # === 최적화 ===
    model.optimize()

    # === 결과 ===
    remaining = sum(g[k, j] for j in teams if j != k)
    result = {}

    if model.status == GRB.INFEASIBLE:
        # k를 탈락시킬 방법이 없음 → 이미 확정!
        result['clinched'] = True
        result['clinch_number'] = 0
        result['clinch_wins'] = w_hat[k]
    elif model.status == GRB.OPTIMAL:
        max_lose_wins = int(round(W[k].X))
        clinch_wins = max_lose_wins + 1
        clinch_num = clinch_wins - w_hat[k]

        if clinch_num > remaining:
            # 남은 경기 전부 이겨도 확정 불가 → '*' 표시
            result['clinched'] = False
            result['clinch_number'] = None  # None = 전승해도 보장 불가
            result['clinch_wins'] = None
        else:
            result['clinched'] = False
            result['clinch_number'] = clinch_num
            result['clinch_wins'] = clinch_wins
    else:
        result['clinched'] = None
        result['clinch_number'] = None
        result['clinch_wins'] = None
        result['solver_status'] = model.status

    model.dispose()
    return result


# ============================================================
# 전체 팀 계산 + JSON 출력
# ============================================================

def calculate_all(data, env, verbose=False, show_progress=True):
    """모든 팀의 매직넘버 + 확정넘버를 계산하고 결과를 반환."""
    teams = data['teams']
    results = []

    for i, team in enumerate(teams):
        if show_progress:
            print(f"\n[{i + 1}/{len(teams)}] {team}")

        # 1) 탈락 모델 (현재 가능한 최소 승수)
        if show_progress:
            print(f"  탈락 모델...", end=' ')
        elim = solve_magic_number(env, data, team, verbose=verbose)
        status_e = "탈락" if elim['eliminated'] else f"매직넘버 {elim['magic_number']}"
        if show_progress:
            print(status_e)

        # 2) 확정 모델 (확정에 필요한 승수)
        if show_progress:
            print(f"  확정 모델...", end=' ')
        clinch = solve_clinch_number(env, data, team, verbose=verbose)
        if clinch['clinched']:
            status_c = "이미 확정!"
        elif clinch['clinch_number'] is not None:
            status_c = f"확정넘버 {clinch['clinch_number']}"
        else:
            status_c = "전승해도 확정 불가"
        if show_progress:
            print(status_c)

        # 결과 합치기
        elim.update(clinch)
        results.append(elim)

    # 순위 정렬 (매직넘버 오름차순, 탈락팀은 맨 뒤)
    def sort_key(r):
        if r['eliminated']:
            return (1, 0)
        if r['magic_number'] is None:
            return (2, 0)
        return (0, r['magic_number'])

    results.sort(key=sort_key)

    for rank, r in enumerate(results, 1):
        r['rank'] = rank

    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'data_date': data['date'],
        'n_playoff': N_PLAYOFF,
        'teams': results,
    }
    return output


def run_model(input_path=None, data=None, team=None, verbose=False, env=None, show_progress=False):
    """CLI 없이 파이썬/Jupyter에서 직접 실행하기 위한 진입점.

    Args:
        input_path: main.py JSON 입력 경로
        data: JSON 호환 dict 또는 normalize_data() 결과
        team: 특정 팀만 계산
        verbose: Gurobi 로그 출력 여부
        env: 기존 Gurobi env 재사용용
        show_progress: 팀별 진행 로그 출력 여부
    """
    if data is not None:
        model_data = data if 'w_hat' in data else normalize_data(data)
    else:
        model_data = load_data(input_path)

    owns_env = env is None
    if owns_env:
        env = create_gurobi_env()

    try:
        if team:
            if team not in model_data['teams']:
                print(f"[ERROR] 팀 '{team}'을(를) 찾을 수 없습니다.")
                print(f"  가능한 팀: {', '.join(model_data['teams'])}")
                sys.exit(1)

            elim = solve_magic_number(env, model_data, team, verbose=verbose)
            clinch = solve_clinch_number(env, model_data, team, verbose=verbose)
            elim.update(clinch)
            output = {
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'data_date': model_data['date'],
                'n_playoff': N_PLAYOFF,
                'teams': [elim],
            }
        else:
            output = calculate_all(model_data, env, verbose=verbose, show_progress=show_progress)
        return output
    finally:
        if owns_env:
            env.dispose()


def results_table(output):
    """출력 dict를 notebook에서 보기 쉬운 list-of-dicts 형태로 변환."""
    rows = []
    for team in output['teams']:
        rows.append({
            'rank': team.get('rank'),
            'team': team['team'],
            'team_label': team.get('team_label', team['team']),
            'wins': team['current_wins'],
            'losses': team['current_losses'],
            'draws': team['current_draws'],
            'remaining_games': team['remaining_games'],
            'magic_number': team.get('magic_number'),
            'eliminated': team.get('eliminated'),
            'clinch_number': team.get('clinch_number'),
            'clinched': team.get('clinched'),
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description='KBO 매직넘버 계산기')
    parser.add_argument('--input', type=str, help='입력 데이터 JSON 경로')
    parser.add_argument('--output', type=str, help='결과 JSON 출력 경로')
    parser.add_argument('--team', type=str, help='특정 팀만 계산')
    parser.add_argument('--verbose', action='store_true', help='Gurobi 로그 출력')
    args = parser.parse_args()

    data = load_data(args.input)
    env = create_gurobi_env()

    if args.team:
        if args.team not in data['teams']:
            print(f"[ERROR] 팀 '{args.team}'을(를) 찾을 수 없습니다.")
            print(f"  가능한 팀: {', '.join(data['teams'])}")
            sys.exit(1)
        elim = solve_magic_number(env, data, args.team, verbose=args.verbose)
        clinch = solve_clinch_number(env, data, args.team, verbose=args.verbose)
        elim.update(clinch)
        output = {
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'data_date': data['date'],
            'n_playoff': N_PLAYOFF,
            'teams': [elim],
        }
    else:
        output = calculate_all(data, env, verbose=args.verbose, show_progress=True)

    # 콘솔 출력
    print("\n" + "=" * 72)
    print(f"  KBO 매직넘버  (기준일: {output['data_date']})")
    print("=" * 72)
    print(f"{'순위':>4}  {'팀':>8}  {'현재':>5}  {'탈락방지':>6}  {'PS확정':>6}  {'상태':>10}")
    print("-" * 72)
    for r in output['teams']:
        cur = f"{r['current_wins']}승"

        # 탈락 방지 (elimination)
        if r['eliminated']:
            elim_str = 'X'
        elif r['magic_number'] is not None:
            elim_str = str(r['magic_number'])
        else:
            elim_str = '?'

        # PS 확정 (clinch)
        if r.get('clinched'):
            clinch_str = 'In'
        elif r.get('clinch_number') is not None:
            clinch_str = str(r['clinch_number'])
        else:
            clinch_str = '*'

        # 상태 요약
        if r['eliminated']:
            status = '탈락'
        elif r.get('clinched'):
            status = '확정'
        elif r['magic_number'] == 0:
            status = '생존'
        else:
            status = '경쟁중'

        print(f"{r.get('rank', '-'):>4}  {r['team']:>8}  {cur:>5}  {elim_str:>6}  {clinch_str:>6}  {status:>10}")
    print("=" * 72)

    # JSON 저장
    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n[INFO] 결과 저장: {args.output}")

    env.dispose()


if __name__ == '__main__':
    main()
