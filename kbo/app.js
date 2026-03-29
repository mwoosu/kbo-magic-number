/* ============================================================
   KBO Dashboard — app.js
   ============================================================ */

const pageConfig = {
    dataUrl: document.body.dataset.dataUrl || 'data/result.json',
};

const appState = {
    data: null,
    selectedTeamId: null,
    hasAnimatedCards: false,
};

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

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function formatPct(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '-';
    if (numeric >= 1) return '1.000';
    return numeric.toFixed(3);
}

function formatGap(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '-';
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1);
}

function formatRelativeGap(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '-';
    if (numeric === 0) return '동률';
    const gap = formatGap(Math.abs(numeric));
    return numeric > 0 ? `${gap}경기 뒤` : `${gap}경기 앞`;
}

const TEAM_LOGO_MAP = {
    Doosan: 'logo/Doosan_emblem.webp',
    Hanwha: 'logo/Hanwha_emblem.png',
    KIA: 'logo/KIA_emblem.png',
    KT: 'logo/KT_Emblem.jpg',
    Kiwoom: 'logo/Kiwoom_Emblem.jpg',
    LG: 'logo/LG_emblem.png',
    Lotte: 'logo/Lotte_emblem.jpg',
    NC: 'logo/NC_emblem.png',
    Samsung: 'logo/Samsung_emblem.png',
    SSG: 'logo/ssg_emblem.png',
};

function getTeamLogoPath(teamId) {
    return TEAM_LOGO_MAP[teamId] || '';
}

function renderTeamLogo(team) {
    const logoPath = getTeamLogoPath(team.team);
    if (!logoPath) return '';
    return `<img class="team-logo" src="${escapeHtml(logoPath)}" alt="${escapeHtml(team.team_label)} 엠블럼" loading="lazy">`;
}

function renderMetaLine(className, parts) {
    const items = parts
        .filter(Boolean)
        .map((part) => `<span class="meta-group">${escapeHtml(part)}</span>`)
        .join('');
    return `<div class="${className}">${items}</div>`;
}

function renderRecordLine(parts) {
    return renderMetaLine('team-record', parts);
}

function getRankClass(rank, nPlayoff) {
    if (rank <= 3) return `top rank-${rank}`;
    if (nPlayoff && rank <= nPlayoff) return 'top';
    return 'out';
}

function getDetailStatusClass(team, phase) {
    if (phase === 'exhibition') {
        return team.rank === 1 ? 'safe' : 'warning';
    }
    if (team.eliminated) return 'danger';
    if (team.clinched) return 'safe';
    if (team.clinch_number !== null && team.clinch_number !== undefined) return 'safe';
    if (team.magic_number === 0) return 'warning';
    return 'danger';
}

