"""Page HTML inline pour le HUD Jarvis.

Volontairement monolithique (un seul gros template HTML+CSS+JS) pour pas
avoir à servir d'assets séparés. Palette Iron-Man (cyan/violet/lime) reprise
de `recherche/_assets/theme.css`.
"""

from __future__ import annotations

HUD_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jarvis · HUD</title>
  <style>
    :root {
      --bg-0: #0a0c14;
      --bg-1: #11141d;
      --bg-card: rgba(20, 24, 33, 0.65);
      --text-0: #eef2ff;
      --text-1: #c9d1e7;
      --text-2: #8896b3;
      --text-3: #5a6580;
      --accent-cyan: #00ddff;
      --accent-violet: #7c5cff;
      --accent-lime: #84cc16;
      --border: rgba(124, 92, 255, 0.25);
      --radius: 14px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { background: var(--bg-0); color: var(--text-1); font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; }
    body { overflow: hidden; }
    .orb { position: fixed; border-radius: 50%; filter: blur(80px); opacity: 0.4; pointer-events: none; z-index: 0; }
    .orb-1 { width: 400px; height: 400px; background: var(--accent-cyan); top: -100px; left: -100px; animation: float 14s ease-in-out infinite; }
    .orb-2 { width: 500px; height: 500px; background: var(--accent-violet); bottom: -150px; right: -150px; animation: float 18s ease-in-out infinite reverse; }
    .orb-3 { width: 300px; height: 300px; background: var(--accent-lime); top: 50%; left: 50%; transform: translate(-50%, -50%); opacity: 0.15; }
    @keyframes float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(30px); } }

    header { position: relative; z-index: 10; padding: 18px 24px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 16px; background: rgba(10,12,20,0.7); backdrop-filter: blur(20px); }
    header h1 { font-size: 22px; font-weight: 800; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .pulse { width: 10px; height: 10px; border-radius: 50%; background: var(--accent-lime); box-shadow: 0 0 12px var(--accent-lime); animation: pulse 2s ease-in-out infinite; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
    .header-meta { margin-left: auto; font-size: 12px; color: var(--text-2); }

    main { position: relative; z-index: 1; display: grid; grid-template-columns: 280px 1fr 320px; gap: 18px; padding: 18px; height: calc(100vh - 68px); }
    @media (max-width: 1024px) { main { grid-template-columns: 1fr; height: auto; } body { overflow: auto; } }

    .panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; backdrop-filter: blur(20px); display: flex; flex-direction: column; min-height: 0; }
    .panel h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--text-3); margin-bottom: 14px; }

    /* Left panel : system */
    .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(124,92,255,0.08); font-size: 13px; }
    .stat-row:last-child { border-bottom: 0; }
    .stat-label { color: var(--text-2); }
    .stat-value { color: var(--text-0); font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
    .stat-value.up { color: var(--accent-lime); }
    .stat-value.down { color: #ef4444; }
    .bar { width: 100%; height: 4px; background: rgba(124,92,255,0.15); border-radius: 2px; overflow: hidden; margin-top: 4px; }
    .bar > div { height: 100%; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet)); transition: width 0.3s; }
    .section-title { font-size: 11px; text-transform: uppercase; color: var(--text-3); margin: 14px 0 6px; letter-spacing: 1px; }

    /* Center panel : chat */
    #chat { flex: 1; overflow-y: auto; padding-right: 8px; display: flex; flex-direction: column; gap: 12px; }
    .msg { padding: 12px 16px; border-radius: 12px; max-width: 85%; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
    .msg.user { background: rgba(0,221,255,0.12); border: 1px solid rgba(0,221,255,0.25); align-self: flex-end; }
    .msg.assistant { background: rgba(124,92,255,0.12); border: 1px solid rgba(124,92,255,0.25); align-self: flex-start; }
    .msg.tool { background: rgba(132,204,22,0.08); border: 1px solid rgba(132,204,22,0.2); font-family: 'JetBrains Mono', monospace; font-size: 12px; align-self: flex-start; }
    .msg.error { background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3); color: #fca5a5; align-self: stretch; max-width: 100%; }
    .input-row { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border); }
    #input { flex: 1; background: rgba(10,12,20,0.8); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; color: var(--text-0); font-family: inherit; font-size: 14px; outline: none; transition: border-color 0.2s; }
    #input:focus { border-color: var(--accent-cyan); }
    button { background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet)); border: 0; color: white; padding: 12px 18px; border-radius: 10px; font-weight: 700; font-family: inherit; cursor: pointer; transition: opacity 0.2s; }
    button:hover { opacity: 0.9; }
    button:disabled { opacity: 0.4; cursor: not-allowed; }

    /* Right panel : audit */
    #audit { flex: 1; overflow-y: auto; font-size: 12px; }
    .audit-entry { padding: 8px 10px; border-radius: 8px; margin-bottom: 6px; background: rgba(10,12,20,0.5); border: 1px solid rgba(124,92,255,0.1); }
    .audit-meta { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-3); margin-bottom: 4px; }
    .audit-action { color: var(--text-0); font-weight: 600; font-size: 12px; }
    .audit-status { padding: 2px 8px; border-radius: 999px; font-size: 9px; font-weight: 700; text-transform: uppercase; }
    .audit-status.ok { background: rgba(132,204,22,0.15); color: var(--accent-lime); }
    .audit-status.refused { background: rgba(239,68,68,0.15); color: #ef4444; }
    .audit-status.error { background: rgba(245,158,11,0.15); color: #f59e0b; }

    .empty { color: var(--text-3); font-style: italic; font-size: 12px; text-align: center; padding: 20px; }
  </style>
</head>
<body>
  <div class="orb orb-1"></div>
  <div class="orb orb-2"></div>
  <div class="orb orb-3"></div>

  <header>
    <span class="pulse"></span>
    <h1>JARVIS · HUD</h1>
    <div class="header-meta" id="header-meta">connexion…</div>
  </header>

  <main>
    <!-- LEFT : système -->
    <section class="panel">
      <h2>État système</h2>
      <div id="sys-cpu"><div class="stat-row"><span class="stat-label">CPU</span><span class="stat-value" data-key="cpu">—</span></div><div class="bar"><div data-bar="cpu" style="width:0%"></div></div></div>
      <div id="sys-ram"><div class="stat-row"><span class="stat-label">RAM</span><span class="stat-value" data-key="ram">—</span></div><div class="bar"><div data-bar="ram" style="width:0%"></div></div></div>
      <div id="sys-gpu"><div class="stat-row"><span class="stat-label">GPU</span><span class="stat-value" data-key="gpu">—</span></div><div class="bar"><div data-bar="gpu" style="width:0%"></div></div></div>

      <div class="section-title">Services</div>
      <div class="stat-row"><span class="stat-label">Ollama</span><span class="stat-value" id="ollama-status">—</span></div>
      <div id="services-extra"></div>
    </section>

    <!-- CENTER : chat -->
    <section class="panel">
      <h2>Conversation</h2>
      <div id="chat"><div class="empty">Tape un message pour démarrer.</div></div>
      <div class="input-row">
        <input id="input" placeholder="Demande à Jarvis…" autocomplete="off">
        <button id="send">Envoyer</button>
      </div>
    </section>

    <!-- RIGHT : audit -->
    <section class="panel">
      <h2>Audit log <small style="color:var(--text-3);font-weight:400;text-transform:none;letter-spacing:0">(50 derniers)</small></h2>
      <div id="audit"><div class="empty">Aucun event.</div></div>
    </section>
  </main>

  <script>
    const STATUS_INTERVAL = 2000;
    const AUDIT_INTERVAL = 5000;

    async function fetchJSON(url) {
      try { const r = await fetch(url); return await r.json(); } catch(e) { return null; }
    }

    function setText(sel, txt) { const el = document.querySelector(sel); if (el) el.textContent = txt; }
    function setBar(key, percent) { const b = document.querySelector(`[data-bar='${key}']`); if (b) b.style.width = Math.max(0, Math.min(100, percent)) + '%'; }

    function renderStatus(s) {
      if (!s) return;
      // CPU
      if (s.cpu && s.cpu.percent !== undefined) {
        setText("[data-key='cpu']", `${s.cpu.percent.toFixed(0)}% (${s.cpu.count_physical}c/${s.cpu.count_logical}t)`);
        setBar('cpu', s.cpu.percent);
      } else { setText("[data-key='cpu']", "n/a"); }
      // RAM
      if (s.memory && s.memory.percent !== undefined) {
        setText("[data-key='ram']", `${s.memory.used_gb}/${s.memory.total_gb} Go (${s.memory.percent.toFixed(0)}%)`);
        setBar('ram', s.memory.percent);
      } else { setText("[data-key='ram']", "n/a"); }
      // GPU
      if (s.gpu && s.gpu.gpus && s.gpu.gpus.length) {
        const g = s.gpu.gpus[0];
        setText("[data-key='gpu']", `${g.name.split(' ').slice(-2).join(' ')} · ${g.vram_used_mb}/${g.vram_total_mb} Mo · ${g.temp_c}°C`);
        setBar('gpu', (g.vram_used_mb / Math.max(1, g.vram_total_mb)) * 100);
      } else { setText("[data-key='gpu']", "n/a"); }
      // Ollama
      const o = document.getElementById('ollama-status');
      if (s.ollama && s.ollama.status === 'running') { o.textContent = 'up'; o.className = 'stat-value up'; }
      else { o.textContent = 'down'; o.className = 'stat-value down'; }
      // Extra services
      const extra = document.getElementById('services-extra');
      extra.innerHTML = '';
      for (const [name, state] of Object.entries(s.services || {})) {
        const row = document.createElement('div');
        row.className = 'stat-row';
        row.innerHTML = `<span class='stat-label'>${name}</span><span class='stat-value ${state === 'up' ? 'up' : 'down'}'>${state}</span>`;
        extra.appendChild(row);
      }
      // Header meta
      const date = new Date(s.timestamp * 1000);
      document.getElementById('header-meta').textContent = `mis à jour ${date.toLocaleTimeString()}`;
    }

    function renderAudit(data) {
      const root = document.getElementById('audit');
      if (!data || !data.events || data.events.length === 0) {
        root.innerHTML = "<div class='empty'>Aucun event.</div>"; return;
      }
      root.innerHTML = '';
      for (const ev of data.events) {
        const div = document.createElement('div');
        div.className = 'audit-entry';
        const dt = (ev.timestamp || '').slice(11, 19) || '—';
        div.innerHTML = `
          <div class='audit-meta'><span>${dt}</span><span class='audit-status ${ev.status}'>${ev.status}</span></div>
          <div class='audit-action'>${ev.action}</div>
        `;
        root.appendChild(div);
      }
    }

    async function pollStatus() {
      const s = await fetchJSON('/api/status');
      renderStatus(s);
    }
    async function pollAudit() {
      const a = await fetchJSON('/api/audit?limit=50');
      renderAudit(a);
    }

    setInterval(pollStatus, STATUS_INTERVAL); pollStatus();
    setInterval(pollAudit, AUDIT_INTERVAL); pollAudit();

    // Chat WebSocket
    const proto = (location.protocol === 'https:') ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
    const chat = document.getElementById('chat');
    const input = document.getElementById('input');
    const sendBtn = document.getElementById('send');

    function appendMsg(type, text) {
      // Vider le placeholder vide la 1ère fois
      const empty = chat.querySelector('.empty');
      if (empty) empty.remove();
      const div = document.createElement('div');
      div.className = 'msg ' + type;
      div.textContent = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        appendMsg(msg.type || 'assistant', msg.text || '');
      } catch (e) { appendMsg('error', 'message non-JSON'); }
      sendBtn.disabled = false;
    };
    ws.onclose = () => appendMsg('error', 'WebSocket fermé');
    ws.onerror = () => appendMsg('error', 'WebSocket erreur');

    function send() {
      const text = input.value.trim();
      if (!text || ws.readyState !== 1) return;
      sendBtn.disabled = true;
      ws.send(JSON.stringify({text}));
      input.value = '';
    }
    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  </script>
</body>
</html>"""
