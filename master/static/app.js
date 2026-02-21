/* CANAVAR Monitor - Dashboard JavaScript */

const REFRESH_INTERVAL = 5000;

// Toast notification
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${icons[type] || ''}</span> ${message}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// Get metric color class based on value
function getMetricClass(value, base) {
    if (value >= 90) return 'danger';
    if (value >= 75) return 'warning';
    return base;
}

// Build PC card HTML
function buildPCCard(agent) {
    const statusClass = `badge-${agent.status}`;
    const statusText = { online: 'Çevrimiçi', offline: 'Çevrimdışı', warning: 'Uyarı' }[agent.status] || agent.status;

    let processHTML = '';
    if (agent.watched_status && Object.keys(agent.watched_status).length > 0) {
        const tags = Object.entries(agent.watched_status).map(([name, running]) =>
            `<span class="process-tag ${running ? 'running' : 'stopped'}">${running ? '●' : '○'} ${name}</span>`
        ).join('');
        processHTML = `<div class="process-section"><h4>İzlenen Programlar</h4><div class="process-list">${tags}</div></div>`;
    }

    return `
    <div class="pc-card" onclick="window.location='/pc/${agent.pc_name}'">
        <div class="pc-card-header">
            <div class="pc-card-name">
                <span class="pc-icon">🖥️</span>
                <div>
                    <h3>${agent.pc_name}</h3>
                    <span class="pc-ip">${agent.ip || '—'}</span>
                </div>
            </div>
            <span class="badge ${statusClass}"><span class="dot"></span>${statusText}</span>
        </div>
        <div class="metrics">
            <div class="metric">
                <span class="metric-label">CPU</span>
                <div class="metric-bar"><div class="metric-fill ${getMetricClass(agent.cpu, 'blue')}" style="width:${agent.cpu}%"></div></div>
                <span class="metric-value">${agent.cpu}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">RAM</span>
                <div class="metric-bar"><div class="metric-fill ${getMetricClass(agent.ram, 'purple')}" style="width:${agent.ram}%"></div></div>
                <span class="metric-value">${agent.ram}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Disk</span>
                <div class="metric-bar"><div class="metric-fill ${getMetricClass(agent.disk, 'green')}" style="width:${agent.disk}%"></div></div>
                <span class="metric-value">${agent.disk}%</span>
            </div>
        </div>
        ${processHTML}
        <div class="pc-card-footer">
            <span class="last-seen">🕐 ${agent.last_seen_ago || agent.last_seen_str || '—'}</span>
            <span class="version">v${agent.agent_version || '?'}</span>
        </div>
    </div>`;
}

// Refresh dashboard
async function refreshDashboard() {
    try {
        const res = await fetch('/api/agents');
        const agents = await res.json();

        // Stats
        const total = agents.length;
        const online = agents.filter(a => a.status === 'online').length;
        const offline = agents.filter(a => a.status === 'offline').length;
        const warning = agents.filter(a => a.status === 'warning').length;

        document.getElementById('stat-total').textContent = total;
        document.getElementById('stat-online').textContent = online;
        document.getElementById('stat-offline').textContent = offline;
        document.getElementById('stat-warning').textContent = warning;

        // Cards
        const grid = document.getElementById('pc-grid');
        if (agents.length === 0) {
            grid.innerHTML = `<div class="empty-state"><div class="icon">📡</div><h3>Henüz PC bağlanmadı</h3><p>Agent'ları diğer PC'lerde çalıştırın, otomatik olarak burada görünecekler.</p></div>`;
        } else {
            grid.innerHTML = agents.map(buildPCCard).join('');
        }
    } catch (err) {
        console.error('Dashboard yenileme hatası:', err);
    }
}