function setHeader(data) {
    const badge = document.getElementById('header-badge');
    const title = document.getElementById('page-title');
    const info = document.getElementById('update-info');
    const legend = document.getElementById('info-legend');

    const phase = data.phase || 'regular';

    if (phase === 'exhibition') {
        badge.textContent = 'SPRING TRAINING';
        title.textContent = 'KBO 시범경기';
        info.textContent = `${data.data_date} 기준 · 업데이트 ${data.updated_at}`;
        legend.innerHTML = `
            <div class="legend-item">
                <span class="legend-label">현재 상태</span>
                <span class="legend-desc">${data.headline || '정규시즌 개막 전까지 시범경기 순위를 제공합니다.'}</span>
            </div>
            <div class="legend-item">
                <span class="legend-label">카드 숫자</span>
                <span class="legend-desc">왼쪽은 승률, 오른쪽은 경기수입니다.</span>
            </div>
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
        `;
        return;
    }

    badge.textContent = 'LIVE TRACKER';
    title.textContent = 'KBO 매직넘버';
    info.textContent = `${data.data_date} 기준 · 업데이트 ${data.updated_at}`;

    const teams = data.teams || [];
    const hasEliminated = teams.some((t) => t.eliminated);
    const hasClinched = teams.some((t) => t.clinched);
    const hasNoSelfClinch = teams.some((t) => !t.eliminated && !t.clinched && (t.clinch_number === null || t.clinch_number === undefined));

    let symbolParts = [];
    if (hasNoSelfClinch) symbolParts.push('<code>*</code>는 전승해도 자력 확정을 보장할 수 없다는 뜻입니다.');
    if (hasEliminated) symbolParts.push('<code>-</code>는 이미 탈락해 해당 없음입니다.');
    if (hasClinched) symbolParts.push('<code>In</code>은 이미 진출 확정입니다.');

    const symbolLegend = symbolParts.length > 0
        ? `<div class="legend-item">
            <span class="legend-label">기호</span>
            <span class="legend-desc">${symbolParts.join(' ')}</span>
        </div>`
        : '';

    legend.innerHTML = `
        <div class="legend-item">
            <span class="legend-label">탈락방지</span>
            <span class="legend-desc">포스트시즌 가능성을 유지하기 위해 필요한 최소 추가 승수</span>
        </div>
        <div class="legend-item">
            <span class="legend-label">진출확정</span>
            <span class="legend-desc">다른 경기 결과와 무관하게 포스트시즌 진출을 확정하기 위한 추가 승수</span>
        </div>
        ${symbolLegend}
        <hr class="legend-divider">
        <div class="legend-item legend-hint">
            <span class="legend-desc"><span class="legend-dot">·</span>각 팀 카드를 클릭하면 상세 해설을 확인할 수 있습니다.</span>
        </div>
    `;
}

function getFallbackRegularAnalysis(data, team) {
    const nPlayoff = data.n_playoff || 5;
    let headline = '현재 상태를 추가로 해석할 수 있습니다.';
    if (team.eliminated) {
        headline = '남은 모든 경우를 고려해도 포스트시즌 진입이 불가능합니다.';
    } else if (team.clinched) {
        headline = '이미 포스트시즌 진출이 확정됐습니다.';
    } else if (team.clinch_number === 1) {
        headline = '앞으로 1승만 더하면 포스트시즌 진출이 확정됩니다.';
    } else if (team.clinch_number !== null && team.clinch_number !== undefined) {
        headline = `앞으로 ${team.clinch_number}승을 더하면 포스트시즌 진출이 확정됩니다.`;
    } else if (team.magic_number === 0) {
        headline = '아직 탈락하지 않았지만 경쟁팀 결과에 따라 순위가 바뀔 수 있습니다.';
    } else if (team.magic_number !== null && team.magic_number !== undefined) {
        headline = `포스트시즌 가능성을 유지하려면 최소 ${team.magic_number}승이 더 필요합니다.`;
    }

    const notes = [
        `${team.team_label}는 현재 ${team.rank ?? '-'}위이며 ${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무를 기록 중입니다.`,
        `잔여 경기는 ${team.remaining_games}경기입니다.`,
    ];

    return {
        status_label: team.eliminated ? '탈락' : team.clinched ? '확정' : '경쟁 중',
        headline,
        notes,
        rivals: [],
        remaining_schedule: [],
        summary: notes[0],
    };
}

function getFallbackExhibitionAnalysis(team) {
    const notes = [
        `${team.team_label}는 현재 ${team.rank}위이며 ${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무입니다.`,
        `최근 흐름은 ${team.recent || '-'}입니다.`,
        `시범경기 승률은 ${formatPct(team.win_pct)}이고 ${team.games}경기를 소화했습니다.`,
    ];
    return {
        status_label: '시범경기',
        headline: team.rank === 1 ? '현재 시범경기 선두권입니다.' : '시범경기 순위를 유지 중입니다.',
        notes,
        rivals: [],
        remaining_schedule: [],
        summary: notes[0],
    };
}

