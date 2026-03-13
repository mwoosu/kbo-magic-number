/* ============================================================
   KBO Dashboard — app.js
   ============================================================ */

const pageConfig = {
    dataUrl: document.body.dataset.dataUrl || 'data/result.json',
    pageMode: document.body.dataset.pageMode || 'live',
};

function isDemoPage() {
    return pageConfig.pageMode === 'demo';
}

async function loadData() {
    try {
        const res = await fetch(pageConfig.dataUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (error) {
        console.error('데이터 로드 실패:', error);
        return null;
    }
}

function formatPct(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '-';
    return `.${numeric.toFixed(3).split('.')[1]}`;
}

function getRankClass(rank, nPlayoff) {
    if (rank <= 3) return `top rank-${rank}`;
    if (nPlayoff && rank <= nPlayoff) return 'top';
    return 'out';
}

function setHeader(data) {
    const badge = document.getElementById('header-badge');
    const title = document.getElementById('page-title');
    const info = document.getElementById('update-info');
    const legend = document.getElementById('info-legend');
    const demoMode = isDemoPage();
    const demoLegend = demoMode
        ? `
            <div class="legend-item">
                <span class="legend-label">데모</span>
                <span class="legend-desc">지난 시즌 정규시즌 스냅샷으로 계산한 테스트 페이지입니다.</span>
            </div>
        `
        : '';

    const phase = data.phase || 'regular';

    if (phase === 'exhibition') {
        badge.textContent = demoMode ? 'SPRING DEMO' : 'SPRING TRAINING';
        title.textContent = demoMode ? 'KBO 시범경기 DEMO' : 'KBO 시범경기';
        info.textContent = demoMode
            ? `${data.data_date} 기준 · 시범경기 테스트 데이터`
            : `${data.data_date} 기준 · 업데이트 ${data.updated_at}`;
        legend.innerHTML = `
            <div class="legend-item">
                <span class="legend-label">현재 상태</span>
                <span class="legend-desc">${data.headline || '정규시즌 개막 전까지 시범경기 순위를 제공합니다.'}</span>
            </div>
            <div class="legend-item">
                <span class="legend-label">카드 숫자</span>
                <span class="legend-desc">왼쪽은 승률, 오른쪽은 경기수입니다.</span>
            </div>
            ${demoLegend}
        `;
        return;
    }

    if (phase === 'offseason') {
        badge.textContent = 'OFFSEASON';
        title.textContent = 'KBO 대시보드';
        info.textContent = `업데이트 ${data.updated_at}`;
        legend.innerHTML = `
            <div class="legend-item">
                <span class="legend-label">안내</span>
                <span class="legend-desc">${data.headline || '현재 활성화된 경기 데이터가 없습니다.'}</span>
            </div>
            ${demoLegend}
        `;
        return;
    }

    badge.textContent = demoMode ? 'HISTORICAL DEMO' : 'LIVE TRACKER';
    title.textContent = demoMode ? 'KBO 매직넘버 DEMO' : 'KBO 매직넘버';
    info.textContent = demoMode
        ? `${data.data_date} 기준 · 2025 정규시즌 테스트 결과`
        : `${data.data_date} 기준 · 업데이트 ${data.updated_at}`;
    legend.innerHTML = `
        <div class="legend-item">
            <span class="legend-label">탈락방지</span>
            <span class="legend-desc">포스트시즌 탈락을 피하기 위해 필요한 최소 추가 승수</span>
        </div>
        <div class="legend-item">
            <span class="legend-label">진출확정</span>
            <span class="legend-desc">나머지 경기 결과와 무관하게 포스트시즌 진출을 보장받기 위한 추가 승수</span>
        </div>
        ${demoLegend}
    `;
}

function createRegularCard(team, nPlayoff, index) {
    const card = document.createElement('div');
    card.className = `team-card${team.eliminated ? ' eliminated' : ''}`;
    card.style.animationDelay = `${index * 0.06}s`;

    const rankClass = getRankClass(team.rank, nPlayoff);

    let elimDisplay;
    let elimLabel;
    let elimClass;
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

    let clinchDisplay;
    let clinchLabel;
    let clinchClass;
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

    const winPct = team.win_pct !== undefined && team.win_pct !== null
        ? formatPct(team.win_pct)
        : formatPct(team.current_wins / Math.max(team.current_wins + team.current_losses, 1));

    card.innerHTML = `
        <div class="rank-badge ${rankClass}">${team.rank}</div>
        <div class="team-info">
            <div class="team-name">${team.team_label}</div>
            <div class="team-record">
                ${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무
                · 승률 ${winPct}
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

function createExhibitionCard(team, index) {
    const card = document.createElement('div');
    card.className = 'team-card';
    card.style.animationDelay = `${index * 0.06}s`;

    const rankClass = getRankClass(team.rank, 5);

    card.innerHTML = `
        <div class="rank-badge ${rankClass}">${team.rank}</div>
        <div class="team-info">
            <div class="team-name">${team.team_label}</div>
            <div class="team-record">
                ${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무
                · 최근 ${team.recent || '-'}
            </div>
        </div>
        <div class="numbers-section">
            <div class="number-col">
                <div class="magic-number safe">${formatPct(team.win_pct)}</div>
                <div class="magic-label">승률</div>
            </div>
            <div class="number-divider"></div>
            <div class="number-col">
                <div class="magic-number warning">${team.games}</div>
                <div class="magic-label">경기수</div>
            </div>
        </div>
    `;

    return card;
}

function renderError(grid, message) {
    grid.innerHTML = `
        <div class="error-msg">
            <h2>데이터를 불러올 수 없습니다</h2>
            <p>${message}</p>
        </div>
    `;
}

function render(data) {
    const grid = document.getElementById('team-grid');
    const playoffLine = document.getElementById('playoff-line');

    if (!data) {
        renderError(grid, 'result.json 파일이 아직 생성되지 않았거나, 경로가 올바르지 않습니다.');
        return;
    }

    setHeader(data);
    grid.innerHTML = '';
    playoffLine.classList.remove('visible');

    const phase = data.phase || 'regular';
    if (phase === 'offseason') {
        renderError(grid, data.headline || '현재 활성화된 경기 데이터가 없습니다.');
        return;
    }

    if (phase === 'exhibition') {
        data.teams.forEach((team, index) => {
            grid.appendChild(createExhibitionCard(team, index));
        });
        return;
    }

    const nPlayoff = data.n_playoff || 5;
    data.teams.forEach((team, index) => {
        if (team.rank === nPlayoff + 1) {
            playoffLine.classList.add('visible');
            grid.appendChild(playoffLine);
        }
        grid.appendChild(createRegularCard(team, nPlayoff, index));
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    const data = await loadData();
    render(data);
});
