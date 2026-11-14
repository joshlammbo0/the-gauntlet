/* The Gauntlet — single-page app. No build step. */
(() => {
'use strict';
const $ = (sel, el=document) => el.querySelector(sel);
const $$ = (sel, el=document) => Array.from(el.querySelectorAll(sel));
const main = $('#main');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtPct = x => x == null ? '—' : Math.round(x*100) + '';
const chip = s => s == null ? '<span class="score-chip">—</span>' : `<span class="score-chip ${s>=0.75?'good':s>=0.5?'warn':'bad'}">${Math.round(s*100)}</span>`;
const fmtTime = s => { s = Math.max(0, Math.round(s)); return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`; };
let HEALTH = null, SETTINGS = {};
const LS = { get(k, d){ try { const v = localStorage.getItem('gauntlet.'+k); return v==null?d:JSON.parse(v);} catch(e){ return d; } }, set(k,v){ try { localStorage.setItem('gauntlet.'+k, JSON.stringify(v)); } catch(e){} } };

async function api(path, opts={}) {
  const r = await fetch('/api'+path, Object.assign({headers: {'Content-Type':'application/json'}}, opts, opts.body && typeof opts.body !== 'string' && !(opts.body instanceof FormData) ? {body: JSON.stringify(opts.body)} : {}));
  if (opts.body instanceof FormData) { /* let browser set content-type */ }
  if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch(e){} throw new Error(msg); }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r;
}
async function apiForm(path, fd) { const r = await fetch('/api'+path, {method:'POST', body: fd}); if (!r.ok) { let m=r.statusText; try{ m=(await r.json()).error||(await r.json()).detail||m;}catch(e){} throw new Error(m);} return r.json(); }

let toastTimer;
function toast(msg, bad=false) { const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (bad?' bad':''); clearTimeout(toastTimer); toastTimer = setTimeout(()=>t.classList.add('hidden'), 4200); }

/* ------------------------------------------------------------------ router */
const routes = {};
function route(name, fn) { routes[name] = fn; }
function navigate(hash) { location.hash = hash; }
async function render() {
  const hash = location.hash || '#/home';
  const parts = hash.slice(2).split('/');
  const name = parts[0] || 'home';
  const navName = name === 'home' ? 'today' : (name === 'skills' || name === 'history' ? 'progress' : (name === 'bank' || name === 'resume' || name === 'teach' ? 'library' : name));
  $$('nav a.item').forEach(a => a.classList.toggle('active', a.dataset.route === navName || a.dataset.route === name));
  const fn = routes[name] || routes.home;
  main.innerHTML = '<p class="muted">Loading…</p>';
  try { await fn(parts.slice(1)); } catch (e) { main.innerHTML = `<div class="card"><h4>Error</h4><p>${esc(e.message)}</p></div>`; console.error(e); }
}
window.addEventListener('hashchange', render);

async function loadHealth() {
  try { HEALTH = await api('/health'); SETTINGS = HEALTH.settings || {}; } catch (e) { HEALTH = null; }
  const ns = $('#navstatus');
  if (!HEALTH) { ns.innerHTML = '<span class="dot bad"></span>server unreachable'; return; }
  const llm = HEALTH.llm.active;
  const w = HEALTH.whisper;
  ns.innerHTML = `<div><span class="dot ${llm==='offline'?'warn':'ok'}"></span><b>engine</b> ${llm==='offline'?'deterministic (no model)':llm}</div>
    <div><span class="dot ${w.loaded?'ok':w.loading?'warn':(w.error?'bad':'warn')}"></span><b>whisper</b> ${w.loaded?w.model:(w.loading?'loading…':(w.error?'error':'idle'))}</div>
    <div><span class="dot ${HEALTH.tts.available?'ok':'warn'}"></span><b>voice</b> ${voiceMode()}</div>
    <div><span class="dot ${HEALTH.bankvault?'ok':'warn'}"></span><b>bankvault</b> ${HEALTH.bankvault?'linked':'missing'}</div>
    <div class="dim">${HEALTH.questions} questions · v${HEALTH.version}</div>`;
}
function voiceMode(){ return LS.get('voiceMode', 'browser'); }

/* ------------------------------------------------------------------ home */
route('home', async () => {
  const [modes, skills, sessions] = await Promise.all([api('/modes'), api('/skills'), api('/sessions?limit=5')]);
  const long = skills.longitudinal;
  const active = sessions.find(s => s.status === 'active');
  const assessed = skills.skills.filter(s => s.state === 'assessed');
  main.innerHTML = `
    <h1>The Gauntlet</h1>
    <p class="sub">Pick a mode. Every session feeds the skill map; the debrief tells you exactly what to fix.</p>
    ${active ? `<div class="card" style="border-color:var(--accent);margin-bottom:16px"><div class="row"><div><h4>Interview in progress: ${esc(active.mode_name)}</h4><p>Started ${new Date(active.created*1000).toLocaleString()}. Your state is saved after every turn.</p></div><span class="spacer"></span><button class="primary" onclick="location.hash='#/session/${active.id}'">Resume</button><button class="ghost" id="endActive">End it</button></div></div>` : ''}
    <div class="grid cols4" style="margin-bottom:18px">
      <div class="card"><h3>Sessions</h3><div class="scorebox"><div class="big">${long.sessions_completed}</div>completed · ${long.practice_hours}h practiced</div></div>
      <div class="card"><h3>Answers scored</h3><div class="scorebox"><div class="big">${long.answers_evaluated}</div>${long.data_sufficiency === 'insufficient' ? 'not enough data for trends yet' : 'trend available'}</div></div>
      <div class="card"><h3>Skills assessed</h3><div class="scorebox"><div class="big">${assessed.length}<span class="muted" style="font-size:14px">/${skills.skills.length}</span></div>${skills.due.length} due for review</div></div>
      <div class="card"><h3>Weakest right now</h3>${skills.weaknesses.slice(0,3).map(w=>`<div class="small">${esc(w.name)} <span class="mono muted">${w.mastery}/5</span></div>`).join('') || '<p>Not yet assessed. Start with a Superday or Death Match.</p>'}</div>
    </div>
    <h2>Modes</h2>
    <div class="grid cols2">${modes.map(m => `<div class="card click" data-mode="${m.key}"><h4>${esc(m.name)}</h4><p>${esc(m.desc)}</p></div>`).join('')}</div>
    ${skills.remediation.length ? `<h2>Recommended drills</h2><div class="grid cols2">${skills.remediation.slice(0,4).map(r => `<div class="card"><h4>${esc(r.name)} <span class="pill warn">${r.mastery}/5</span></h4><p>${esc(r.why)}</p><div style="margin-top:8px"><button class="small" data-drill="${r.skill}">Run 4-question drill</button></div></div>`).join('')}</div>` : ''}
    <div id="setup"></div>`;
  $$('[data-mode]').forEach(el => el.onclick = () => showSetup(el.dataset.mode, modes.find(m=>m.key===el.dataset.mode)));
  $$('[data-drill]').forEach(b => b.onclick = () => startSession('explain', {skill: b.dataset.drill, duration_min: 15, persona: 'associate'}));
  const ea = $('#endActive'); if (ea) ea.onclick = async () => { await api(`/sessions/${active.id}/end`, {method:'POST'}); render(); };
});

async function showSetup(mode, meta) {
  let el = $('#setup'); if (!el) { el = document.createElement('div'); el.id = 'setup'; main.appendChild(el); }
  const [personas, banks, profile] = await Promise.all([api('/personas'), api('/banks'), api('/profile')]);
  const areas = ['accounting','valuation','dcf','ma','lbo','fig','healthcare','energy','commercial'];
  const skillsForExplain = (await api('/skills')).skills.filter(s => !s.skill.startsWith('behavioral') && !s.skill.startsWith('resume') && !s.skill.startsWith('deal'));
  const needsBank = mode === 'bank_specific' || mode === 'superday' || mode === 'hot_seat';
  el.innerHTML = `<div class="card setup" style="margin-top:22px;border-color:var(--accent)">
    <h2 style="margin-top:0">${esc(meta.name)}</h2><p class="muted small">${esc(meta.desc)}</p>
    <div class="grid cols3">
      ${needsBank ? `<div><label>Bank ${mode==='bank_specific'?'':'(optional)'}</label><select id="s_bank"><option value="">— none —</option>${banks.map(b=>`<option value="${b.slug}">${esc(b.name)}${b.has_research?'':' (no research)'}</option>`).join('')}</select>
        <label>Group / sector</label><select id="s_sector"><option value="">Generalist</option>${['healthcare','energy','power','fig','tmt','industrials','m&a','consumer','sports'].map(s=>`<option value="${s}">${s}</option>`).join('')}</select><div class="hint" id="groupHint"></div></div>` : ''}
      ${mode !== 'hot_seat' && mode !== 'rapid_fire' && mode !== 'tmay' ? `<div><label>Interviewer</label><select id="s_persona">${personas.filter(p=>p.key!=='hot_seat').map(p=>`<option value="${p.key}" ${p.key==='vp'?'selected':''}>${esc(p.name)}</option>`).join('')}</select><div class="hint" id="personaHint"></div></div>` : ''}
      <div><label>Duration</label><select id="s_dur">${[10,15,20,30,45,60].map(d=>`<option value="${d}" ${d===(mode==='rapid_fire'||mode==='tmay'?10:30)?'selected':''}>${d} min</option>`).join('')}</select>
        <label>Difficulty</label><select id="s_diff"><option value="easy">Easy</option><option value="medium" selected>Medium</option><option value="hard">Hard</option><option value="brutal">Brutal</option></select></div>
      ${['superday','bank_specific','hot_seat'].includes(mode) ? `<div><label>Technical vs behavioral</label><input type="range" id="s_tw" min="0" max="100" value="60" oninput="document.getElementById('twv').textContent=this.value+'% technical'"><div class="hint" id="twv">60% technical</div>
        <label><input type="checkbox" id="s_resume" checked style="width:auto;margin-right:6px">Resume-specific questions</label><label><input type="checkbox" id="s_deal" style="width:auto;margin-right:6px">Current transaction discussion</label></div>` : ''}
      ${mode === 'death_match' || mode === 'rapid_fire' ? `<div style="grid-column:span 2"><label>Categories (none = comprehensive)</label><div class="row">${areas.map(a=>`<label style="text-transform:none;letter-spacing:0;margin:0"><input type="checkbox" class="s_cat" value="${a}" style="width:auto;margin-right:4px">${a}</label>`).join('')}</div></div>` : ''}
      ${mode === 'resume_defense' ? `<div><label>Experience</label><select id="s_exp"><option value="">All bullets</option>${profile.experiences.map(e=>`<option value="${e.id}">${esc(e.org)}</option>`).join('')}</select></div>` : ''}
      ${mode === 'deal_defense' ? `<div><label>Focus</label><select id="s_deal_focus"><option value="">Any pitch or deal</option><option value="uthr">United Therapeutics (BUY)</option><option value="insulet">Insulet (BUY)</option><option value="saro">StandardAero (BUY)</option><option value="viasat">Viasat (SELL)</option><option value="seahawks">Seahawks franchise</option><option value="devon">Devon / Coterra (cover-letter deal)</option><option value="deal">A deal in the news</option></select></div>` : ''}
      ${mode === 'explain' ? `<div><label>Skill to drill</label><select id="s_skill">${skillsForExplain.map(s=>`<option value="${s.skill}">${esc(s.name)}${s.mastery!=null?' ('+s.mastery+'/5)':''}</option>`).join('')}</select></div>` : ''}
      ${mode === 'tmay' ? `<div><label>Variant</label><select id="s_tmay"><option value="standard">Cycle 90 → 60 → 120 → 180s, then interrupted</option><option value="interrupted">Interrupted from the start</option><option value="led">Interviewer-led</option></select></div>` : ''}
      <div><label>Max questions (optional)</label><input id="s_max" type="number" min="1" max="40" placeholder="until time runs out">
        <label><input type="checkbox" id="s_health" style="width:auto;margin-right:6px" ${SETTINGS.include_health_story?'checked':''}>Allow the T1D story (sensitive)</label></div>
    </div>
    <div class="row" style="margin-top:18px"><button class="primary" id="begin">Begin interview</button><span class="muted small">Voice: ${voiceMode()} · Engine: ${HEALTH?.llm?.active || 'offline'}</span></div>
  </div>`;
  el.scrollIntoView({behavior:'smooth'});
  const pSel = $('#s_persona'); if (pSel) { const upd = () => { const p = personas.find(x=>x.key===pSel.value); $('#personaHint').textContent = p ? p.style : ''; }; pSel.onchange = upd; upd(); }
  const bSel = $('#s_bank'); if (bSel) { bSel.onchange = async () => { const h = $('#groupHint'); h.textContent=''; if (!bSel.value) return; try { const b = await api(`/banks/${bSel.value}`); h.textContent = `${b.groups.length} groups researched: ${b.groups.slice(0,6).map(g=>g.name).join(', ')}${b.groups.length>6?'…':''}`; } catch(e) { h.textContent = 'No BankVault research; firm questions stay generic.'; } }; }
  $('#begin').onclick = () => {
    const cfg = {duration_min: +$('#s_dur').value, difficulty: $('#s_diff').value, include_health_story: $('#s_health').checked};
    if ($('#s_max').value) cfg.max_questions = +$('#s_max').value;
    if ($('#s_bank')) { cfg.bank = $('#s_bank').value || null; cfg.sector = $('#s_sector').value || null; }
    if ($('#s_persona')) cfg.persona = $('#s_persona').value;
    if ($('#s_tw')) { cfg.technical_weight = +$('#s_tw').value/100; cfg.resume_questions = $('#s_resume').checked; cfg.deal_discussion = $('#s_deal').checked; }
    const cats = $$('.s_cat:checked').map(c=>c.value); if (cats.length) cfg.categories = cats;
    if ($('#s_exp')) cfg.experience_id = $('#s_exp').value || null;
    if ($('#s_deal_focus')) cfg.deal_focus = $('#s_deal_focus').value || null;
    if ($('#s_skill')) cfg.skill = $('#s_skill').value;
    if ($('#s_tmay')) cfg.tmay_style = $('#s_tmay').value;
    if (mode === 'bank_specific' && !cfg.bank) { toast('Pick a bank for a bank-specific interview', true); return; }
    startSession(mode, cfg);
  };
}

async function startSession(mode, config) {
  try {
    const res = await api('/sessions', {method:'POST', body:{mode, config}});
    LS.set('activeSession', res.session.id);
    navigate('#/session/' + res.session.id);
  } catch (e) { toast('Could not start: ' + e.message, true); }
}

/* ------------------------------------------------------------------ interview room */
const Room = { sid:null, session:null, turns:[], timer:null, rec:null, speaking:false, lastQuestionText:'', recStart:0, mediaStream:null, chunks:[], audioCtx:null, analyser:null, silenceTimer:null, levelRaf:null, sr:null, interim:'', finalSR:'', pauses:[], lastVoiceAt:0 };

route('session', async ([sid]) => {
  const data = await api(`/sessions/${sid}`);
  Room.sid = sid; Room.session = data.session; Room.turns = data.turns;
  if (Room.session.ended) { navigate('#/debrief/' + sid); return; }
  LS.set('activeSession', sid);
  renderRoom();
  const last = [...Room.turns].reverse().find(t => t.role === 'interviewer');
  if (last) { Room.lastQuestionText = last.text; if (!Room.session.paused) speak(last.text); }
  startTimer();
});

function renderRoom() {
  const s = Room.session;
  const lastQ = [...Room.turns].reverse().find(t => t.role === 'interviewer');
  main.innerHTML = `
  <div class="row" style="margin-bottom:12px"><h1 style="font-size:20px;margin:0">${esc(s.mode_name)}</h1>
    ${s.deathmatch ? `<span class="pill bad" id="hud-lives">${hearts(s.deathmatch.lives)}</span><span class="pill acc" id="hud-score">${s.deathmatch.score} pts · streak ${s.deathmatch.streak}</span>` : ''}
    ${s.career ? `<span class="pill acc">${esc(s.career.bank)} · ${esc(s.career.stage_key.replace('_',' '))}${s.career.boss?' · boss':''}</span>` : ''}
    ${s.daily ? `<span class="pill info">Daily Draft ${esc(s.daily.date)}</span>` : ''}
    ${s.config.bank ? `<span class="pill acc">${esc(s.config.bank)}${s.config.sector?' · '+esc(s.config.sector):''}</span>` : ''}
    <span class="pill">${esc(s.config.difficulty||'medium')}</span><span class="pill">${esc(s.persona.name)}</span>
    <span class="spacer"></span><span class="timer" id="timer"></span></div>
  <div class="room">
    <div class="stage">
      <div class="interviewer"><div class="avatar" id="avatar">${esc((s.persona.title||'I')[0])}</div><div class="who"><b>${esc(s.persona.name)}</b><span>${esc(s.persona.title)}${s.bank_context_available ? ' · firm research loaded' : ''}</span></div>
        <span class="spacer"></span><label style="margin:0;text-transform:none;letter-spacing:0;display:flex;gap:6px;align-items:center" title="Hands-free: the mic opens when the interviewer finishes speaking, stops on silence, and submits automatically"><input type="checkbox" id="handsfree" style="width:auto" ${LS.get('handsFree', true)?'checked':''}>Hands-free</label><button class="ghost small" id="replay" title="Replay the question">↻ Replay</button></div>
      <div class="question ${lastQ && lastQ.kind==='followup' ? 'followup':''}" id="question">${esc(lastQ ? lastQ.text : '…')}</div>
      <div class="row"><div class="pill ${lastQ&&lastQ.kind==='followup'?'warn':'info'}" id="qkind">${lastQ ? (lastQ.kind==='followup' ? 'follow-up' + (s.followup_depth?` · depth ${s.followup_depth}`:'') : lastQ.kind) : ''}</div><span class="pill ${s.hide_scores?'warn':'good'}">${s.hide_scores?'simulation · scores hidden':'learning · live feedback'}</span><span class="spacer"></span><span class="room-status" id="roomstatus">Ready</span></div>
      <div class="transcript" id="transcript"><span class="dim">Your answer will appear here. Speak, or type below.</span></div>
      <textarea id="typed" placeholder="Type your answer here if you'd rather not speak (or to correct the transcript before submitting)…" style="margin-top:10px"></textarea>
      <div class="ctrls">
        <div class="mic" id="mic" title="Start / stop recording" role="button" tabindex="0" aria-label="Start or stop recording"><svg viewBox="0 0 24 24"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11z"/></svg></div>
        <div><div class="recstatus" id="recstatus">Ready</div><div class="level"><i id="level"></i></div></div>
        <button class="primary" id="submit">Submit answer</button>
        <button id="retry" class="ghost">Discard</button>
        <span class="spacer"></span>
        <button id="pause">${s.paused ? 'Resume' : 'Pause'}</button>
        <button id="skip">Skip</button>
        <button id="endiv" class="danger">End interview</button>
      </div>
    </div>
    <div class="side">
      ${s.hide_scores ? '' : `<div class="card" id="livescore"><h3>Live evaluation</h3><div id="livebody" class="small muted">Answer a question to see the rubric result.</div></div>`}
      <details class="card" ${s.hide_scores ? '' : ''}><summary><h3 style="display:inline">Transcript</h3></summary><div class="log" id="log"></div></details>
      <details class="card advanced"><summary>Controls, shortcuts and status</summary><div class="small muted" style="margin-top:8px"><div><b>Hands-free:</b> the mic opens when the interviewer stops; it closes after ${(SETTINGS.silence_seconds||2.5)}s of silence and submits. Toggle it next to the interviewer.</div><div style="margin-top:4px"><b>Keys:</b> <kbd>Space</kbd> start/stop mic · <kbd>Enter</kbd> submit typed answer (Shift+Enter for a newline) · <kbd>R</kbd> replay · <kbd>P</kbd> pause · <kbd>Esc</kbd> interrupt the interviewer.</div><div style="margin-top:4px"><b>Mic trouble?</b> Type below; the Discard button clears a bad take. Edit the transcript before submitting if a term was misheard.</div><div style="margin-top:6px">Engine: ${s.llm_provider} · Voice: ${voiceMode()}${s.hide_scores?' · scores hidden until the debrief':''}</div></div></details>
    </div>
  </div>`;
  renderLog();
  $('#mic').onclick = toggleRecord;
  $('#mic').onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); toggleRecord(); } };
  $('#submit').onclick = submitAnswer;
  $('#retry').onclick = () => { stopRecording(true); setTranscript(''); $('#typed').value=''; };
  $('#replay').onclick = () => speak(Room.lastQuestionText);
  $('#handsfree').onchange = (e) => { LS.set('handsFree', e.target.checked); toast(e.target.checked ? 'Hands-free on: speak after the question, pause to finish.' : 'Hands-free off: click the mic to answer.'); };
  $('#avatar').onclick = () => { if (Room.speaking) { if (window.speechSynthesis) speechSynthesis.cancel(); if (currentAudio) currentAudio.pause(); Room.speaking = false; $('#avatar').classList.remove('speaking'); toast('Interrupted the interviewer.'); } };
  $('#pause').onclick = togglePause;
  $('#skip').onclick = async (e) => { if (!armConfirm(e.currentTarget, 'Confirm skip (counts as a miss)')) return; const r = await api(`/sessions/${Room.sid}/skip`, {method:'POST'}); handleInterviewer(r.interviewer_turns, r.state); };
  $('#endiv').onclick = async (e) => { if (!armConfirm(e.currentTarget, 'Click again to end')) return; const r = await api(`/sessions/${Room.sid}/end`, {method:'POST'}); handleInterviewer(r.interviewer_turns, r.state); };
  document.onkeydown = (e) => { if (!location.hash.startsWith('#/session/')) return; const typing = ['TEXTAREA','INPUT','SELECT'].includes(document.activeElement.tagName); if (e.key === 'Enter' && document.activeElement.id === 'typed' && !e.shiftKey) { e.preventDefault(); submitAnswer(); return; } if (typing) return; if (e.code === 'Space') { e.preventDefault(); toggleRecord(); } else if (e.key === 'r' || e.key === 'R') speak(Room.lastQuestionText); else if (e.key === 'p' || e.key === 'P') togglePause(); else if (e.key === 'Escape') $('#avatar')?.click(); };
}

function renderLog() {
  const log = $('#log'); if (!log) return;
  log.innerHTML = Room.turns.map(t => `<div class="t ${t.role==='interviewer'?'i':'c'}"><small>${t.role==='interviewer' ? (t.kind||'') : 'you' + (t.meta && t.meta.duration ? ' · '+Math.round(t.meta.duration)+'s' : '')}</small>${esc(t.text)}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}
function startTimer() {
  clearInterval(Room.timer);
  const tick = () => { const s = Room.session; if (!s) return; const el = $('#timer'); if (!el) return; const total = (s.duration_min||30)*60; const base = s.elapsed_sec || 0; const extra = s.paused ? 0 : (Date.now() - Room._syncAt)/1000; const el2 = base + extra; el.innerHTML = `<b>${fmtTime(el2)}</b> / ${fmtTime(total)}${s.paused ? ' · paused' : ''}${el2 > total ? ' · over time' : ''}`; };
  Room._syncAt = Date.now(); tick(); Room.timer = setInterval(tick, 1000);
}
async function togglePause() {
  const s = Room.session;
  const st = await api(`/sessions/${Room.sid}/${s.paused ? 'resume' : 'pause'}`, {method:'POST'});
  Room.session = st; Room._syncAt = Date.now(); $('#pause').textContent = st.paused ? 'Resume' : 'Pause'; startTimer();
  if (st.paused) { stopRecording(true); window.speechSynthesis && speechSynthesis.cancel(); }
}

/* ---------------- voice output */
let currentAudio = null;
async function speak(text) {
  if (!text) return;
  const mode = voiceMode();
  const avatar = $('#avatar');
  const setSpeaking = v => { Room.speaking = v; if (avatar) avatar.classList.toggle('speaking', v); if (v) setRecStatus('Interviewer speaking'); else if (!Room.rec) setRecStatus('Ready'); };
  if (mode === 'off') return;
  if (currentAudio) { try { currentAudio.pause(); } catch(e){} currentAudio = null; }
  if (window.speechSynthesis) speechSynthesis.cancel();
  if (mode === 'mac') {
    try {
      const r = await fetch('/api/tts', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text, voice: LS.get('macVoice', null), rate: LS.get('ttsRate', 175), persona: Room.session?.persona?.key})});
      if (!r.ok) throw new Error('tts');
      const blob = await r.blob(); const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url); setSpeaking(true);
      currentAudio.onended = () => { setSpeaking(false); URL.revokeObjectURL(url); maybeAutoRecord(); };
      currentAudio.onerror = () => setSpeaking(false);
      await currentAudio.play();
      return;
    } catch (e) { /* fall through to browser voice */ }
  }
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  const wanted = LS.get('browserVoice', null);
  const voices = speechSynthesis.getVoices();
  const v = voices.find(x => x.name === wanted) || voices.find(x => /en[-_]US/.test(x.lang) && /Samantha|Alex|Daniel|Google US|Aaron|Nicky/.test(x.name)) || voices.find(x => /en/.test(x.lang));
  if (v) u.voice = v;
  u.rate = LS.get('browserRate', 1.0); u.pitch = 1.0;
  u.onstart = () => setSpeaking(true); u.onend = () => { setSpeaking(false); maybeAutoRecord(); }; u.onerror = () => setSpeaking(false);
  speechSynthesis.speak(u);
}
function handsFree() { return LS.get('handsFree', true); }
function maybeAutoRecord() { if ((handsFree() || LS.get('autoRecord', false)) && Room.sid && !Room.rec && !Room.session?.paused && !Room.session?.ended && !Room.pending && location.hash.startsWith('#/session/')) setTimeout(() => { if (!Room.rec && !Room.speaking) toggleRecord(); }, 350); }
const MAX_ANSWER_SEC = { numeric: 90, technical: 150, behavioral: 150, resume: 150, followup: 120 };

