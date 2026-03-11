/* ============================================================
   KBO Magic Number Dashboard — app.js
   ============================================================ */

const DATA_URL = 'data/result.json';

async function loadData() {
    try {
        const res = await fetch(DATA_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error('데이터 로드 실패:', e);
        return null;
    }
}

function getElimClass(team) {
    if (team.eliminated) return 'eliminated';
    if (team.magic_number === 0) return 'safe';
    if (team.magic_number <= 5) return 'safe';
    if (team.magic_number <= 15) return 'warning';
    return 'danger';
}

function getRankClass(rank, nPlayoff) {
    if (rank <= 3) return `top rank-${rank}`;
    if (rank <= nPlayoff) return 'top';
    return 'out';
}

function createTeamCard(team, nPlayoff, index) {
    const card = document.createElement('div');
    card.className = `team-card${team.eliminated ? ' eliminated' : ''}`;
    card.style.animationDelay = `${index * 0.06}s`;

    const rankClass = getRankClass(team.rank, nPlayoff);

    // 탈락방지 (elimination) 숫자
    let elimDisplay, elimLabel, elimClass;
    if (team.eliminated) {
        elimDisplay = '탈락';
        elimLabel = 'ELIMINATED';
        elimClass = 'eliminated';
    } else if (team.magic_number === 0) {
        elimDisplay = '0';
        elimLabel = '생존';
        elimClass = 'safe';
    } else {
        elimDisplay = team.magic_number;
        elimLabel = `${team.min_wins}승 필요`;
        elimClass = team.magic_number <= 5 ? 'safe' : team.magic_number <= 15 ? 'warning' : 'danger';
    }

    // PS확정 (clinch) 숫자
    let clinchDisplay, clinchLabel, clinchClass;
    if (team.clinched) {
        clinchDisplay = 'In';
        clinchLabel = '확정';
        clinchClass = 'clinched';
    } else if (team.clinch_number !== null && team.clinch_number !== undefined) {
        clinchDisplay = team.clinch_number;
        clinchLabel = `${team.clinch_wins}승 필요`;
        clinchClass = team.clinch_number <= 10 ? 'safe' : 'warning';
    } else {
        clinchDisplay = '*';
        clinchLabel = '보장 불가';
        clinchClass = 'danger';
    }

    const winPct = team.win_pct
        ? (team.win_pct * 1000 / 10).toFixed(1)
        : ((team.current_wins / (team.current_wins + team.current_losses)) * 100).toFixed(1);

    card.innerHTML = `
        <div class="rank-badge ${rankClass}">${team.rank}</div>
        <div class="team-info">
            <div class="team-name">${team.team_label}</div>
            <div class="team-record">
                ${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무
                · 승률 .${winPct.replace('.', '')}
                · 잔여 ${team.remaining_games}경기
            </div>
        </div>
        <div class="numbers-section">
            <div class="number-col">
                <div class="magic-number ${elimClass}">${elimDisplay}</div>
                <div class="magic-label">탈락방지</div>
            </div>
            <div class="number-divider"></div>
            <div class="number-col">
                <div class="magic-number ${clinchClass}">${clinchDisplay}</div>
                <div class="magic-label">진출확정</div>
            </div>
        </div>
    `;

    return card;
}

function render(data) {
    const grid = document.getElementById('team-grid');
    const info = document.getElementById('update-info');
    const playoffLine = document.getElementById('playoff-line');

    if (!data) {
        grid.innerHTML = `
            <div class="error-msg">
                <h2>데이터를 불러올 수 없습니다</h2>
                <p>result.json 파일이 아직 생성되지 않았거나, 경로가 올바르지 않습니다.</p>
            </div>
        `;
        return;
    }

    info.textContent = `${data.data_date} 기준 · 업데이트 ${data.updated_at}`;

    grid.innerHTML = '';

    const teams = data.teams;
    const nPlayoff = data.n_playoff || 5;

    teams.forEach((team, i) => {
        if (team.rank === nPlayoff + 1) {
            playoffLine.classList.add('visible');
            grid.appendChild(playoffLine);
        }

        grid.appendChild(createTeamCard(team, nPlayoff, i));
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    const data = await loadData();
    render(data);
});