// PC Detail page
async function refreshPCDetail(pcName) {
    try {
        const res = await fetch(`/api/agent/${pcName}`);
        if (!res.ok) return;
        const agent = await res.json();

        const statusClass = `badge-${agent.status}`;
        const statusText = { online: 'Çevrimiçi', offline: 'Çevrimdışı', warning: 'Uyarı' }[agent.status] || agent.status;

        document.getElementById('detail-status').className = `badge ${statusClass}`;
        document.getElementById('detail-status').innerHTML = `<span class="dot"></span>${statusText}`;

        document.getElementById('detail-ip').textContent = agent.ip || '—';
        document.getElementById('detail-os').textContent = agent.os_info || '—';
        document.getElementById('detail-uptime').textContent = agent.uptime || '—';
        document.getElementById('detail-version').textContent = `v${agent.agent_version || '?'}`;
        document.getElementById('detail-lastseen').textContent = agent.last_seen_str || '—';

        // Metrics
        ['cpu', 'ram', 'disk'].forEach(m => {
            const fill = document.getElementById(`detail-${m}-fill`);
            const val = document.getElementById(`detail-${m}-value`);
            if (fill && val) {
                fill.style.width = `${agent[m]}%`;
                fill.className = `metric-fill ${getMetricClass(agent[m], m === 'cpu' ? 'blue' : m === 'ram' ? 'purple' : 'green')}`;
                val.textContent = `${agent[m]}%`;
            }
        });

        // RAM & Disk details
        if (document.getElementById('detail-ram-detail'))
            document.getElementById('detail-ram-detail').textContent = `${agent.ram_used || 0} GB / ${agent.ram_total || 0} GB`;
        if (document.getElementById('detail-disk-detail'))
            document.getElementById('detail-disk-detail').textContent = `${agent.disk_used || 0} GB / ${agent.disk_total || 0} GB`;

        // Watched programs
        const watchedEl = document.getElementById('watched-programs');
        if (watchedEl && agent.watched_status) {
            watchedEl.innerHTML = Object.entries(agent.watched_status).map(([name, running]) => `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.03)">
                    <span style="display:flex;align-items:center;gap:8px">
                        <span class="process-tag ${running ? 'running' : 'stopped'}" style="margin:0">${running ? '●' : '○'} ${name}</span>
                    </span>
                    <div style="display:flex;gap:6px">
                        ${!running ? `<button class="btn btn-success btn-sm" onclick="sendCommand('${pcName}','start_program','${name}')">▶ Başlat</button>` : ''}
                        ${running ? `<button class="btn btn-danger btn-sm" onclick="sendCommand('${pcName}','stop_program','${name}')">⏹ Durdur</button>` : ''}
                    </div>
                </div>
            `).join('');
        }

        // All processes
        const allProcs = document.getElementById('all-processes');
        if (allProcs && agent.processes) {
            allProcs.innerHTML = agent.processes.slice(0, 30).map(p =>
                `<span class="process-tag running">${p}</span>`
            ).join('');
        }
    } catch (err) {
        console.error('PC detay hatası:', err);
    }
}

// Send command to agent
async function sendCommand(pcName, action, target = '') {
    try {
        const res = await fetch(`/api/command/${pcName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, target })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast(`Komut gönderildi: ${action} ${target}`, 'success');
        } else {
            showToast(`Hata: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast('Komut gönderilemedi', 'error');
    }
}

// Settings page
async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        const settings = await res.json();

        const cpuEl = document.getElementById('alert-cpu');
        const ramEl = document.getElementById('alert-ram');
        const diskEl = document.getElementById('alert-disk');
        const versionUrlEl = document.getElementById('update-version-url');
        const zipUrlEl = document.getElementById('update-zip-url');

        if (cpuEl) cpuEl.value = settings.alert_cpu_threshold || 90;
        if (ramEl) ramEl.value = settings.alert_ram_threshold || 90;
        if (diskEl) diskEl.value = settings.alert_disk_threshold || 90;
        if (versionUrlEl) versionUrlEl.value = settings.update_url_version || '';
        if (zipUrlEl) zipUrlEl.value = settings.update_url_zip || '';

        // Programs tag input
        const wrapper = document.getElementById('programs-wrapper');
        if (wrapper && settings.watched_programs) {
            settings.watched_programs.forEach(p => addTag(wrapper, p));
        }
    } catch (err) {
        console.error('Ayar yükleme hatası:', err);
    }
}

async function saveSettings() {
    const wrapper = document.getElementById('programs-wrapper');
    const programs = [];
    if (wrapper) {
        wrapper.querySelectorAll('.tag').forEach(tag => {
            programs.push(tag.dataset.value);
        });
    }

    const settings = {
        watched_programs: programs,
        alert_cpu_threshold: parseInt(document.getElementById('alert-cpu')?.value) || 90,
        alert_ram_threshold: parseInt(document.getElementById('alert-ram')?.value) || 90,
        alert_disk_threshold: parseInt(document.getElementById('alert-disk')?.value) || 90,
        update_url_version: document.getElementById('update-version-url')?.value || '',
        update_url_zip: document.getElementById('update-zip-url')?.value || '',
    };

    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        showToast('Ayarlar kaydedildi!', 'success');
    } catch (err) {
        showToast('Ayarlar kaydedilemedi', 'error');
    }
}

// Tag input helper
function addTag(wrapper, value) {
    if (!value.trim()) return;
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.dataset.value = value.trim();
    tag.innerHTML = `${value.trim()} <span class="remove" onclick="this.parentElement.remove()">×</span>`;
    const input = wrapper.querySelector('input');
    wrapper.insertBefore(tag, input);
}

function initTagInput(wrapperId) {
    const wrapper = document.getElementById(wrapperId);
    if (!wrapper) return;
    const input = wrapper.querySelector('input');
    if (!input) return;
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            addTag(wrapper, input.value);
            input.value = '';
        }
    });
}

// Custom command
function sendCustomCommand(pcName) {
    const input = document.getElementById('custom-command');
    if (!input || !input.value.trim()) return;
    sendCommand(pcName, 'custom', input.value.trim());
    input.value = '';
}