/* ---------------- voice input */
async function toggleRecord() {
  if (Room.rec) { stopRecording(false); return; }
  if (Room.speaking) { if (window.speechSynthesis) speechSynthesis.cancel(); if (currentAudio) currentAudio.pause(); Room.speaking=false; $('#avatar')?.classList.remove('speaking'); }
  try {
    const constraints = {audio: {echoCancellation:true, noiseSuppression:true, deviceId: LS.get('micId', undefined) ? {exact: LS.get('micId')} : undefined}};
    Room.mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
  } catch (e) { toast('Microphone unavailable: ' + e.message + '. Type your answer instead.', true); return; }
  const mime = ['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(m => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || '';
  Room.chunks = []; Room.pauses = [];
  Room.rec = new MediaRecorder(Room.mediaStream, mime ? {mimeType: mime} : undefined);
  Room.rec.ondataavailable = e => { if (e.data.size) Room.chunks.push(e.data); };
  Room.rec.onstop = onRecordingStopped;
  Room.rec.start(250);
  Room.recStart = Date.now(); Room.lastVoiceAt = Date.now(); Room._silenceStart = null;
  $('#mic').classList.add('rec'); setRecStatus('Recording… 0:00');
  setTranscript('', true);
  startLevelMeter();
  startLiveSR();
  Room._recTick = setInterval(() => { if (Room.rec) setRecStatus('Recording… ' + fmtTime((Date.now()-Room.recStart)/1000)); }, 500);
}
function setRecStatus(s) { const el = $('#recstatus'); if (el) el.textContent = s; const rs = $('#roomstatus'); if (rs) { rs.textContent = s; rs.className = 'room-status ' + (/record/i.test(s) ? 'listening' : /transcrib|evaluat/i.test(s) ? 'transcribing' : /speak/i.test(s) ? 'speaking' : ''); } }
function setTranscript(text, interim=false) { const el = $('#transcript'); if (!el) return; if (!text && !interim) { el.innerHTML = '<span class="dim">Your answer will appear here. Speak, or type below.</span>'; return; } el.innerHTML = interim ? `<span class="interim">${esc(text || 'listening…')}</span>` : esc(text); }
function startLevelMeter() {
  try {
    Room.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src = Room.audioCtx.createMediaStreamSource(Room.mediaStream);
    Room.analyser = Room.audioCtx.createAnalyser(); Room.analyser.fftSize = 1024; src.connect(Room.analyser);
    const buf = new Uint8Array(Room.analyser.fftSize);
    const thresh = SETTINGS.silence_threshold || 0.012; const silenceSec = SETTINGS.silence_seconds || 2.5; const minSec = SETTINGS.min_answer_seconds || 4;
    const loop = () => {
      if (!Room.analyser) return;
      Room.analyser.getByteTimeDomainData(buf);
      let sum = 0; for (let i=0;i<buf.length;i++){ const v=(buf[i]-128)/128; sum+=v*v; }
      const rms = Math.sqrt(sum/buf.length);
      const lv = $('#level'); if (lv) lv.style.width = Math.min(100, rms*600) + '%';
      const now = Date.now();
      if (rms > thresh) { if (Room._silenceStart && (now - Room._silenceStart) > 1500) Room.pauses.push((now - Room._silenceStart)/1000); Room._silenceStart = null; Room.lastVoiceAt = now; }
      else if (!Room._silenceStart) Room._silenceStart = now;
      const elapsed = (now - Room.recStart)/1000;
      const lastQ = [...Room.turns].reverse().find(t => t.role === 'interviewer');
      const cap = MAX_ANSWER_SEC[(lastQ && lastQ.kind) || 'technical'] || 150;
      if (LS.get('interruptLong', true) && elapsed > cap) { Room._interrupted = true; setRecStatus('Interviewer cut in'); stopRecording(false); return; }
      if (LS.get('autoStop', true) && elapsed > minSec && (now - Room.lastVoiceAt)/1000 > silenceSec && Room.lastVoiceAt > Room.recStart + 800) { stopRecording(false); return; }
      Room.levelRaf = requestAnimationFrame(loop);
    };
    loop();
  } catch (e) { console.warn('level meter', e); }
}
function startLiveSR() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR || !LS.get('liveCaptions', true)) return;
  try {
    Room.sr = new SR(); Room.sr.continuous = true; Room.sr.interimResults = true; Room.sr.lang = 'en-US';
    Room.finalSR = ''; Room.interim = '';
    Room.sr.onresult = (ev) => { let interim=''; for (let i=ev.resultIndex;i<ev.results.length;i++){ const r=ev.results[i]; if (r.isFinal) Room.finalSR += r[0].transcript + ' '; else interim += r[0].transcript; } Room.interim = interim; setTranscript((Room.finalSR + interim).trim() || '', true); };
    Room.sr.onerror = () => {}; Room.sr.start();
  } catch (e) { Room.sr = null; }
}
function stopRecording(discard) {
  if (Room._recTick) clearInterval(Room._recTick);
  if (Room.levelRaf) cancelAnimationFrame(Room.levelRaf);
  Room.analyser = null; if (Room.audioCtx) { try { Room.audioCtx.close(); } catch(e){} Room.audioCtx = null; }
  if (Room.sr) { try { Room.sr.stop(); } catch(e){} Room.sr = null; }
  $('#mic')?.classList.remove('rec');
  if (Room.rec) { Room._discard = discard; try { Room.rec.stop(); } catch(e){} Room.rec = null; }
  if (Room.mediaStream) { Room.mediaStream.getTracks().forEach(t=>t.stop()); Room.mediaStream = null; }
  if (discard) { setRecStatus('Ready'); }
}
async function onRecordingStopped() {
  const duration = (Date.now() - Room.recStart)/1000;
  if (Room._discard) { Room.chunks = []; return; }
  const blob = new Blob(Room.chunks, {type: Room.chunks[0]?.type || 'audio/webm'});
  Room.chunks = [];
  if (blob.size < 2000) { setRecStatus('Too short'); setTranscript(''); return; }
  setRecStatus('Transcribing…'); $('#mic').classList.add('busy');
  const fd = new FormData(); fd.append('audio', blob, 'answer.webm'); fd.append('session_id', Room.sid); fd.append('keep', LS.get('keepAudio', false) ? '1' : '0');
  try {
    const r = await apiForm('/transcribe', fd);
    const text = r.text || '';
    Room.pending = {text, raw: r.raw, duration: r.duration || duration, pauses: (r.pauses||[]).concat(Room.pauses), transcript_id: r.transcript_id, audio_url: r.audio_url, input_mode:'voice', interrupted: !!Room._interrupted};
    Room._interrupted = false;
    setTranscript(text || '(nothing recognized)');
    $('#typed').value = text;
    setRecStatus(`Transcribed in ${r.seconds}s · ${Math.round(Room.pending.duration)}s answer`);
    if (!text) { if (handsFree()) { setRecStatus('Heard nothing. Listening again…'); maybeAutoRecord(); } return; }
    if ((LS.get('autoSubmit', false) || handsFree()) && text) submitAnswer();
  } catch (e) {
    const fallback = (Room.finalSR + ' ' + Room.interim).trim();
    if (fallback) { Room.pending = {text: fallback, raw: fallback, duration, pauses: Room.pauses, input_mode:'voice-browser'}; $('#typed').value = fallback; setTranscript(fallback); setRecStatus('Whisper failed; using browser captions'); }
    else { setRecStatus('Transcription failed'); toast('Transcription failed: ' + e.message + '. Type your answer.', true); }
  } finally { $('#mic')?.classList.remove('busy'); }
}
async function submitAnswer() {
  const typed = $('#typed').value.trim();
  if (Room.rec) stopRecording(false);
  const p = Room.pending || {};
  const text = typed || p.text || '';
  if (!text) { toast('Nothing to submit yet.', true); return; }
  const payload = {text, duration: p.duration || (typed ? Math.max(5, typed.split(/\s+/).length/150*60) : null), pauses: p.pauses || [], transcript_id: p.transcript_id || null, raw_transcript: p.raw || null, input_mode: p.text ? (typed !== p.text ? 'voice-corrected' : p.input_mode) : 'text', interrupted: !!p.interrupted};
  $('#submit').disabled = true; setRecStatus('Evaluating…');
  try {
    const r = await api(`/sessions/${Room.sid}/answer`, {method:'POST', body: payload});
    Room.pending = null; $('#typed').value = ''; setTranscript('');
    Room.turns.push({role:'candidate', text, kind:'answer', meta:{duration: payload.duration}});
    if (r.evaluation) showLiveEval(r.evaluation);
    handleInterviewer(r.interviewer_turns, r.state);
  } catch (e) { toast('Submit failed: ' + e.message, true); }
  finally { $('#submit').disabled = false; setRecStatus('Ready'); }
}
function hearts(n) { let out = ''; for (let i = 0; i < 3; i++) out += i < n ? '\u2665' : '\u2661'; return out; }
function handleInterviewer(turns, state) {
  Room.session = state; Room._syncAt = Date.now();
  if (state.deathmatch) { const l = $('#hud-lives'), sc = $('#hud-score'); if (l) l.textContent = hearts(state.deathmatch.lives); if (sc) sc.textContent = `${state.deathmatch.score} pts · streak ${state.deathmatch.streak}${state.deathmatch.boss_pending ? ' · BOSS next' : ''}`; }
  (turns||[]).forEach(t => Room.turns.push(t));
  renderLog();
  const last = (turns||[]).slice(-1)[0];
  if (state.ended) { toast('Interview over. Building your debrief…'); if (last) speak(last.text); setTimeout(()=>navigate('#/debrief/'+Room.sid), last ? 2500 : 300); return; }
  if (last) {
    Room.lastQuestionText = last.text;
    $('#question').textContent = last.text; $('#question').className = 'question' + (last.kind==='followup' ? ' followup' : '');
    const k = $('#qkind'); k.textContent = last.kind==='followup' ? 'follow-up' + (state.followup_depth ? ` · depth ${state.followup_depth}` : '') + (last.meta?.reason ? ' · ' + last.meta.reason.replace(/_/g,' ') : '') : last.kind; k.className = 'pill ' + (last.kind==='followup'?'warn':'info');
    speak(turns.map(t=>t.text).join(' '));
  }
  const pb = $('#pause'); if (pb) pb.textContent = state.paused ? 'Resume' : 'Pause';
}
function showLiveEval(ev) {
  const body = $('#livebody'); if (!body) return;
  const dims = ev.dimensions ? Object.entries(ev.dimensions).map(([k,v])=>`<div class="row small" style="gap:6px"><span style="width:95px" class="muted">${k}</span><div class="bar ${v>=0.75?'good':v>=0.5?'warn':'bad'}" style="flex:1"><i style="width:${Math.round(v*100)}%"></i></div></div>`).join('') : '';
  const comps = (ev.components||[]).map(c => `<div class="small">${c.present ? '<span style="color:var(--good)">✓</span>' : '<span style="color:var(--bad)">✗</span>'} ${esc(c.text)}</div>`).join('');
  const mis = (ev.misconceptions||[]).map(m => `<div class="small" style="color:var(--bad)">⚠ ${esc(m.explain)}</div>`).join('');
  body.innerHTML = `<div class="row"><span class="big" style="font-size:26px;font-weight:600">${chip(ev.score)}</span><span class="pill ${ev.verdict==='correct'||ev.verdict==='strong'?'good':ev.verdict==='partial'||ev.verdict==='adequate'?'warn':'bad'}">${esc(ev.verdict)}</span>${ev.speed?`<span class="pill">${ev.speed}</span>`:''}<span class="pill">${esc(ev.provider||'')}</span></div>
    ${ev.key_error || ev.key_weakness ? `<div class="small" style="margin:6px 0;color:var(--warn)">${esc(ev.key_error || ev.key_weakness)}</div>` : ''}
    ${dims}${comps}${mis}
    ${ev.delivery && ev.delivery.notes && ev.delivery.notes.length ? `<div class="small dim" style="margin-top:6px">${ev.delivery.notes.map(esc).join('<br>')}</div>` : ''}
    ${ev.unsupported_claims && ev.unsupported_claims.length ? `<div class="small" style="color:var(--bad);margin-top:6px">Fact check: ${esc(ev.unsupported_claims[0])}</div>` : ''}`;
}