function getAnalysis(data, team) {
    const phase = data.phase || 'regular';
    if (team.analysis) return team.analysis;
    if (phase === 'exhibition') return getFallbackExhibitionAnalysis(team);
    return getFallbackRegularAnalysis(data, team);
}

function createRegularCard(team, nPlayoff, index) {
    const card = document.createElement('div');
    card.className = `team-card${team.eliminated ? ' eliminated' : ''}${appState.selectedTeamId === team.team ? ' is-selected' : ''}`;
    if (appState.hasAnimatedCards) {
        card.classList.add('no-entry-animation');
    } else {
        card.style.animationDelay = `${index * 0.06}s`;
    }
    card.setAttribute('role', 'button');
    card.tabIndex = 0;
    card.dataset.teamId = team.team;

    const rankClass = getRankClass(team.rank, nPlayoff);

    let elimDisplay;
    let elimClass;
    if (team.eliminated) {
        elimDisplay = '탈락';
        elimClass = 'eliminated';
    } else if (team.magic_number === 0) {
        elimDisplay = '0';
        elimClass = 'safe';
    } else {
        elimDisplay = team.magic_number;
        elimClass = team.magic_number <= 5 ? 'safe' : team.magic_number <= 15 ? 'warning' : 'danger';
    }

    let clinchDisplay;
    let clinchClass;
    if (team.eliminated) {
        clinchDisplay = '-';
        clinchClass = 'muted';
    } else if (team.clinched) {
        clinchDisplay = 'In';
        clinchClass = 'clinched';
    } else if (team.clinch_number !== null && team.clinch_number !== undefined) {
        clinchDisplay = team.clinch_number;
        clinchClass = team.clinch_number <= 10 ? 'safe' : 'warning';
    } else {
        clinchDisplay = '*';
        clinchClass = 'danger';
    }

    const winPct = team.win_pct !== undefined && team.win_pct !== null
        ? formatPct(team.win_pct)
        : formatPct(team.current_wins / Math.max(team.current_wins + team.current_losses, 1));

    const recordLine = renderRecordLine([
        `${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무`,
        `승률 ${winPct}`,
        `잔여 ${team.remaining_games}경기`,
    ]);

    card.innerHTML = `
        <div class="rank-badge ${rankClass}">${escapeHtml(team.rank)}</div>
        <div class="team-logo-wrap">
            ${renderTeamLogo(team)}
        </div>
        <div class="team-info">
            <div class="team-name">${escapeHtml(team.team_label)}</div>
            ${recordLine}
        </div>
        <div class="numbers-section">
            <div class="number-col">
                <div class="magic-number ${elimClass}">${escapeHtml(elimDisplay)}</div>
                <div class="magic-label">탈락방지</div>
            </div>
            <div class="number-divider"></div>
            <div class="number-col">
                <div class="magic-number ${clinchClass}">${escapeHtml(clinchDisplay)}</div>
                <div class="magic-label">진출확정</div>
            </div>
        </div>
    `;

    bindCardInteraction(card, team.team);
    return card;
}

function createExhibitionCard(team, index) {
    const card = document.createElement('div');
    card.className = `team-card${appState.selectedTeamId === team.team ? ' is-selected' : ''}`;
    if (appState.hasAnimatedCards) {
        card.classList.add('no-entry-animation');
    } else {
        card.style.animationDelay = `${index * 0.06}s`;
    }
    card.setAttribute('role', 'button');
    card.tabIndex = 0;
    card.dataset.teamId = team.team;

    const rankClass = getRankClass(team.rank, 5);

    const recordLine = renderRecordLine([
        `${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무`,
        `최근 ${team.recent || '-'}`,
    ]);

    card.innerHTML = `
        <div class="rank-badge ${rankClass}">${escapeHtml(team.rank)}</div>
        <div class="team-logo-wrap">
            ${renderTeamLogo(team)}
        </div>
        <div class="team-info">
            <div class="team-name">${escapeHtml(team.team_label)}</div>
            ${recordLine}
        </div>
        <div class="numbers-section">
            <div class="number-col">
                <div class="magic-number safe">${escapeHtml(formatPct(team.win_pct))}</div>
                <div class="magic-label">승률</div>
            </div>
            <div class="number-divider"></div>
            <div class="number-col">
                <div class="magic-number warning">${escapeHtml(team.games)}</div>
                <div class="magic-label">경기수</div>
            </div>
        </div>
    `;

    bindCardInteraction(card, team.team);
    return card;
}

