(function() {
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // Toast
    function toast(msg) {
        const el = $('#toast');
        el.textContent = msg;
        el.classList.add('show');
        setTimeout(() => el.classList.remove('show'), 2000);
    }

    // Tabs
    $$('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            $$('.tab').forEach(t => t.classList.remove('active'));
            $$('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            $(`#tab-${tab.dataset.tab}`).classList.add('active');
            if (tab.dataset.tab === 'rules') loadRules();
            if (tab.dataset.tab === 'downloads') loadDownloads();
        });
    });

    // Modal
    const modal = $('#config-modal');
    const form = $('#config-form');
    let editingName = null;
    let regionOptions = [];
    let regionLabels = {};

    function openModal(config, name) {
        editingName = name || null;
        $('#modal-title').textContent = name ? '编辑配置' : '添加配置';
        $('#cfg-name').value = name || '';
        $('#cfg-name').disabled = false;
        $('#cfg-url').value = config ? config.url : '';
        $('#cfg-type').value = config ? (config.type || 'yaml') : 'yaml';
        $('#cfg-vip').checked = config ? config.enable_vip !== false : true;
        $('#cfg-skip-rules').checked = config ? !!config.skip_rules_file : false;
        $('#cfg-load-balance').checked = config ? !!config.default_load_balance : false;
        $('#cfg-region-mode').value = config ? (config.region_filter_mode || 'off') : 'off';
        renderRegionOptions(config ? (config.region_filter_regions || []) : []);
        syncRegionOptionsState();
        modal.classList.add('show');
    }

    function closeModal() {
        modal.classList.remove('show');
        form.reset();
        editingName = null;
        $('#cfg-name').disabled = false;
    }

    $('#btn-add-config').addEventListener('click', () => openModal(null, null));
    $('#btn-cancel-modal').addEventListener('click', closeModal);
    $('#cfg-region-mode').addEventListener('change', syncRegionOptionsState);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = $('#cfg-name').value.trim();
        const data = {
            url: $('#cfg-url').value.trim(),
            type: $('#cfg-type').value,
            enable_vip: $('#cfg-vip').checked,
            skip_rules_file: $('#cfg-skip-rules').checked,
            default_load_balance: $('#cfg-load-balance').checked,
            region_filter_mode: $('#cfg-region-mode').value,
            region_filter_regions: getSelectedRegions(),
        };

        try {
            if (editingName) {
                if (name !== editingName) {
                    data.new_name = name;
                }
                await fetch(`/api/configs/${encodeURIComponent(editingName)}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data),
                });
            } else {
                data.name = name;
                await fetch('/api/configs', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data),
                });
            }
            toast('保存成功');
            closeModal();
            loadConfigs();
        } catch (err) {
            toast('保存失败: ' + err.message);
        }
    });

    // Load configs
    async function loadConfigs() {
        const resp = await fetch('/api/configs');
        if (resp.status === 401) { window.location.href = '/login'; return; }
        const configs = await resp.json();
        const tbody = $('#configs-table tbody');
        tbody.innerHTML = '';

        for (const [name, cfg] of Object.entries(configs)) {
            const tr = document.createElement('tr');
            const tags = [];
            if (cfg.enable_vip !== false) tags.push('<span class="tag tag-vip">AI 专线</span>');
            if (cfg.skip_rules_file) tags.push('<span class="tag tag-skip">跳过规则</span>');
            if (cfg.default_load_balance) tags.push('<span class="tag tag-lb">负载均衡</span>');
            const regionTag = formatRegionFilterTag(cfg);
            if (regionTag) tags.push(regionTag);

            const convertUrl = `/convert?config=${encodeURIComponent(name)}`;

            tr.innerHTML = `
                <td><strong>${esc(name)}</strong></td>
                <td><span class="url-cell" title="${esc(cfg.url)}">${esc(cfg.url)}</span></td>
                <td><span class="tag">${esc(cfg.type || 'yaml')}</span></td>
                <td>${tags.join(' ')}</td>
                <td>
                    <div class="actions">
                        <button class="btn btn-sm btn-secondary btn-copy" data-url="${esc(convertUrl)}">复制链接</button>
                        <button class="btn btn-sm btn-secondary btn-edit" data-name="${esc(name)}">编辑</button>
                        <button class="btn btn-sm btn-danger btn-delete" data-name="${esc(name)}">删除</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        }

        // Bind edit/delete
        tbody.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const name = btn.dataset.name;
                openModal(configs[name], name);
            });
        });

        tbody.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                const name = btn.dataset.name;
                if (!confirm(`确定删除配置 "${name}"？`)) return;
                await fetch(`/api/configs/${encodeURIComponent(name)}`, { method: 'DELETE' });
                toast('已删除');
                loadConfigs();
            });
        });

        tbody.querySelectorAll('.btn-copy').forEach(btn => {
            btn.addEventListener('click', () => {
                const url = window.location.origin + btn.dataset.url;
                copyText(url);
            });
        });
    }

    // Clear cache
    $('#btn-clear-cache').addEventListener('click', async () => {
        await fetch('/api/clear-cache', { method: 'POST' });
        toast('缓存已清除');
    });

    $('#btn-refresh-downloads').addEventListener('click', loadDownloads);

    async function loadRegionOptions() {
        const resp = await fetch('/api/region-options');
        if (resp.status === 401) { window.location.href = '/login'; return; }
        regionOptions = await resp.json();
        regionLabels = regionOptions.reduce((acc, option) => {
            acc[option.key] = option.label;
            return acc;
        }, {});
        renderRegionOptions([]);
    }

    function renderRegionOptions(selectedRegions) {
        const picker = $('#cfg-region-picker');
        const selected = new Set(selectedRegions || []);
        picker.innerHTML = regionOptions.map(option => `
            <label class="region-option">
                <input type="checkbox" value="${esc(option.key)}" ${selected.has(option.key) ? 'checked' : ''}>
                <span>${esc(option.label)}</span>
            </label>
        `).join('');
    }

    function syncRegionOptionsState() {
        const disabled = $('#cfg-region-mode').value === 'off';
        const picker = $('#cfg-region-picker');
        picker.classList.toggle('is-disabled', disabled);
        picker.querySelectorAll('input').forEach(input => {
            input.disabled = disabled;
        });
    }

    function getSelectedRegions() {
        return Array.from($('#cfg-region-picker').querySelectorAll('input:checked'))
            .map(input => input.value);
    }

    function formatRegionFilterTag(cfg) {
        const mode = cfg.region_filter_mode || 'off';
        const regions = cfg.region_filter_regions || [];
        if (mode === 'off' || !regions.length) return '';
        const names = regions.map(key => regionLabels[key] || key);
        const prefix = mode === 'include' ? '仅' : '排除';
        return `<span class="tag tag-region">${esc(prefix + names.join('、'))}</span>`;
    }

    // Rules
    async function loadRules() {
        const resp = await fetch('/api/rules');
        if (resp.status === 401) { window.location.href = '/login'; return; }
        const data = await resp.json();
        $('#rules-editor').value = data.content;
    }

    $('#btn-save-rules').addEventListener('click', async () => {
        const content = $('#rules-editor').value;
        await fetch('/api/rules', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ content }),
        });
        toast('规则已保存');
    });

    async function loadDownloads() {
        const resp = await fetch('/api/downloads');
        if (resp.status === 401) { window.location.href = '/login'; return; }
        const data = await resp.json();
        const tbody = $('#downloads-table tbody');
        const rows = [];

        (data.files || []).forEach(item => {
            const url = absoluteUrl(item.url);
            rows.push(`
                <tr>
                    <td><strong>${esc(item.label || item.filename)}</strong></td>
                    <td><span class="tag">${esc(item.kind || '文件')}</span></td>
                    <td>
                        <span>${esc(formatBytes(item.size))}</span>
                        <span class="muted-cell">${esc(formatTime(item.modified_at))}</span>
                    </td>
                    <td><span class="url-cell" title="${esc(url)}">${esc(url)}</span></td>
                    <td>
                        <div class="actions">
                            <button class="btn btn-sm btn-secondary btn-copy-text" data-copy="${esc(url)}">复制链接</button>
                            <a class="btn btn-sm btn-secondary" href="${esc(item.url)}">下载</a>
                            <button class="btn btn-sm btn-secondary btn-upload-file" data-upload-url="${esc(item.upload_url)}" data-filename="${esc(item.filename)}">更新文件</button>
                            <input class="hosted-file-input" type="file" data-upload-url="${esc(item.upload_url)}" data-filename="${esc(item.filename)}">
                        </div>
                    </td>
                </tr>
            `);
        });

        (data.scripts || []).forEach(item => {
            const url = absoluteUrl(item.url);
            const command = `wget -O - ${url} | sh`;
            rows.push(`
                <tr>
                    <td><strong>${esc(item.label)}</strong></td>
                    <td><span class="tag tag-script">下载脚本</span></td>
                    <td>-</td>
                    <td><span class="url-cell command-cell" title="${esc(command)}">${esc(command)}</span></td>
                    <td>
                        <div class="actions">
                            <button class="btn btn-sm btn-secondary btn-copy-text" data-copy="${esc(command)}">复制命令</button>
                            <button class="btn btn-sm btn-secondary btn-copy-text" data-copy="${esc(url)}">复制链接</button>
                        </div>
                    </td>
                </tr>
            `);
        });

        tbody.innerHTML = rows.join('');
        tbody.querySelectorAll('.btn-copy-text').forEach(btn => {
            btn.addEventListener('click', () => copyText(btn.dataset.copy));
        });
        tbody.querySelectorAll('.btn-upload-file').forEach(btn => {
            btn.addEventListener('click', () => {
                const input = btn.parentElement.querySelector('.hosted-file-input');
                input.click();
            });
        });
        tbody.querySelectorAll('.hosted-file-input').forEach(input => {
            input.addEventListener('change', () => uploadHostedFile(input));
        });
    }

    async function uploadHostedFile(input) {
        const file = input.files[0];
        if (!file) return;

        const filename = input.dataset.filename;
        if (!confirm(`确定用 "${file.name}" 覆盖托管文件 "${filename}"？`)) {
            input.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        const button = input.parentElement.querySelector('.btn-upload-file');
        button.disabled = true;
        button.textContent = '上传中';

        try {
            const resp = await fetch(input.dataset.uploadUrl, {
                method: 'POST',
                body: formData,
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                throw new Error(data.error || '上传失败');
            }
            toast('文件已更新');
            loadDownloads();
        } catch (err) {
            toast(err.message);
        } finally {
            input.value = '';
            button.disabled = false;
            button.textContent = '更新文件';
        }
    }

    function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(() => toast('链接已复制'));
        } else {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            toast('链接已复制');
        }
    }

    function esc(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    function absoluteUrl(path) {
        return new URL(path, window.location.origin).toString();
    }

    function formatBytes(bytes) {
        if (bytes == null) return '-';
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = Number(bytes);
        let index = 0;
        while (size >= 1024 && index < units.length - 1) {
            size /= 1024;
            index += 1;
        }
        return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
    }

    function formatTime(timestamp) {
        if (!timestamp) return '';
        return new Date(timestamp * 1000).toLocaleString();
    }

    // Init
    loadRegionOptions().then(loadConfigs);
})();