/* ------------------------------------------------------------------ debrief */
route('debrief', async ([sid]) => {
  const d = await api(`/sessions/${sid}/debrief`);
  if (LS.get('activeSession') === sid) LS.set('activeSession', null);
  const o = d.overall;
  const qhtml = d.questions.map(q => `<div class="q-item">
      <div class="row"><span class="q">${esc(q.question)}</span><span class="spacer"></span>${q.skill?`<span class="pill">${esc(q.skill)}</span>`:''}${chip(q.score)}${q.appealed?'<span class="pill info">appealed</span>':''}</div>
      <div class="a">${esc(q.answer)}</div>
      <div class="row small muted">${q.duration?`${Math.round(q.duration)}s`:''}${q.delivery&&q.delivery.wpm?` · ${q.delivery.wpm} wpm`:''}${q.delivery&&q.delivery.filler_total?` · ${q.delivery.filler_total} fillers`:''}${q.answered_question===false?' · <span style="color:var(--bad)">did not answer the question</span>':''}</div>
      ${q.got_right.length?`<div class="small" style="color:var(--good);margin-top:6px">Got right</div><ul>${q.got_right.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
      ${q.got_wrong.length?`<div class="small" style="color:var(--bad)">Got wrong</div><ul>${q.got_wrong.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
      ${q.omitted.length?`<div class="small" style="color:var(--warn)">Omitted</div><ul>${q.omitted.slice(0,4).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
      ${q.unsupported_claims&&q.unsupported_claims.length?`<div class="small" style="color:var(--bad)">Fact check: ${q.unsupported_claims.map(esc).join('; ')}</div>`:''}
      ${q.dimensions?`<div class="row small" style="gap:12px;margin-top:4px">${Object.entries(q.dimensions).map(([k,v])=>`<span class="mono muted">${k} <b style="color:${v>=0.75?'var(--good)':v>=0.5?'var(--warn)':'var(--bad)'}">${Math.round(v*100)}</b></span>`).join('')}</div>`:''}
      ${q.stronger_answer?`<div class="fix"><b>Stronger answer</b> <span class="dim small">(educational example from the rubric; [brackets] are placeholders, not facts about you)</span><br>${esc(q.stronger_answer)}</div>`:''}
      ${q.coach_notes?`<div class="small dim" style="margin-top:6px"><b>Coach notes:</b> ${esc(q.coach_notes)}</div>`:''}
      ${q.citation?`<div class="small dim" style="margin-top:4px">Source: ${esc(q.citation.short)} · ${esc(q.citation.section||'')} · p.${q.citation.page} <span class="pill ${q.citation.verification==='verified'?'good':'warn'}">${q.citation.verification}</span></div>`:''}
      ${q.callback_of?`<span class="pill info">callback</span>`:''}${q.provisional?`<span class="pill warn" title="rule-based grade; deep grade pending">provisional</span>`:''}
      ${q.skill?`<div class="row" style="margin-top:8px"><button class="small ghost" data-teach="${q.skill}">Teach me why</button>${q.evaluation_id?`<button class="small ghost" data-reattempt="${q.evaluation_id}">Reattempt concept</button>`:''}</div>`:''}
      ${q.evaluation_id?`<details><summary class="small">Challenge this evaluation</summary><div class="small muted" style="margin:6px 0">If Whisper misheard you, paste the corrected transcript. If you think the grading missed something, say why; it is re-scored against the rubric (and reconsidered by the model when one is connected).</div><textarea id="corr_${q.evaluation_id}" placeholder="Corrected transcript (optional)">${esc(q.answer)}</textarea><input id="arg_${q.evaluation_id}" placeholder="Your argument (optional)" style="margin-top:6px"><div class="row" style="margin-top:6px"><button class="small" data-appeal="${q.evaluation_id}">Re-evaluate</button><span class="small muted" id="appeal_${q.evaluation_id}"></span></div></details>`:''}
    </div>`).join('');
  main.innerHTML = `
    <div class="row"><h1>Debrief</h1><span class="pill acc">${esc(d.mode)}</span>${d.config.bank?`<span class="pill">${esc(d.config.bank)}</span>`:''}<span class="spacer"></span><button class="primary" id="retest">Retry my weakest questions</button><button onclick="location.hash='#/skills'">Skill map</button></div>
    ${d.verdict ? `<div class="card" style="border-color:var(--accent);margin:14px 0"><div class="row"><h2 style="margin:0">30-second verdict</h2><span class="spacer"></span>${chip(d.verdict.score)}</div><p style="margin:8px 0 10px"><b>${esc(d.verdict.headline)}</b></p>
      <div class="grid cols2"><div><div class="small muted">What held up</div>${d.verdict.strengths.length?d.verdict.strengths.map(x=>`<div class="small">✓ ${esc(x.question)} <span class="dim">${Math.round(x.score*100)}</span></div>`).join(''):'<div class="small dim">No answer cleared 75 this session.</div>'}</div>
      <div><div class="small muted">Highest-leverage problems</div>${d.verdict.problems.length?d.verdict.problems.map(x=>`<div class="small">✗ ${esc(x.question)} <span class="dim">${Math.round(x.score*100)}</span>${x.key?`<div class="dim" style="margin-left:14px">${esc(x.key.slice(0,140))}</div>`:''}</div>`).join(''):'<div class="small dim">Nothing below 60.</div>'}</div></div>
      <div class="row" style="margin-top:12px">${d.verdict.next_actions.map((a,i)=>`<button class="${i===0?'primary':''} small" data-next="${a.key}">${esc(a.label)}</button>`).join('')}</div></div>` : ''}
    <div class="grid cols4" style="margin:14px 0">
      <div class="card"><h3>Overall</h3><div class="scorebox"><div class="big">${o.score!=null?Math.round(o.score*100):'—'}</div>${o.n_scored} answers scored</div></div>
      <div class="card"><h3>Technical</h3><div class="scorebox"><div class="big">${o.technical_avg!=null?Math.round(o.technical_avg*100):'—'}</div>${Object.entries(o.by_area).filter(([a])=>a!=='behavioral').map(([a,v])=>`${a} ${Math.round(v*100)}`).join(' · ')||'—'}</div></div>
      <div class="card"><h3>Behavioral</h3><div class="scorebox"><div class="big">${o.behavioral_avg!=null?Math.round(o.behavioral_avg*100):'—'}</div></div></div>
      <div class="card"><h3>Delivery</h3><div class="small">${d.delivery.avg_duration_sec?`avg ${d.delivery.avg_duration_sec}s`:''}${d.delivery.avg_wpm?` · ${d.delivery.avg_wpm} wpm`:''}${d.delivery.avg_words?` · ${d.delivery.avg_words} words`:''}<br>${d.delivery.total_fillers} fillers · ${d.delivery.total_hedges} hedges · ${d.delivery.too_long} too long<br><span class="dim">${d.delivery.basis}-based</span></div></div>
    </div>
    <div class="card" style="margin-bottom:16px"><b>${esc(o.readiness)}</b><div class="small dim" style="margin-top:4px">${esc(o.caveat)}</div>${d.pending_deep_grades?`<div class="small" style="color:var(--warn);margin-top:6px">${d.pending_deep_grades} answer(s) still carry a provisional (rule-based) grade; the model's deep grade is pending or unavailable. Reload to refresh.</div>`:''}</div>
    <div id="gamebanner"></div>
    ${d.callbacks && d.callbacks.length ? `<div class="card" style="margin-bottom:16px"><h3>Callbacks</h3>${d.callbacks.map(c=>`<div class="small">${c.success?'<span style="color:var(--good)">OK</span>':'<span style="color:var(--bad)">X</span>'} ${esc(c.skill)}: revisited later ${c.success?'and held up':'and still missed'} (${Math.round(c.score*100)})</div>`).join('')}</div>` : ''}
    ${d.contradictions.length?`<div class="card" style="border-color:var(--bad);margin-bottom:16px"><h3>Contradictions the interviewer noticed</h3>${d.contradictions.map(c=>`<div class="small">${esc(c.phrased)}</div>`).join('')}</div>`:''}
    ${d.technical_corrections.length?`<h2>Specific technical corrections</h2>${d.technical_corrections.map(c=>`<div class="card" style="margin-bottom:10px"><div class="small muted">${esc(c.question)}</div>${c.errors.map(e=>`<div style="color:var(--bad)">✗ ${esc(e)}</div>`).join('')}${c.omitted.length?`<div class="small" style="color:var(--warn)">Omitted: ${c.omitted.map(esc).join('; ')}</div>`:''}${c.fix?`<div class="fix">${esc(c.fix)}</div>`:''}</div>`).join('')}`:''}
    ${d.delivery.notes.length?`<h2>Delivery</h2><div class="card small">${d.delivery.notes.map(n=>`<div>· ${esc(n)}</div>`).join('')}${d.delivery.repeated_phrases.length?`<div class="dim" style="margin-top:6px">Repeated phrases: ${d.delivery.repeated_phrases.map(esc).join('; ')}</div>`:''}<div class="dim" style="margin-top:6px">These are text measurements of the transcript (plus pause lengths from the recorder). They say nothing about confidence or character.</div></div>`:''}
    <h2 id="weak">Question by question</h2><details open><summary class="small muted">${d.questions.length} questions · click to collapse</summary>${qhtml || '<p class="muted">No answers recorded.</p>'}</details>
    ${d.remediation.length?`<h2>What to drill next</h2><div class="grid cols2">${d.remediation.map(r=>`<div class="card"><h4>${esc(r.name)} <span class="pill warn">${r.mastery}/5</span></h4><p>${esc(r.why)}</p><ul class="small" style="margin:8px 0 8px 18px">${r.drill.map(q=>`<li>${esc(q.text)}</li>`).join('')}</ul><button class="small" data-drill="${r.skill}">Start drill</button></div>`).join('')}</div>`:''}`;
  $('#retest').onclick = async () => { try { const r = await api(`/sessions/${sid}/retest`, {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e){ toast(e.message, true); } };
  $$('[data-teach]').forEach(b => b.onclick = () => navigate('#/teach/' + b.dataset.teach));
  $$('[data-next]').forEach(b => b.onclick = async () => { const a = (d.verdict.next_actions||[]).find(x=>x.key===b.dataset.next); if (!a) return; if (a.route) return navigate(a.route); if (a.retest) return $('#retest').click(); if (a.anchor) return document.getElementById(a.anchor)?.scrollIntoView({behavior:'smooth'}); if (a.evaluation_id) { try { const r = await api(`/evaluations/${a.evaluation_id}/reattempt`, {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e) { toast(e.message, true); } } });
  $$('[data-reattempt]').forEach(b => b.onclick = async () => { try { const r = await api(`/evaluations/${b.dataset.reattempt}/reattempt`, {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e){ toast(e.message, true); } });
  try { const sum = (await api('/sessions?limit=200')).find(x=>x.id===sid); const g = (sum && sum.summary) || {};
    const parts = [];
    if (g.career) parts.push(`<b>Career:</b> ${esc(g.career.bank)} ${esc(g.career.stage_key.replace('_',' '))}: ${g.career.passed?'<span style="color:var(--good)">PASSED</span>':'<span style="color:var(--bad)">not passed</span>'} (score ${Math.round(g.career.score*100)} vs pass mark ${Math.round(g.career.pass_mark*100)})${g.career.offer?' · <b>Fictional offer earned</b>':''} · +${g.career.xp} XP`);
    if (g.deathmatch) parts.push(`<b>Deathmatch:</b> ${g.deathmatch.score} pts · ${g.deathmatch.questions} questions · best streak ${g.deathmatch.best_streak} · personal record ${g.deathmatch.records.best_score}`);
    if (g.daily) parts.push(`<b>Daily Draft:</b> complete · streak ${g.daily.streak} day(s)`);
    if (g.xp_earned) parts.push(`<b>XP from answers:</b> +${g.xp_earned}`);
    if (g.achievements && g.achievements.length) parts.push(`<b>Achievements unlocked:</b> ${g.achievements.map(esc).join(', ')}`);
    if (parts.length) $('#gamebanner').innerHTML = `<div class="card" style="border-color:var(--accent);margin-bottom:16px">${parts.map(p=>`<div class="small" style="margin:3px 0">${p}</div>`).join('')}${g.career && !g.career.passed ? `<div class="row" style="margin-top:8px"><button class="small primary" id="rematch">Rematch with new questions</button></div>`:''}</div>`;
    const rm = $('#rematch'); if (rm) rm.onclick = async () => { const r = await api(`/career/${g.career.bank}/start`, {method:'POST'}); navigate('#/session/'+r.session.id); };
  } catch(e) { console.warn(e); }
  $$('[data-drill]').forEach(b => b.onclick = () => startSession('explain', {skill: b.dataset.drill, duration_min: 15, persona:'associate'}));
  $$('[data-appeal]').forEach(b => b.onclick = async () => {
    const id = b.dataset.appeal; const corr = $('#corr_'+id).value.trim(); const arg = $('#arg_'+id).value.trim();
    const body = {}; if (arg) body.argument = arg; const q = d.questions.find(x=>x.evaluation_id===id); if (corr && corr !== q.answer) body.corrected_text = corr;
    if (!body.argument && !body.corrected_text) { toast('Add a corrected transcript or an argument first.', true); return; }
    try { const r = await api(`/evaluations/${id}/appeal`, {method:'POST', body}); $('#appeal_'+id).textContent = `${r.note} Score ${fmtPct(q.score)} → ${fmtPct(r.evaluation.score)}${r.changed?'':' (unchanged)'}.`; } catch(e) { toast(e.message, true); }
  });
});

/* ------------------------------------------------------------------ skills */
route('skills', async () => {
  const s = await api('/skills');
  const byArea = {};
  s.skills.forEach(k => (byArea[k.area] = byArea[k.area] || []).push(k));
  const l = s.longitudinal;
  main.innerHTML = `<h1>Skill map</h1><p class="sub">Mastery is estimated from scored answers (recency- and difficulty-weighted, shrunk toward the middle when evidence is thin). "Not yet assessed" means exactly that: no assumption is made from your resume or the build notes.</p>
    <div class="grid cols4" style="margin-bottom:16px">
      <div class="card"><h3>Practice</h3><div class="scorebox"><div class="big">${l.practice_hours}h</div>${l.sessions_completed} sessions</div></div>
      <div class="card"><h3>Trend</h3><div class="small">${l.weekly_trend.length?l.weekly_trend.slice(-4).map(w=>`${w.week.slice(5)}: ${Math.round(w.avg*100)} (${w.n})`).join('<br>'):'insufficient data'}</div></div>
      <div class="card"><h3>Accuracy by area</h3><div class="small">${Object.entries(l.accuracy_by_area).map(([a,v])=>`${a} ${Math.round(v*100)}`).join(' · ')||'—'}</div></div>
      <div class="card"><h3>Recurring errors</h3><div class="small">${l.recurring_misconceptions.length?l.recurring_misconceptions.map(([k,n])=>`${esc(k)} ×${n}`).join('<br>'):'none recorded'}</div></div>
    </div>
    ${s.due.length?`<h2>Due for review (spaced)</h2><div class="row">${s.due.map(d=>`<button class="small" data-drill="${d.skill}">${esc(d.name)} · ${d.mastery}/5</button>`).join('')}</div>`:''}
    ${Object.entries(s.areas).map(([a,name]) => `<h2>${esc(name)}</h2><div class="heat">${(byArea[a]||[]).map(k => `<div class="cell ${k.state==='not_assessed'?'na':''}" title="${esc(k.prior_hint||'')}"><b>${esc(k.name)}</b>${k.state==='assessed'?`<div class="bar ${k.mastery>=3.75?'good':k.mastery>=2.5?'warn':'bad'}"><i style="width:${k.mastery/5*100}%"></i></div><div class="row small" style="justify-content:space-between;margin-top:4px"><span class="mono">${k.mastery}/5</span><span class="dim">n=${k.n_obs} · conf ${Math.round(k.confidence*100)}%${k.due?' · due':''}</span></div>`:`<div class="dim small">not yet assessed${k.prior_hint?' · <span style="color:var(--warn)">flagged in Oct notes</span>':''}</div>`}<div style="margin-top:6px"><button class="small ghost" data-drill="${k.skill}">drill</button></div></div>`).join('')}</div>`).join('')}
    ${s.remediation.length?`<h2>Remediation plan</h2>${s.remediation.map(r=>`<div class="card" style="margin-bottom:10px"><h4>${esc(r.name)} <span class="pill warn">${r.mastery}/5</span></h4><p>${esc(r.why)}</p><ul class="small" style="margin:8px 0 8px 18px">${r.drill.map(q=>`<li>${esc(q.text)} <span class="dim">(d${q.difficulty})</span></li>`).join('')}</ul><button class="small" data-drill="${r.skill}">Start this drill</button></div>`).join('')}`:''}`;
  $$('[data-drill]').forEach(b => b.onclick = () => startSession('explain', {skill: b.dataset.drill, duration_min: 15, persona: 'associate'}));
});

/* ------------------------------------------------------------------ resume defense */
route('resume', async () => {
  const bullets = await api('/resume-defense');
  const groups = {};
  bullets.forEach(b => (groups[b.org] = groups[b.org] || []).push(b));
  main.innerHTML = `<h1>Resume defense</h1><p class="sub">Every bullet, decomposed into claims, the concepts behind them, the credibility challenges a banker will raise, and the questions to expect. Unknowns are facts no document on this Mac answers; fill them in so the interviewer can hold you to them.</p>
    ${Object.entries(groups).map(([org, bs]) => `<h2>${esc(org)} <button class="small ghost" data-exp="${bs[0].experience_id}">Drill this experience</button></h2>${bs.map(b => `<details><summary>${esc(b.text)} <span class="badge-src">${esc(b.source)} · ${esc(b.status)}</span></summary>
      <div class="grid cols2" style="margin-top:10px">
        <div><h3>Claims</h3><ul class="small">${b.claims.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><h3>Concepts tested</h3><div>${b.concepts.map(c=>`<span class="pill">${esc(c)}</span>`).join('')}</div><h3>Credibility challenges</h3><ul class="small">${b.challenges.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>${b.discrepancies.length?`<h3 style="color:var(--bad)">Discrepancies</h3><ul class="small">${b.discrepancies.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:''}</div>
        <div><h3>Expected questions</h3><ul class="small">${b.questions.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>${b.advanced.length?`<h3>Advanced</h3><ul class="small">${b.advanced.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:''}<h3>Supporting documents</h3><div class="small muted">${b.evidence.map(esc).join(' · ')}</div></div>
      </div>
      ${b.unknowns.length?`<h3>Facts you need to supply</h3>${b.unknowns.map(u=>`<div class="row small" style="margin:4px 0"><span style="flex:1">${u.filled?'<span style="color:var(--good)">✓</span>':'<span style="color:var(--warn)">?</span>'} ${esc(u.ask)}</span><button class="small ghost" data-kb="${u.id}" data-topic="${b.experience_id}" data-ask="${esc(u.ask)}">${u.filled?'edit':'answer'}</button></div>`).join('')}`:''}
    </details>`).join('')}`).join('')}
    <div id="kbform"></div>`;
  $$('[data-exp]').forEach(b => b.onclick = () => startSession('resume_defense', {experience_id: b.dataset.exp, persona: 'vp', duration_min: 20}));
  $$('[data-kb]').forEach(b => b.onclick = () => {
    const f = $('#kbform');
    f.innerHTML = `<div class="card" style="position:sticky;bottom:10px;border-color:var(--accent)"><b>${esc(b.dataset.ask)}</b><textarea id="kbclaim" placeholder="Write only what is true. Example: 'Base case used the NYMEX strip for 2026–27 then flat $3.25 Henry Hub; Dominion South basis of −$0.85.'" style="margin-top:8px"></textarea><div class="row" style="margin-top:8px"><button class="primary" id="kbsave">Save to knowledge base</button><button class="ghost" onclick="document.getElementById('kbform').innerHTML=''">Cancel</button></div></div>`;
    f.scrollIntoView({behavior:'smooth'});
    $('#kbsave').onclick = async () => { const claim = $('#kbclaim').value.trim(); if (!claim) return; await api('/kb', {method:'POST', body:{topic: b.dataset.topic, key: b.dataset.kb, claim, source:'the candidate (KB entry)', status:'user'}}); toast('Saved. The interviewer can now hold you to it.'); render(); };
  });
});

/* In-page text panel (alert() is blocked in embedded browsers). */
function showText(text) {
  let ov = document.getElementById('textpanel');
  if (!ov) {
    ov = document.createElement('div'); ov.id = 'textpanel';
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:60;display:flex;align-items:center;justify-content:center;padding:16px';
    ov.innerHTML = '<div class="card" style="max-width:720px;width:100%;max-height:80vh;overflow:auto"><div class="row"><span class="spacer"></span><button id="textpanel-close">Close</button></div><div id="textpanel-body" style="white-space:pre-wrap;font-size:13px;margin-top:8px"></div></div>';
    document.body.appendChild(ov);
    ov.onclick = (e) => { if (e.target === ov || e.target.id === 'textpanel-close') ov.remove(); };
  }
  document.getElementById('textpanel-body').textContent = text;
}
/* Two-click confirm inside the page: native confirm() is blocked in embedded browsers (it silently returns false). */
function armConfirm(btn, label) {
  if (btn.dataset.armed === '1') { clearTimeout(btn._disarm); btn.dataset.armed = ''; btn.textContent = btn.dataset.label; return true; }
  btn.dataset.label = btn.textContent; btn.dataset.armed = '1'; btn.textContent = label;
  btn._disarm = setTimeout(() => { btn.dataset.armed = ''; btn.textContent = btn.dataset.label; }, 4000);
  return false;
}
/* ------------------------------------------------------------------ history */
route('history', async () => {
  const rows = await api('/sessions?limit=100');
  main.innerHTML = `<h1>History</h1><table><thead><tr><th>When</th><th>Mode</th><th>Config</th><th>Status</th><th>Result</th><th></th></tr></thead><tbody>
    ${rows.map(r => `<tr><td class="mono small">${new Date(r.created*1000).toLocaleString()}</td><td>${esc(r.mode_name)}</td><td class="small muted">${esc([r.config.bank, r.config.sector, r.config.persona, r.config.difficulty, r.config.skill].filter(Boolean).join(' · '))}</td><td><span class="pill ${r.status==='ended'?'good':'warn'}">${r.status}</span></td><td>${r.summary&&r.summary.avg!=null?chip(r.summary.avg)+` <span class="small muted">${r.summary.n} answers</span>`:'—'}</td><td class="row"><button class="small" onclick="location.hash='#/${r.status==='ended'?'debrief':'session'}/${r.id}'">${r.status==='ended'?'Debrief':'Resume'}</button><button class="small ghost danger" data-del="${r.id}">delete</button></td></tr>`).join('') || '<tr><td colspan="6" class="muted">No sessions yet.</td></tr>'}</tbody></table>`;
  $$('[data-del]').forEach(b => b.onclick = async (e) => { if (!armConfirm(e.currentTarget, 'Confirm delete')) return; await api('/sessions/'+b.dataset.del, {method:'DELETE'}); render(); });
});

/* ------------------------------------------------------------------ question bank */
route('bank', async () => {
  const qs = await api('/questions');
  const topics = [...new Set(qs.map(q=>q.topic))];
  const draw = (filter) => { const rows = qs.filter(q => (!filter.topic || q.topic===filter.topic) && (!filter.q || q.text.toLowerCase().includes(filter.q))); $('#qtable').innerHTML = rows.map(q => `<tr><td><span class="pill">${esc(q.topic)}</span></td><td>${esc(q.text)}<div class="dim small mono">${esc(q.skill)} · ${q.n_components} components · ${q.n_followups} follow-ups${q.prereqs.length?' · needs '+q.prereqs.join(', '):''}</div></td><td class="mono">d${q.difficulty}</td><td class="small muted">${q.times_asked?`asked ${q.times_asked}× · best ${fmtPct(q.best_score)}`:'—'}</td><td><button class="small ghost" data-q="${q.id}">rubric</button></td></tr>`).join(''); $$('[data-q]').forEach(b => b.onclick = async () => { const d = await api('/questions/'+b.dataset.q); showText(`${d.text}\n\nExpected components:\n${d.components.map(c=>'• '+c.text).join('\n')}\n\nMisconceptions:\n${d.misconceptions.map(m=>'• '+m.explain).join('\n')||'—'}\n\nSolution:\n${d.solution}${d.assumptions?'\n\nAssumptions: '+d.assumptions:''}`); }); $('#qcount').textContent = rows.length + ' questions'; };
  main.innerHTML = `<h1>Question bank</h1><p class="sub">${qs.length} authored questions plus ${HEALTH?HEALTH.numeric_generators.length:0} numeric generators (unlimited variants, programmatically verified) and ${77} resume-defense questions derived from your bullets.</p>
    <div class="row"><select id="ftopic" style="width:200px"><option value="">All topics</option>${topics.map(t=>`<option>${t}</option>`).join('')}</select><input id="fq" placeholder="search…" style="width:300px"><span class="muted small" id="qcount"></span></div>
    <table style="margin-top:12px"><thead><tr><th>Topic</th><th>Question</th><th>Diff</th><th>Your record</th><th></th></tr></thead><tbody id="qtable"></tbody></table>`;
  const f = {}; draw(f);
  $('#ftopic').onchange = e => { f.topic = e.target.value; draw(f); }; $('#fq').oninput = e => { f.q = e.target.value.toLowerCase(); draw(f); };
});

/* ------------------------------------------------------------------ profile & KB */
route('profile', async () => {
  const p = await api('/profile');
  main.innerHTML = `<h1>Profile &amp; knowledge base</h1><p class="sub">What the interviewer is allowed to treat as true about you, with its source. Anything marked <span class="pill warn">prompt_only</span> or <span class="pill bad">unknown</span> may be asked about but is never asserted.</p>
    ${p.discrepancies.length?`<div class="card" style="border-color:var(--warn);margin-bottom:16px"><h3>Discrepancies between your documents</h3>${p.discrepancies.map(d=>`<div class="small" style="margin:4px 0"><b>${esc(d.experience)}:</b> ${esc(d.issue)}</div>`).join('')}</div>`:''}
    <h2>Experiences</h2>${p.experiences.map(e => `<details><summary>${esc(e.org)} — ${esc(e.title)} <span class="badge-src">${esc(e.dates)}</span></summary>
      <h3>Resume bullets</h3><ul class="small">${e.bullets.map(b=>`<li>${esc(b.text)} <span class="badge-src">${esc(b.source)}</span></li>`).join('')}</ul>
      <h3>Documented facts</h3><ul class="small">${e.facts.map(f=>`<li>${esc(f.text)} <span class="badge-src">${esc(f.source)}</span></li>`).join('')}</ul>
      ${e.unknowns&&e.unknowns.length?`<h3>Unknowns (fill in Resume defense)</h3><ul class="small muted">${e.unknowns.map(u=>`<li>${esc(u.ask)}</li>`).join('')}</ul>`:''}</details>`).join('')}
    <h2>Stories</h2><div class="grid cols2">${p.stories.map(s => `<div class="card"><h4>${esc(s.title)} <span class="pill ${s.status==='verified'?'good':'warn'}">${s.status}</span>${s.sensitive?'<span class="pill bad">sensitive</span>':''}</h4><p>${esc(s.summary)}</p><div style="margin-top:6px">${s.categories.map(c=>`<span class="pill">${c}</span>`).join('')}${s.tennis?'<span class="pill">tennis</span>':''}</div>${s.gaps?`<div class="small" style="color:var(--warn);margin-top:6px">Gaps: ${s.gaps.map(esc).join('; ')}</div>`:''}</div>`).join('')}</div>
    <h2>Tell-me-about-yourself spine <span class="badge-src">${esc(p.tmay.source)}</span></h2><div class="card">${p.tmay.beats.map(([k,v])=>`<div class="small"><b>${k}</b> — ${esc(v)}</div>`).join('')}<h3>Known issues</h3><ul class="small">${p.tmay.known_issues.map(i=>`<li>${esc(i)}</li>`).join('')}</ul></div>
    <h2>Your knowledge base entries</h2><div class="card"><table><thead><tr><th>Topic</th><th>Key</th><th>Claim</th><th></th></tr></thead><tbody>${p.kb.map(k=>`<tr><td>${esc(k.topic)}</td><td class="mono small">${esc(k.key||'')}</td><td>${esc(k.claim)}</td><td><button class="small ghost danger" data-kbdel="${k.id}">delete</button></td></tr>`).join('')||'<tr><td colspan="4" class="muted">Nothing yet. Add facts from the Resume defense page or below.</td></tr>'}</tbody></table>
      <div class="grid cols3" style="margin-top:12px"><input id="kbt" placeholder="topic (e.g. hobo)"><input id="kbk" placeholder="key (optional)"><input id="kbc" placeholder="the fact, exactly as you'd say it"></div><div class="row" style="margin-top:8px"><button class="small" id="kbadd">Add fact</button></div></div>`;
  $$('[data-kbdel]').forEach(b => b.onclick = async () => { await api('/kb/'+b.dataset.kbdel, {method:'DELETE'}); render(); });
  $('#kbadd').onclick = async () => { const t=$('#kbt').value.trim(), c=$('#kbc').value.trim(); if(!t||!c) return; await api('/kb',{method:'POST',body:{topic:t,key:$('#kbk').value.trim()||null,claim:c,source:'the candidate (KB entry)',status:'user'}}); render(); };
});

/* ------------------------------------------------------------------ settings */
route('settings', async () => {
  const h = await api('/health'); SETTINGS = h.settings || {};
  let voices = []; try { voices = await api('/tts/voices'); } catch(e){}
  const bvoices = (window.speechSynthesis ? speechSynthesis.getVoices() : []).filter(v=>/en/.test(v.lang));
  let mics = []; try { mics = (await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='audioinput'); } catch(e){}
  main.innerHTML = `<h1>Settings</h1>
    <div class="grid cols2">
      <div class="card"><h3>Reasoning engine</h3>
        <div class="kv"><div>Active</div><div><b>${esc(h.llm.active)}</b></div><div>Anthropic API key</div><div>${h.llm.anthropic_api_key?'present (.env)':'not set'}</div><div>Claude CLI</div><div>${h.llm.claude_cli_path?(h.llm.claude_cli_logged_in?'logged in':'found, <b>not logged in</b>'):'not found'}</div><div>Calls / failures</div><div>${h.llm.calls} / ${h.llm.failures}</div>${h.llm.last_error?`<div>Last error</div><div class="small mono">${esc(h.llm.last_error)}</div>`:''}</div>
        <label>Preference</label><select id="st_llm"><option value="auto">auto (API → CLI → offline)</option><option value="anthropic_api">Anthropic API only</option><option value="claude_cli">Claude CLI only</option><option value="offline">offline (deterministic)</option></select>
        <label><input type="checkbox" id="st_use_llm" style="width:auto;margin-right:6px">Use the model for evaluation refinement when available</label>
        <label><input type="checkbox" id="st_llm_iv" style="width:auto;margin-right:6px">Let the model rephrase interviewer turns in persona voice</label>
        <div class="hint">Without a model, the engine is fully deterministic: rubric matching, numeric checks, misconception patterns and the follow-up trees in the question bank. To connect Claude: add <span class="mono">ANTHROPIC_API_KEY=…</span> to <span class="mono">gauntlet/.env</span>, or run <span class="mono">claude /login</span> once in a terminal and click probe.</div>
        <label><input type="checkbox" id="st_excerpts" style="width:auto;margin-right:6px">Send guide excerpts to the model when grading source-based questions</label>
        <div class="hint"><b>Disclosure:</b> when this is on and a model is connected, the reference answer from your local M&I 400 / Red Book copy for the question being graded is included in the grading prompt sent to Anthropic. When off, the model grades without the excerpt and only the local deterministic rubric uses it. The guides themselves never leave this Mac otherwise.</div>
        ${h.llm.last_error && /limit|reset/i.test(h.llm.last_error) ? `<div class="hint" style="color:var(--warn)">Usage limit: ${esc(h.llm.last_error)}. The engine falls back to deterministic grading until it resets.</div>` : ''}
        ${h.workers && h.workers.turns ? `<div class="hint">Persistent model workers: ${h.workers.turns} turns, avg ${h.workers.avg_ms} ms, ${h.workers.failures} failures.</div>` : ''}
        <div class="row" style="margin-top:8px"><button class="small" id="probe">Probe Claude CLI</button></div></div>
      <div class="card"><h3>Voice</h3>
        <label>Interviewer voice</label><select id="st_voice"><option value="browser">Browser speech (instant)</option><option value="mac">Mac system voice (higher quality, via server)</option><option value="off">Off (read the question)</option></select>
        <label>Browser voice</label><select id="st_bvoice"><option value="">auto</option>${bvoices.map(v=>`<option>${esc(v.name)}</option>`).join('')}</select>
        <label>Mac voice</label><select id="st_mvoice"><option value="">auto by persona</option>${voices.map(v=>`<option ${v.preferred?'':'class="dim"'}>${esc(v.name)}</option>`).join('')}</select>
        <label>Speech rate (Mac wpm)</label><input id="st_rate" type="number" min="120" max="240" value="${LS.get('ttsRate',175)}">
        <label>Microphone</label><select id="st_mic"><option value="">default</option>${mics.map(m=>`<option value="${m.deviceId}">${esc(m.label||m.deviceId.slice(0,8))}</option>`).join('')}</select>
        <label><input type="checkbox" id="st_autostop" style="width:auto;margin-right:6px">Stop recording automatically after silence</label>
        <label>Silence seconds before auto-stop</label><input id="st_sil" type="number" step="0.5" min="1" max="8" value="${SETTINGS.silence_seconds||2.5}">
        <label>Minimum answer seconds before auto-stop can trigger</label><input id="st_min" type="number" min="1" max="30" value="${SETTINGS.min_answer_seconds||4}">
        <label><input type="checkbox" id="st_live" style="width:auto;margin-right:6px">Show live browser captions while recording (if supported)</label>
        <label><input type="checkbox" id="st_autorec" style="width:auto;margin-right:6px">Start recording automatically when the interviewer finishes speaking</label>
        <label><input type="checkbox" id="st_autosub" style="width:auto;margin-right:6px">Submit automatically after transcription (no review step)</label>
        <label><input type="checkbox" id="st_keep" style="width:auto;margin-right:6px">Keep recordings on disk (data/audio); off by default. Transcripts are always kept with the session.</label>
        <label><input type="checkbox" id="st_interrupt" style="width:auto;margin-right:6px">Let the interviewer cut off answers that run long (150s technical / 90s numeric)</label>
        <div class="hint">Whisper model: ${esc(h.whisper.model)} (${h.whisper.loaded?'loaded':h.whisper.loading?'loading':'idle'}${h.whisper.error?' · error: '+esc(h.whisper.error):''}). Finance vocabulary is injected and common mis-hearings (WACC, EBITDA, NOL, PV-10…) are auto-corrected; you can always edit before submitting.</div></div>
      <div class="card"><h3>Content</h3>
        <label><input type="checkbox" id="st_health" style="width:auto;margin-right:6px">Allow the type 1 diabetes story to be asked about (off by default)</label>
        <div class="hint">Sensitive. When off, no question or sample answer references it.</div></div>
    </div>
    <div class="row" style="margin-top:16px"><button class="primary" id="save">Save</button><span class="muted small" id="saved"></span></div>`;
  $('#st_llm').value = SETTINGS.llm_provider || 'auto'; $('#st_excerpts').checked = SETTINGS.send_guide_excerpts !== false; $('#st_use_llm').checked = SETTINGS.use_llm !== false; $('#st_llm_iv').checked = SETTINGS.llm_interviewer !== false;
  $('#st_voice').value = voiceMode(); $('#st_bvoice').value = LS.get('browserVoice','')||''; $('#st_mvoice').value = LS.get('macVoice','')||''; $('#st_mic').value = LS.get('micId','')||'';
  $('#st_autostop').checked = LS.get('autoStop', true); $('#st_interrupt').checked = LS.get('interruptLong', true); $('#st_live').checked = LS.get('liveCaptions', true); $('#st_autorec').checked = LS.get('autoRecord', false); $('#st_autosub').checked = LS.get('autoSubmit', false); $('#st_keep').checked = LS.get('keepAudio', false);
  $('#st_health').checked = !!SETTINGS.include_health_story;
  $('#probe').onclick = async () => { const r = await api('/llm/probe', {method:'POST'}); toast(r.cli_logged_in ? 'Claude CLI is logged in and usable.' : 'Claude CLI not logged in: ' + (r.status.last_error||'').slice(0,120), !r.cli_logged_in); render(); };
  $('#save').onclick = async () => {
    LS.set('voiceMode', $('#st_voice').value); LS.set('browserVoice', $('#st_bvoice').value||null); LS.set('macVoice', $('#st_mvoice').value||null); LS.set('ttsRate', +$('#st_rate').value); LS.set('micId', $('#st_mic').value||null);
    LS.set('autoStop', $('#st_autostop').checked); LS.set('interruptLong', $('#st_interrupt').checked); LS.set('liveCaptions', $('#st_live').checked); LS.set('autoRecord', $('#st_autorec').checked); LS.set('autoSubmit', $('#st_autosub').checked); LS.set('keepAudio', $('#st_keep').checked);
    await api('/settings', {method:'POST', body:{settings:{llm_provider: $('#st_llm').value, use_llm: $('#st_use_llm').checked, llm_interviewer: $('#st_llm_iv').checked, silence_seconds: +$('#st_sil').value, min_answer_seconds: +$('#st_min').value, include_health_story: $('#st_health').checked, send_guide_excerpts: $('#st_excerpts').checked}}});
    $('#saved').textContent = 'Saved.'; loadHealth();
  };
});

/* ------------------------------------------------------------------ boot */
window.G = { route, api, esc, chip, fmtPct, fmtTime, toast, LS, startSession, navigate, render, Room, showLiveEval, handleInterviewer, showSetup, get HEALTH(){ return HEALTH; }, get SETTINGS(){ return SETTINGS; }, routes, main };
if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {};
const boot = () => loadHealth().then(render);
if (document.readyState === 'complete') boot(); else window.addEventListener('load', boot);
setInterval(loadHealth, 30000);
})();