function bindCardInteraction(card, teamId) {
    const select = () => {
        appState.selectedTeamId = teamId;
        syncCardSelection();
        renderTeamDetail(appState.data, ensureSelectedTeam(appState.data));
    };
    card.addEventListener('click', select);
    card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            select();
        }
    });
}

function clearSelectedTeam() {
    appState.selectedTeamId = null;
    syncCardSelection();
    renderTeamDetail(appState.data, null);
}

function renderError(grid, message) {
    grid.innerHTML = `
        <div class="error-msg">
            <h2>데이터를 불러올 수 없습니다</h2>
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

function renderDetailEmpty(message) {
    const detail = document.getElementById('team-detail');
    detail.classList.remove('is-open');
    detail.innerHTML = `
        <div class="detail-empty">
            <h2>팀 상세</h2>
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

function ensureSelectedTeam(data) {
    const teams = data.teams || [];
    if (!teams.length) {
        appState.selectedTeamId = null;
        return null;
    }

    const current = teams.find((team) => team.team === appState.selectedTeamId);
    return current || null;
}

function syncCardSelection() {
    document.querySelectorAll('.team-card[data-team-id]').forEach((card) => {
        const isSelected = card.dataset.teamId === appState.selectedTeamId;
        card.classList.toggle('is-selected', isSelected);
    });
}

function renderMetrics(team, phase) {
    if (phase === 'exhibition') {
        return `
            <div class="detail-metrics">
                <div class="detail-metric">
                    <span class="detail-metric-label">현재 순위</span>
                    <div class="detail-metric-value">${escapeHtml(team.rank)}</div>
                </div>
                <div class="detail-metric">
                    <span class="detail-metric-label">승률</span>
                    <div class="detail-metric-value">${escapeHtml(formatPct(team.win_pct))}</div>
                </div>
                <div class="detail-metric">
                    <span class="detail-metric-label">경기수</span>
                    <div class="detail-metric-value">${escapeHtml(team.games)}</div>
                </div>
            </div>
        `;
    }

    const eliminationValue = team.eliminated
        ? '탈락'
        : team.magic_number === null || team.magic_number === undefined
            ? '-'
            : String(team.magic_number);
    const clinchValue = team.eliminated
        ? '-'
        : team.clinched
            ? 'In'
            : team.clinch_number === null || team.clinch_number === undefined
                ? '*'
                : String(team.clinch_number);

    return `
        <div class="detail-metrics">
            <div class="detail-metric">
                <span class="detail-metric-label">현재 순위</span>
                <div class="detail-metric-value">${escapeHtml(team.rank ?? '-')}</div>
            </div>
            <div class="detail-metric">
                <span class="detail-metric-label">탈락방지</span>
                <div class="detail-metric-value">${escapeHtml(eliminationValue)}</div>
            </div>
            <div class="detail-metric">
                <span class="detail-metric-label">진출확정</span>
                <div class="detail-metric-value">${escapeHtml(clinchValue)}</div>
            </div>
        </div>
    `;
}

function getRivalSectionTitle(data, team) {
    const phase = data.phase || 'regular';
    if (phase !== 'regular') return '주변 팀';
    const nPlayoff = data.n_playoff || 5;
    if (team.rank >= nPlayoff - 1 && team.rank <= nPlayoff + 2) {
        return '컷라인 경쟁';
    }
    return '주변 팀과 승차';
}

function renderRivals(data, team, analysis) {
    if (!analysis.rivals || !analysis.rivals.length) return '';
    const title = getRivalSectionTitle(data, team);
    const rows = analysis.rivals.map((rival) => {
        const subtitle = renderMetaLine('detail-row-subtitle', [
            `${rival.wins}승 ${rival.losses}패 ${rival.draws}무`,
            `잔여 ${rival.remaining_games}경기`,
            rival.status_label,
        ]);
        return `
            <div class="detail-row">
                <div>
                    <div class="detail-row-title">${escapeHtml(rival.rank)}위 ${escapeHtml(rival.team_label)}</div>
                    ${subtitle}
                </div>
                <div class="detail-row-value">${escapeHtml(formatRelativeGap(rival.gap_from_selected))}</div>
            </div>
        `;
    }).join('');

    return `
        <section class="detail-section">
            <h3>${escapeHtml(title)}</h3>
            <p class="detail-section-note">선택한 팀 기준으로 상대 팀이 몇 경기 앞서거나 뒤져 있는지 보여줍니다.</p>
            <p class="detail-section-note">경기차는 (승수 차 + 패수 차) ÷ 2로 계산합니다.</p>
            <div class="detail-table">${rows}</div>
        </section>
    `;
}

function renderSchedule(analysis, phase) {
    if (!analysis.remaining_schedule || !analysis.remaining_schedule.length) return '';
    const rows = analysis.remaining_schedule.slice(0, 5).map((item) => {
        const subtitle = phase === 'regular'
            ? renderMetaLine('detail-row-subtitle', [
                `맞대결 ${item.head_to_head_wins}승 ${item.head_to_head_losses}패`,
                `남은 ${item.games_left}경기`,
            ])
            : renderMetaLine('detail-row-subtitle', [`남은 ${item.games_left}경기`]);
        return `
            <div class="detail-row">
                <div>
                    <div class="detail-row-title">${escapeHtml(item.team_label)}</div>
                    ${subtitle}
                </div>
                <div class="detail-row-value">${escapeHtml(item.games_left)}경기</div>
            </div>
        `;
    }).join('');

    return `
        <section class="detail-section">
            <h3>잔여 일정</h3>
            <div class="detail-table">${rows}</div>
        </section>
    `;
}

function renderTeamDetail(data, team) {
    const detail = document.getElementById('team-detail');
    const phase = data.phase || 'regular';

    if (!team) {
        renderDetailEmpty('카드를 누르면 상세 해설이 표시됩니다.');
        return;
    }

    detail.classList.add('is-open');

    const analysis = getAnalysis(data, team);
    const statusClass = getDetailStatusClass(team, phase);
    const notes = (analysis.notes || [])
        .map((note) => `<li>${escapeHtml(note)}</li>`)
        .join('');
    const detailSubtitle = renderMetaLine('detail-subtitle', [
        `${team.current_wins}승 ${team.current_losses}패 ${team.current_draws}무`,
        phase === 'exhibition' ? `최근 ${team.recent || '-'}` : `잔여 ${team.remaining_games}경기`,
    ]);

    detail.innerHTML = `
        <div class="detail-header">
            <div class="detail-heading">
                <div class="detail-team">${escapeHtml(team.team_label)}</div>
                ${detailSubtitle}
                <div class="detail-status ${statusClass}">${escapeHtml(analysis.status_label || '상세')}</div>
            </div>
            <button type="button" class="detail-close" aria-label="상세 닫기" id="detail-close">×</button>
        </div>
        <div class="detail-headline">${escapeHtml(analysis.headline || '')}</div>
        ${renderMetrics(team, phase)}
        <section class="detail-section">
            <h3>모델 해설</h3>
            <ul class="detail-list">${notes}</ul>
        </section>
        ${renderRivals(data, team, analysis)}
        ${renderSchedule(analysis, phase)}
    `;
    document.getElementById('detail-close').addEventListener('click', clearSelectedTeam);
}

function render(data) {
    appState.data = data;

    const grid = document.getElementById('team-grid');
    const playoffLine = document.getElementById('playoff-line');

    if (!data) {
        renderError(grid, 'result.json 파일이 아직 생성되지 않았거나, 경로가 올바르지 않습니다.');
        renderDetailEmpty('데이터가 준비되면 팀 상세가 여기에 표시됩니다.');
        return;
    }

    setHeader(data);
    grid.innerHTML = '';
    playoffLine.classList.remove('visible');

    const phase = data.phase || 'regular';
    if (phase === 'offseason') {
        renderError(grid, data.headline || '현재 활성화된 경기 데이터가 없습니다.');
        renderDetailEmpty(data.headline || '현재 활성화된 경기 데이터가 없습니다.');
        appState.hasAnimatedCards = true;
        return;
    }

    const selectedTeam = ensureSelectedTeam(data);

    if (phase === 'exhibition') {
        data.teams.forEach((team, index) => {
            grid.appendChild(createExhibitionCard(team, index));
        });
        renderTeamDetail(data, selectedTeam);
        appState.hasAnimatedCards = true;
        return;
    }

    const nPlayoff = data.n_playoff || 5;
    let playoffLineInserted = false;
    data.teams.forEach((team, index) => {
        if (!playoffLineInserted && team.rank > nPlayoff) {
            playoffLineInserted = true;
            playoffLine.classList.add('visible');
            grid.appendChild(playoffLine);
        }
        grid.appendChild(createRegularCard(team, nPlayoff, index));
    });
    renderTeamDetail(data, selectedTeam);
    appState.hasAnimatedCards = true;
}

document.addEventListener('DOMContentLoaded', async () => {
    const data = await loadData();
    render(data);
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        if (document.getElementById('feedback-overlay')?.classList.contains('is-open')) {
            closeFeedback();
        } else if (appState.selectedTeamId) {
            clearSelectedTeam();
        }
    }
});

