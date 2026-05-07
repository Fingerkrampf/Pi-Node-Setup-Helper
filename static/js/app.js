/* ═══════════════════════════════════════════════════════
   Pi Node Setup Helper v12.1 — JavaScript Application
   Platform (Windows)
   ═══════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ── State ──
    let currentLang = 'en';
    let translations = {};
    let isOperating = false;
    let statusInterval = null;
    let tooltipEl = null;
    let detectedOS = 'Windows';
    let detectedArch = 'AMD64';
    let downloadDir = '';
    let config = {};
    let updateInfo = null;

    const TASKS_ORDER = [
        'wsl_setup', 'hibernate', 'firewall', 'docker',
        'pi_node', 'wireguard_client', 'wireguard_keys', 'wireguard_server'
    ];

    const TASK_ICONS = {
        wsl_setup: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>`,
        hibernate: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`,
        firewall: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
        docker: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>`,
        pi_node: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line></svg>`,
        wireguard_client: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`,
        wireguard_keys: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"></path></svg>`,
        wireguard_server: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>`,
    };

    document.addEventListener('DOMContentLoaded', init);

    function init() {
        // Preferred language: System language from backend, fallback to browser language
        currentLang = window.SYSTEM_LANG === 'de' ? 'de' : (navigator.language.startsWith('de') ? 'de' : 'en');
        tooltipEl = document.createElement('div');
        tooltipEl.className = 'tooltip-popup';
        document.body.appendChild(tooltipEl);
        loadTranslations(currentLang).then(() => {
            renderUI();
            pollStatus();
            statusInterval = setInterval(pollStatus, 5000);
            
            // Heartbeat to keep backend alive
            setInterval(() => {
                fetch('/api/heartbeat', { method: 'POST' }).catch(() => {});
            }, 5000);

            // Shutdown when browser window is closed
            window.addEventListener('unload', () => {
                navigator.sendBeacon('/api/shutdown');
            });

            // Telemetry
            if (window.Telemetry.getConsent() !== 'true') {
                showTelemetryConsent();
            }
            window.Telemetry.logEvent('app_started', { os: detectedOS, arch: detectedArch });

            // Version update check
            checkForUpdates();
        });
    }

    // ── Helpers ──
    /** Get a translation key */
    function t(key) {
        return translations[key] || key;
    }

    // ── API ──
    async function loadTranslations(lang) {
        try {
            const res = await fetch(`/api/translations/${lang}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            translations = await res.json();
        } catch (e) { 
            console.error('Failed to load translations:', e); 
            window.Telemetry.logError({ message: 'Translation load failed', error: e.toString(), lang });
        }
    }

    async function pollStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            detectedOS = data.os || 'Windows';
            detectedArch = data.arch || '';
            config = data.config || {};
            window.NODE_ID = config.node_id;
            downloadDir = config.download_dir || '';
            updateConfigUI();
            updateAllCards(data.tasks);
            updateAdminWarning(data.admin);
            updateOSBadge();
            updateHeaderStatus(data.tasks, data.pi_node_container_running);
            if (data.wsl_phase === 2 && data.tasks['wsl_setup'] && data.tasks['wsl_setup'].active && !isOperating && !window.phase2PromptShown) {
                window.phase2PromptShown = true;
                showPhase2Prompt();
            }
        } catch (e) { 
            console.error('Status poll failed:', e); 
            window.Telemetry.logError({ message: 'Status poll failed', error: e.toString() });
        }
    }

    function updateHeaderStatus(tasks, piContainerRunning) {
        const badge = document.getElementById('assistant-badge');
        const badgeText = document.getElementById('assistant-text');
        
        if (!badge) return;

        // Reset classes
        badge.classList.remove('success', 'error');

        // Pi Node is only "ONLINE" (Green Blinking) if the Docker container is actually running
        if (piContainerRunning) {
            badge.classList.add('success');
            if (badgeText) badgeText.textContent = t('node_status_online') || 'Pi Node: ONLINE';
        } else {
            badge.classList.add('error');
            if (badgeText) badgeText.textContent = t('node_status_offline') || 'Pi Node: OFFLINE';
        }

        // VPN Badge for wireguard_server
        const vpnActive = tasks['wireguard_server'] && tasks['wireguard_server'].active;
        const vpnContainer = document.getElementById('vpn-badge-container');
        if (vpnContainer) {
            if (vpnActive) {
                if (!document.getElementById('vpn-active-badge')) {
                    vpnContainer.innerHTML = `<div class="vpn-badge" id="vpn-active-badge">${t('vpn_active') || 'VPN AKTIV'}</div>`;
                }
            } else {
                vpnContainer.innerHTML = '';
            }
        }
    }
    async function checkForUpdates() {
        try {
            const res = await fetch('/api/update_check');
            const data = await res.json();
            if (data.update_available) {
                updateInfo = data;
                renderUpdateBanner();
            }
        } catch (e) { console.error('Update check failed:', e); }
    }

    function renderUpdateBanner() {
        if (!updateInfo) return;
        const banner = document.getElementById('update-banner');
        if (banner) {
            banner.innerHTML = `<span>🚀</span> ${t('update_available_text').replace('{v}', updateInfo.latest_version)}`;
            banner.classList.add('visible');
            document.body.classList.add('has-update');
            banner.onclick = () => window.open(updateInfo.url || 'https://github.com/Fingerkrampf', '_blank');
        }
    }

    async function pickConfig() {
        try {
            const res = await fetch('/api/config/pick_dir', { method: 'POST' });
            const data = await res.json();
            if (data.ok) {
                downloadDir = data.config.download_dir;
                pollStatus();
            } else if (data.error) {
                showModal('Error', data.error);
            }
        } catch (e) { showModal('Error', e.toString()); }
    }

    async function updateDownloadDir(newPath) {
        if (!newPath) return;
        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_dir: newPath })
            });
            const data = await res.json();
            if (data.ok) {
                downloadDir = data.config.download_dir;
                // Update internal input value to match normalized path from backend
                const input = document.getElementById('download-dir-input');
                if (input) input.value = downloadDir;
                pollStatus();
            }
        } catch (e) {
            console.error('Failed to update download dir:', e);
        }
    }

    function togglePasswordVisibility(inputId, btn) {
        const input = document.getElementById(inputId);
        if (!input) return;
        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
        
        const eyeOpen = btn.querySelector('.eye-open');
        const eyeClosed = btn.querySelector('.eye-closed');
        if (eyeOpen && eyeClosed) {
            eyeOpen.style.display = isPassword ? 'none' : 'block';
            eyeClosed.style.display = isPassword ? 'block' : 'none';
        }
    }

    async function openDownloadDir() {
        try {
            await fetch('/api/config/open_dir', { method: 'POST' });
        } catch (e) { console.error('Failed to open dir:', e); }
    }

    async function executeAction(taskName, actionType, extraData = {}) {
        if (isOperating) return;
        isOperating = true;
        disableAllButtons();
        const card = document.getElementById(`task-${taskName}`);
        
        if (taskName === 'wireguard_server' && actionType === 'action') {
            const settingsContainer = document.getElementById('settings-wireguard_server');
            const toggleBtn = document.querySelector('[data-target="settings-wireguard_server"]');
            
            // Check if we have values in the expanded fields
            const ip = document.getElementById('ssh-ip')?.value.trim();
            const port = document.getElementById('ssh-port')?.value.trim();
            const user = document.getElementById('ssh-user')?.value.trim();
            const pass = document.getElementById('ssh-pass')?.value;

            if (!ip || !user || !pass) {
                // If fields are empty, expand the section and don't proceed yet
                if (settingsContainer && !settingsContainer.classList.contains('visible')) {
                    settingsContainer.classList.add('visible');
                    toggleBtn?.classList.add('expanded');
                    // Focus IP field
                    document.getElementById('ssh-ip')?.focus();
                }
                isOperating = false;
                enableAllButtons();
                return;
            }

            const creds = { ip, port, user, pass };
            
            // Pre-check for existing config on server
            showProgress(card, t('connecting'));
            try {
                const checkRes = await (await fetch('/api/tasks/check_wg', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(creds)
                })).json();

                let mode = 'auto';
                if (checkRes.exists) {
                    const choice = await showChoiceModal(
                        t('wg_exists_title'),
                        t('wg_exists_text'),
                        [
                            { id: 'wipe', text: t('wg_wipe'), color: 'btn-danger' },
                            { id: 'repair', text: t('wg_repair'), color: 'btn-primary' }
                        ]
                    );
                    if (!choice) {
                        isOperating = false;
                        enableAllButtons();
                        hideProgress(card);
                        return;
                    }
                    mode = choice;
                }

                const resp = await fetch(`/api/action/${taskName}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ...creds, mode })
                });
                const data = await resp.json();
                if (data.op_id) streamLogs(data.op_id, card, taskName, actionType);
                else if (data.error) throw new Error(data.error);
            } catch (e) {
                showModal('Error', e.toString());
                isOperating = false;
                enableAllButtons();
                hideProgress(card);
            }
            return;
        }

        // Default action logic
        showProgress(card, t('connecting'));
        try {
            const body = { action_type: actionType, ...extraData };
            const res = await fetch(`/api/action/${taskName}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.error) {
                hideProgress(card);
                showModal(t('info_title'), data.error);
                isOperating = false;
                enableAllButtons();
                return;
            }
            streamLogs(data.op_id, card, taskName, actionType);
        } catch (e) {
            hideProgress(card);
            showModal('Error', e.toString());
            window.Telemetry.logError({ message: 'Action execution failed', task: taskName, action: actionType, error: e.toString() });
            isOperating = false;
            enableAllButtons();
        }
    }

    function streamLogs(opId, card, taskName, actionType) {
        const actionWord = actionType === 'uninstall' ? (t('uninstall') || 'Uninstall') : (t('install') || 'Install');
        const titleText = `${actionWord}: ${t(taskName)}`;
        const logModal = showLogModal(titleText);
        const logBox = logModal.querySelector('.log-output');
        const source = new EventSource(`/api/logs/${opId}`);
        source.onmessage = function (event) {
            const data = JSON.parse(event.data);
            if (data.log) {
                logBox.textContent += data.log + '\n';
                logBox.scrollTop = logBox.scrollHeight;
                updateProgressText(card, data.log);
            }
            if (data.done || data.error) {
                source.close();
                hideProgress(card);
                isOperating = false;
                enableAllButtons();
                pollStatus();
                logModal.querySelector('.modal-close').disabled = false;
                
                if (!data.error && taskName === 'pi_node' && actionType === 'action') {
                    window.Telemetry.logEvent('pi_node_started', { success: true });
                }

                if (!data.error && taskName === 'wsl_setup' && actionType === 'action') {
                    const logTxt = logBox.textContent || '';
                    if (logTxt.includes("A system restart is REQUIRED now.")) {
                        window.phase2PromptShown = true;
                        setTimeout(() => showRestartPrompt(), 800);
                    }
                }
            }
        };
        source.onerror = function () {
            source.close();
            hideProgress(card);
            isOperating = false;
            enableAllButtons();
            pollStatus();
        };
    }

    async function showRestartPrompt() {
        const choice = await showChoiceModal(
            t('phase1_restart_title') || "Restart Required",
            t('phase1_restart_text') || "The Windows features have been successfully enabled. Your computer must now be restarted.",
            [
                { id: 'later', text: t('restart_later') || "Later", color: 'btn-ghost' },
                { id: 'restart', text: t('restart_now') || "Restart Now", color: 'btn-danger' }
            ]
        );
        if (choice === 'restart') {
            fetch('/api/restart', { method: 'POST' }).catch(() => {});
        }
    }

    async function showPhase2Prompt() {
        const choice = await showChoiceModal(
            t('phase2_title') || "Phase 2",
            t('phase2_text') || "Phase 2 will now begin.",
            [
                { id: 'start', text: t('start') || "Start Phase 2", color: 'btn-primary' }
            ]
        );
        if (choice === 'start') {
            executeAction('wsl_setup', 'action');
        }
    }

    async function showTelemetryConsent() {
        const choice = await showChoiceModal(
            t('telemetry_consent_title'),
            t('telemetry_consent_text'),
            [
                { id: 'accept', text: t('telemetry_consent_accept'), color: 'btn-primary' },
                { id: 'decline', text: t('exit'), color: 'btn-ghost' }
            ],
            false // Not dismissible
        );
        
        if (choice === 'accept') {
            window.Telemetry.setConsent(true);
            renderUI();
        } else {
            // Shutdown tool and close window
            fetch('/api/shutdown', { method: 'POST' }).finally(() => {
                window.close();
            });
        }
    }

    // ── Rendering ──
    function renderUI() {
        const container = document.getElementById('app-root');
        container.innerHTML = `
            <div id="update-banner" class="update-banner"></div>
            <div class="bg-effects">
                <div class="bg-orb bg-orb--1"></div>
                <div class="bg-orb bg-orb--2"></div>
                <div class="bg-orb bg-orb--3"></div>
            </div>
            <div class="bg-grid"></div>
        `;
        const appDiv = document.createElement('div');
        appDiv.className = 'app-container';
        appDiv.innerHTML = renderHeader() + renderAdminWarning() + renderConfigSection() + renderTasks() + renderFooter();
        container.appendChild(appDiv);
        renderUpdateBanner();
        bindEvents();
    }

    function renderConfigSection() {
        return `
            <div class="config-section">
                <div class="config-header">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    <span>${t('download_dir_label')}</span>
                    <button class="task-tooltip-btn" data-tooltip="${escapeAttr(t('download_dir_info'))}" aria-label="Info">&#9432;</button>
                </div>
                <div class="config-body" style="margin-bottom:8px; display:flex; gap:8px; flex-wrap:wrap;">
                    <input type="text" class="path-input" id="download-dir-input" value="${escapeAttr(downloadDir || '')}" 
                        style="height:38px; flex:1; min-width:200px;"
                        onchange="app.updateDownloadDir(this.value)">
                    <div style="display:flex; gap:8px;">
                        <button class="btn btn-secondary btn-sm" onclick="app.pickConfig()" style="height:38px; white-space:nowrap;">
                            ${t('change')}
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="app.openDownloadDir()" style="height:38px; white-space:nowrap;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                            ${t('open_dir')}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    function renderHeader() {
        const osLabel = `Windows (${detectedArch})`;
        return `
            <header class="app-header">
                <div class="header-profile">
                    <a href="https://github.com/Fingerkrampf" target="_blank" rel="noopener">
                        <img src="https://avatars.githubusercontent.com/u/210079376?v=4" alt="Fingerkrampf Profile" class="profile-img">
                    </a>
                </div>
                <div class="header-content">
                    <div class="header-badge" id="assistant-badge">
                        <span class="badge-dot"></span>
                        <span id="assistant-text">Pi Node Status</span>
                    </div>
                    <div id="vpn-badge-container" style="display: inline-block;"></div>
                    <h1 class="app-title">${t('title')}</h1>
                    <p class="app-subtitle">${t('subtitle')} &middot; <a href="https://github.com/Fingerkrampf" target="_blank" rel="noopener">GitHub</a></p>
                    <div class="os-badge" id="os-badge">
                        &#8862; ${osLabel}
                    </div>
                </div>
            </header>
        `;
    }

    function renderAdminWarning() {
        const msg = t('needs_admin');
        return `
            <div class="admin-warning" id="admin-warning" style="display:none;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                <span>${msg}</span>
            </div>
        `;
    }

    function renderTasks() {
        let html = '<div class="tasks-container" id="tasks-container">';
        let wgNoteInserted = false;

        TASKS_ORDER.forEach((name, i) => {
            if (name === 'wireguard_client' && !wgNoteInserted) {
                wgNoteInserted = true;
                html += `
                    <div class="wg-note" id="wg-note">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                        <span>${t('wg_client_note')}</span>
                    </div>`;
            }

            const taskLabel = t(name);
            const tooltipKey = name + '_tooltip';
            const tooltipText = t(tooltipKey);

            const isExpandable = name === 'firewall' || name === 'wireguard_server';

            html += `
                <div class="task-card" id="task-${name}" data-task="${name}">
                    <div class="task-number">${i + 1}</div>
                    <div class="task-info">
                        <div class="task-title-row">
                            <span class="task-title">${taskLabel}</span>
                            ${tooltipText !== tooltipKey ? `<button class="task-tooltip-btn" data-tooltip="${escapeAttr(tooltipText)}" aria-label="Info">&#9432;</button>` : ''}
                        </div>
                        <div class="task-status">
                            <span class="status-dot"></span>
                            <span class="task-status-text">&mdash;</span>
                        </div>
                        ${isExpandable ? `
                            <button class="task-settings-toggle" data-target="settings-${name}">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                                ${name === 'firewall' ? (t('config_header') || 'Custom Port Settings') : (t('ssh_prompt_title') || 'SSH Configuration')}
                            </button>
                        ` : ''}
                        <div class="task-progress" id="progress-${name}">
                            <div class="progress-bar-container"><div class="progress-bar"></div></div>
                            <span class="progress-text" id="progress-text-${name}"></span>
                        </div>
                    </div>
                    <div class="task-actions" id="actions-${name}"></div>
                    <div class="task-status-icon" id="icon-${name}">&mdash;</div>
                    
                    ${name === 'firewall' ? `
                        <div class="task-expanded-settings" id="settings-firewall">
                            <div class="settings-grid">
                                <div class="form-group">
                                    <label style="display:block;font-size:0.75rem;font-weight:600;color:var(--text-muted);margin-bottom:4px;">${t('tcp_ports_label')}</label>
                                    <input type="text" class="form-input config-auto-save" id="config-tcp-ports" value="${escapeAttr(config.tcp_ports || '31400-31409')}" placeholder="31400-31409">
                                </div>
                                <div class="form-group">
                                    <label style="display:block;font-size:0.75rem;font-weight:600;color:var(--text-muted);margin-bottom:4px;">${t('udp_ports_label')}</label>
                                    <input type="text" class="form-input config-auto-save" id="config-udp-ports" value="${escapeAttr(config.udp_ports || '51820')}" placeholder="51820">
                                </div>
                            </div>
                            <p style="font-size:0.7rem; color:var(--text-muted); margin-top:12px; line-height:1.4;">
                                ${t('config_info')}
                            </p>
                        </div>
                    ` : ''}

                    ${name === 'wireguard_server' ? `
                        <div class="task-expanded-settings" id="settings-wireguard_server">
                            <div class="ssh-settings-grid">
                                <div class="form-group"><label>${t('server_ip') || 'Server IP'}</label><input type="text" class="form-input config-auto-save" id="ssh-ip" value="${escapeAttr(config.ssh_ip || '')}" placeholder="1.2.3.4"></div>
                                <div class="form-group"><label>${t('ssh_port') || 'SSH Port'}</label><input type="number" class="form-input config-auto-save" id="ssh-port" value="${escapeAttr(config.ssh_port || '22')}"></div>
                                <div class="form-group"><label>${t('username') || 'Username'}</label><input type="text" class="form-input config-auto-save" id="ssh-user" value="${escapeAttr(config.ssh_user || 'root')}"></div>
                                <div class="form-group">
                                    <label>${t('password') || 'Password'}</label>
                                    <div class="password-wrapper">
                                        <input type="password" class="form-input" id="ssh-pass" placeholder="********">
                                        <button class="password-toggle" onclick="app.togglePasswordVisibility('ssh-pass', this)" type="button" aria-label="Toggle password visibility">
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-open"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-closed" style="display:none;"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ` : ''}
                </div>`;
        });
        html += '</div>';
        return html;
    }

    function renderFooter() {
        return `
            <div class="footer-bar" id="footer-bar">
                <div class="footer-group">
                    <button class="btn btn-ghost" onclick="app.showHelp()">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                        ${t('help')}
                    </button>
                    <a class="btn btn-ghost" href="https://github.com/Fingerkrampf" target="_blank" rel="noopener">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
                        ${t('github')}
                    </a>
                    <button class="btn btn-ghost" id="btn-donate">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l8.84-8.84 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                        ${t('donate')}
                    </button>
                </div>
                <div class="footer-separator"></div>
                <div class="footer-group">
                    <span class="theme-toggle-label">&#127769;</span>
                    <div class="theme-toggle" id="theme-toggle" role="button" tabindex="0" aria-label="Toggle theme"></div>
                    <span class="theme-toggle-label">&#9728;&#65039;</span>
                </div>
                <div class="footer-separator"></div>
                <div class="footer-group">
                    <div class="lang-toggle" id="lang-toggle">
                        <button class="lang-option ${currentLang === 'de' ? 'active' : ''}" data-lang="de">DE</button>
                        <button class="lang-option ${currentLang === 'en' ? 'active' : ''}" data-lang="en">EN</button>
                    </div>
                </div>
                <div class="footer-separator"></div>
                <div class="footer-group">
                    <span class="copyright-text" style="font-size:0.75rem;color:var(--text-muted);font-weight:500;">Copyright by Fingerkrampf 2026</span>
                </div>
            </div>`;
    }

    // ── Events ──
    function bindEvents() {
        document.getElementById('btn-donate')?.addEventListener('click', showDonateModal);
        document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);
        document.getElementById('btn-update-config')?.addEventListener('click', pickConfig);
        document.getElementById('btn-save-ports')?.remove(); // Cleanup old listener if still exists
        document.querySelectorAll('.config-auto-save').forEach(input => {
            input.addEventListener('change', saveConfig);
        });
        document.querySelectorAll('.lang-option').forEach(btn => btn.addEventListener('click', () => switchLang(btn.dataset.lang)));
        document.querySelectorAll('.task-tooltip-btn').forEach(btn => {
            btn.addEventListener('mouseenter', showTooltip);
            btn.addEventListener('mouseleave', hideTooltip);
            btn.addEventListener('focus', showTooltip);
            btn.addEventListener('blur', hideTooltip);
        });
        document.querySelectorAll('.task-settings-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const targetId = btn.dataset.target;
                const target = document.getElementById(targetId);
                if (target) {
                    const isVisible = target.classList.toggle('visible');
                    btn.classList.toggle('expanded', isVisible);
                }
            });
        });
    }

    // ── Card Updates ──
    function updateAllCards(tasks) {
        for (const name of TASKS_ORDER) {
            if (tasks[name]) updateCard(name, tasks[name]);
        }
    }

    function updateCard(name, task) {
        const card = document.getElementById(`task-${name}`);
        if (!card) return;
        card.classList.remove('active', 'inactive');
        card.classList.add(task.active ? 'active' : 'inactive');
        const iconEl = document.getElementById(`icon-${name}`);
        if (iconEl) iconEl.textContent = task.active ? '\u2713' : '\u2717';

        const titleEl = card.querySelector('.task-title');
        if (titleEl) {
            if (name === 'firewall') {
                const tcp = config.tcp_ports || '31400-31409';
                const udp = config.udp_ports || '51820';
                titleEl.textContent = `${t(name)} (TCP: ${tcp}, UDP: ${udp})`;
            } else {
                titleEl.textContent = t(name);
            }
        }

        const st = card.querySelector('.task-status-text');
        if (st) st.textContent = getStatusText(task.type, task.active);
        const act = document.getElementById(`actions-${name}`);
        if (act && !isOperating) {
            act.innerHTML = renderActionButtons(name, task);
            bindActionButtons(name);
        }
    }

    function getStatusText(type, active) {
        const map = {
            install: [t('status_not_installed'), t('status_installed')],
            activate: [t('status_not_active'), t('status_active')],
            generate: [t('status_no_keys'), t('status_keys_generated')],
            configure: [t('status_not_configured'), t('status_configured')]
        };
        const p = map[type] || ['--', '--'];
        return active ? p[1] : p[0];
    }

    function renderActionButtons(name, task) {
        const labels = {
            install: [t('install'), t('uninstall')],
            activate: [t('activate'), t('deactivate')],
            generate: [t('generate'), t('delete')],
            configure: [t('configure'), t('delete')]
        };
        const l = labels[task.type] || ['Action', 'Undo'];
        if (task.active) {
            return task.has_uninstall
                ? `<button class="btn btn-danger btn-action" data-task="${name}" data-action="uninstall">${l[1]}</button>`
                : '';
        }
        
        // Manual download logic for installers
        if (task.type === 'install') {
            if (task.installer_ready) {
                return `<button class="btn btn-primary btn-action" data-task="${name}" data-action="action">${l[0]}</button>`;
            } else {
                return `<a href="${task.download_url}" target="_blank" rel="noopener" class="btn btn-ghost" style="color:var(--accent);border-color:var(--accent);">${t('download_page')}</a>`;
            }
        }
        
        let btnLabel = l[0];
        if (name === 'wireguard_server' && !task.active) {
            btnLabel = t('connect') || 'Verbinden';
        }
        
        return `<button class="btn btn-primary btn-action" data-task="${name}" data-action="action">${btnLabel}</button>`;
    }

    function updateConfigUI() {
        const pEl = document.getElementById('download-dir-input');
        if (pEl && document.activeElement !== pEl) pEl.value = downloadDir;
        
        const tcpInput = document.getElementById('config-tcp-ports');
        if (tcpInput && config.tcp_ports && document.activeElement !== tcpInput) {
            tcpInput.value = config.tcp_ports;
        }
        const udpInput = document.getElementById('config-udp-ports');
        if (udpInput && config.udp_ports && document.activeElement !== udpInput) {
            udpInput.value = config.udp_ports;
        }
    }

    function bindActionButtons(name) {
        document.getElementById(`actions-${name}`)?.querySelectorAll('.btn-action').forEach(btn => {
            btn.addEventListener('click', () => {
                executeAction(btn.dataset.task, btn.dataset.action);
            });
        });
    }

    function updateAdminWarning(isAdmin) {
        const el = document.getElementById('admin-warning');
        if (el) el.style.display = isAdmin ? 'none' : 'flex';
    }

    function updateOSBadge() {
        const badge = document.getElementById('os-badge');
        if (!badge) return;
        const osLabel = `Windows (${detectedArch})`;
        badge.innerHTML = `&#8862; ${osLabel}`;
    }

    // ── Progress ──
    function showProgress(card, text) {
        if (!card) return;
        const p = card.querySelector('.task-progress');
        if (p) p.classList.add('visible');
        updateProgressText(card, text);
    }
    function hideProgress(card) {
        if (!card) return;
        const p = card.querySelector('.task-progress');
        if (p) p.classList.remove('visible');
    }
    function updateProgressText(card, text) {
        if (!card || !text) return;
        const el = card.querySelector('.progress-text');
        if (el) {
            const clean = text.replace(/[\r\n]+/g, ' ').trim();
            if (clean) el.textContent = clean.substring(0, 80);
        }
    }
    function disableAllButtons() {
        document.querySelectorAll('.btn-action, .btn-ghost, .lang-option').forEach(b => b.disabled = true);
    }
    function enableAllButtons() {
        document.querySelectorAll('.btn-action, .btn-ghost, .lang-option').forEach(b => b.disabled = false);
    }

    // ── Theme / Lang ──
    function toggleTheme() {
        const tgl = document.getElementById('theme-toggle');
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        if (isLight) { document.documentElement.removeAttribute('data-theme'); tgl.classList.remove('light'); }
        else { document.documentElement.setAttribute('data-theme', 'light'); tgl.classList.add('light'); }
    }
    async function switchLang(lang) {
        if (lang === currentLang) return;
        currentLang = lang;
        await loadTranslations(lang);
        renderUI();
        pollStatus();
    }

    // ── Tooltip ──
    function showTooltip(e) {
        let text = e.target.dataset.tooltip;
        const taskRow = e.target.closest('.task-card');
        if (taskRow) {
             const name = taskRow.dataset.task;
            if (name === 'firewall') {
                const tcp = config.tcp_ports || '31400-31409';
                const udp = config.udp_ports || '51820';
                
                if (taskRow.classList.contains('active')) {
                    text = t('firewall_info_text');
                }
                
                // Replace any mention of the default range with actual ports
                text = text.replace(/31400[–-]31409/g, tcp);
                // Ensure UDP is mentioned if relevant
                if (!text.includes(udp)) text += ` (UDP: ${udp})`;
            }
        }
        if (!text || !tooltipEl) return;
        tooltipEl.textContent = text;
        tooltipEl.classList.add('visible');
        const rect = e.target.getBoundingClientRect();
        const tR = tooltipEl.getBoundingClientRect();
        let left = rect.left + rect.width / 2 - tR.width / 2;
        let top = rect.bottom + 8;
        if (left < 8) left = 8;
        if (left + tR.width > window.innerWidth - 8) left = window.innerWidth - tR.width - 8;
        if (top + tR.height > window.innerHeight - 8) top = rect.top - tR.height - 8;
        tooltipEl.style.left = left + 'px';
        tooltipEl.style.top = top + 'px';
    }
    function hideTooltip() { if (tooltipEl) tooltipEl.classList.remove('visible'); }

    // ── SSH Dialog ──
    function showSSHDialog() {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay visible';
            overlay.innerHTML = `
                <div class="modal">
                    <h2 class="modal-title">${t('ssh_prompt_title') || 'SSH Configuration'}</h2>
                    <p class="modal-body" style="margin-bottom:16px;">${t('ssh_prompt_text') || 'Enter your server credentials'}</p>
                    <form class="ssh-form" id="ssh-form">
                        <div class="form-group"><label>Server IP</label><input type="text" class="form-input" id="ssh-ip" value="${escapeAttr(config.ssh_ip || '')}" placeholder="1.2.3.4" required></div>
                        <div class="form-group"><label>${t('ssh_port') || 'SSH Port'}</label><input type="number" class="form-input" id="ssh-port" value="${escapeAttr(config.ssh_port || '22')}" required></div>
                        <div class="form-group"><label>Username</label><input type="text" class="form-input" id="ssh-user" value="${escapeAttr(config.ssh_user || 'root')}" required></div>
                        <div class="form-group"><label>${t('password') || 'Password'}</label><input type="password" class="form-input" id="ssh-pass" placeholder="********" required></div>
                        <div class="modal-actions" style="margin-top:8px;">
                            <button type="button" class="btn btn-ghost" id="ssh-cancel">${t('close')}</button>
                            <button type="submit" class="btn btn-primary">${t('connect')}</button>
                        </div>
                    </form>
                </div>`;
            document.body.appendChild(overlay);
            
            const cancel = document.getElementById('ssh-cancel');
            cancel.onclick = () => { overlay.remove(); resolve(null); };
            
            document.getElementById('ssh-form').onsubmit = (e) => {
                e.preventDefault();
                const creds = {
                    ip: document.getElementById('ssh-ip').value.trim(),
                    port: document.getElementById('ssh-port').value.trim(),
                    user: document.getElementById('ssh-user').value.trim(),
                    pass: document.getElementById('ssh-pass').value
                };
                overlay.remove();
                resolve(creds);
            };
            document.getElementById('ssh-ip').focus();
        });
    }

    async function showChoiceModal(title, text, options, dismissible = true) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay visible';
            overlay.innerHTML = `
                <div class="modal" style="max-width:600px;">
                    <h2 class="modal-title">${escapeHtml(title)}</h2>
                    <div class="modal-body" style="margin-bottom:24px;">${escapeHtml(text)}</div>
                    <div class="modal-actions">
                        ${dismissible ? `<button class="btn btn-ghost" id="choice-cancel">${t('close')}</button>` : ''}
                        ${options.map(o => `<button class="btn ${o.color}" id="btn-${o.id}">${escapeHtml(o.text)}</button>`).join('')}
                    </div>
                </div>`;
            document.body.appendChild(overlay);
            
            if (dismissible) {
                document.getElementById('choice-cancel').onclick = () => { overlay.remove(); resolve(null); };
            }
            options.forEach(o => {
                document.getElementById(`btn-${o.id}`).onclick = () => { overlay.remove(); resolve(o.id); };
            });
        });
    }

    // ── Config Save ──
    async function saveConfig() {
        const tcp = document.getElementById('config-tcp-ports')?.value.trim();
        const udp = document.getElementById('config-udp-ports')?.value.trim();
        const sshIp = document.getElementById('ssh-ip')?.value.trim();
        const sshPort = document.getElementById('ssh-port')?.value.trim();
        const sshUser = document.getElementById('ssh-user')?.value.trim();

        const payload = {};
        if (tcp) payload.tcp_ports = tcp;
        if (udp) payload.udp_ports = udp;
        if (sshIp) payload.ssh_ip = sshIp;
        if (sshPort) payload.ssh_port = sshPort;
        if (sshUser) payload.ssh_user = sshUser;

        try {
            const res = await fetch('/api/config', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            // Optional: feedback
            if (data.ok) {
                console.log('Config saved:', data.config);
            }
        } catch (e) { console.error('Auto-save failed:', e); }
    }

    function showHelpModal() {
        const title = t('info_title');
        const body = t('info_text');
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" style="max-width:600px;">
                <h2 class="modal-title">${escapeHtml(title)}</h2>
                <div class="modal-body" style="white-space: pre-wrap;">${body}</div>
                
                <div class="telemetry-info-section" style="margin-top:24px; padding-top:24px; border-top:1px solid rgba(255,255,255,0.05);">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:600;">${t('telemetry_status')}</span>
                        <span style="color:var(--success); font-weight:600;">${t('telemetry_enabled')}</span>
                    </div>
                </div>

                <div class="uuid-display-section" style="margin-top:12px; font-size:0.75rem; color:var(--text-secondary); text-align:center; opacity:0.8;">
                    UUID: ${window.NODE_ID || 'unknown'}
                </div>

                <div class="modal-actions" style="margin-top:24px;">
                    <button class="btn btn-primary modal-close">OK</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add('visible'));
        
        const close = () => { 
            overlay.classList.remove('visible'); 
            setTimeout(() => overlay.remove(), 300); 
        };

        overlay.querySelector('.modal-close').addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    }

    // ── Modals ──
    function showModal(title, body) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `<div class="modal"><h2 class="modal-title">${escapeHtml(title)}</h2><div class="modal-body">${escapeHtml(body)}</div><div class="modal-actions"><button class="btn btn-primary modal-close">OK</button></div></div>`;
        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add('visible'));
        const close = () => { overlay.classList.remove('visible'); setTimeout(() => overlay.remove(), 300); };
        overlay.querySelector('.modal-close').addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    }

    function showLogModal(title) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" style="max-width:700px;">
                <h2 class="modal-title">${escapeHtml(title)}</h2>
                <div class="log-output"></div>
                <div class="modal-actions" style="margin-top:16px;">
                    <button class="btn btn-ghost" id="log-copy">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                        ${t('copy_content')}
                    </button>
                    <button class="btn btn-primary modal-close" disabled>${t('close')}</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add('visible'));
        const close = () => { overlay.classList.remove('visible'); setTimeout(() => overlay.remove(), 300); };
        overlay.querySelector('.modal-close').addEventListener('click', close);
        overlay.querySelector('#log-copy').addEventListener('click', () => {
            navigator.clipboard.writeText(overlay.querySelector('.log-output').textContent).catch(() => { });
        });
        return overlay;
    }

    function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
    function escapeAttr(s) { 
        if (s == null) return '';
        return String(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); 
    }

    async function showDonateModal() {
        try {
            const res = await fetch('/api/qr_code');
            const data = await res.json();
            if (data.ok) {
                const overlay = document.createElement('div');
                overlay.className = 'modal-overlay';
                overlay.innerHTML = `
                    <div class="modal" style="max-width:400px;text-align:center;">
                        <h2 class="modal-title">${t('donate')}</h2>
                        <div class="modal-body">
                            <p style="margin-bottom:16px;">${currentLang === 'de' ? 'Vielen Dank für deine Unterstützung!' : 'Thank you for your support!'}</p>
                            <div style="background:#fff;padding:16px;border-radius:16px;display:inline-block;margin-bottom:12px;">
                                <img src="${data.base64}" style="max-width:250px;width:100%;height:auto;display:block;" alt="QR Code">
                            </div>
                        </div>
                        <div class="modal-actions" style="justify-content:center;margin-top:16px;">
                            <button class="btn btn-primary modal-close">${t('close')}</button>
                        </div>
                    </div>`;
                document.body.appendChild(overlay);
                requestAnimationFrame(() => overlay.classList.add('visible'));
                const close = () => { overlay.classList.remove('visible'); setTimeout(() => overlay.remove(), 300); };
                overlay.querySelector('.modal-close').addEventListener('click', close);
                overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
            } else {
                showModal(t('donate'), currentLang === 'de' ? "Aktuell ist kein QR-Code hinterlegt. Bitte trage den Base64-Code in der Datei qr_code.txt ein." : "No QR code is currently set. Please enter the base64 code in the qr_code.txt file.");
            }
        } catch (e) {
            showModal('Error', e.toString());
        }
    }

    // Expose public API
    window.app = {
        init,
        executeAction,
        pickConfig,
        openDownloadDir,
        updateDownloadDir,
        togglePasswordVisibility,
        showHelp: showHelpModal,
        showDonation: showDonateModal
    };
})();