/* --- Feedback --- */
function openFeedback() {
    document.getElementById('feedback-overlay').classList.add('is-open');
    document.getElementById('feedback-text').focus();
}

function closeFeedback() {
    const overlay = document.getElementById('feedback-overlay');
    overlay.classList.remove('is-open');
    setTimeout(() => {
        document.getElementById('feedback-text').value = '';
        document.getElementById('feedback-charcount').textContent = '0 / 1000';
        document.getElementById('feedback-done').style.display = 'none';
        document.getElementById('feedback-text').style.display = '';
        document.getElementById('feedback-footer').style.display = '';
        document.getElementById('feedback-desc').style.display = '';
        document.getElementById('feedback-submit').disabled = false;
    }, 300);
}

document.getElementById('feedback-open')?.addEventListener('click', openFeedback);
document.getElementById('feedback-close')?.addEventListener('click', closeFeedback);
document.getElementById('feedback-overlay')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeFeedback();
});

document.getElementById('feedback-text')?.addEventListener('input', (e) => {
    const len = e.target.value.length;
    document.getElementById('feedback-charcount').textContent = `${len} / 1000`;
});

document.getElementById('feedback-submit')?.addEventListener('click', async () => {
    const textarea = document.getElementById('feedback-text');
    const text = textarea.value.trim();
    if (!text) {
        textarea.focus();
        return;
    }

    const btn = document.getElementById('feedback-submit');
    btn.disabled = true;
    btn.textContent = '전송 중...';

    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        await fetch('/file/board/Tools/kbo/feedback.asp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `feedback=${encodeURIComponent(text)}`,
            signal: controller.signal,
        });
        clearTimeout(timeout);
    } catch (err) {
        console.log('[feedback] endpoint not available:', err.message);
    }

    document.getElementById('feedback-text').style.display = 'none';
    document.getElementById('feedback-footer').style.display = 'none';
    document.getElementById('feedback-desc').style.display = 'none';
    document.getElementById('feedback-done').style.display = 'block';
});
