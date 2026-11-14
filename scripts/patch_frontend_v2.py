"""One-off patch applying the 2.0 frontend changes to app.js and index.html (kept for traceability)."""
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")


def patch(path, pairs):
    p = os.path.join(ROOT, path)
    s = open(p).read()
    for old, new in pairs:
        assert old in s, (path, old[:60])
        s = s.replace(old, new)
    open(p, "w").write(s)


patch("static/app.js", [
    ("""/* ------------------------------------------------------------------ boot */
if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {};
loadHealth().then(render);
setInterval(loadHealth, 30000);
})();""", """/* ------------------------------------------------------------------ boot */
window.G = { route, api, esc, chip, fmtPct, fmtTime, toast, LS, startSession, navigate, render, Room, showLiveEval, handleInterviewer, get HEALTH(){ return HEALTH; }, get SETTINGS(){ return SETTINGS; }, routes, main };
if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {};
const boot = () => loadHealth().then(render);
if (document.readyState === 'complete') boot(); else window.addEventListener('load', boot);
setInterval(loadHealth, 30000);
})();"""),
    ("""  <div class="row" style="margin-bottom:12px"><h1 style="font-size:20px;margin:0">${esc(s.mode_name)}</h1>""",
     """  <div class="row" style="margin-bottom:12px"><h1 style="font-size:20px;margin:0">${esc(s.mode_name)}</h1>
    ${s.deathmatch ? `<span class="pill bad" id="hud-lives">${hearts(s.deathmatch.lives)}</span><span class="pill acc" id="hud-score">${s.deathmatch.score} pts · streak ${s.deathmatch.streak}</span>` : ''}
    ${s.career ? `<span class="pill acc">${esc(s.career.bank)} · ${esc(s.career.stage_key.replace('_',' '))}${s.career.boss?' · boss':''}</span>` : ''}
    ${s.daily ? `<span class="pill info">Daily Draft ${esc(s.daily.date)}</span>` : ''}"""),
    ("""function handleInterviewer(turns, state) {
  Room.session = state; Room._syncAt = Date.now();""", """function hearts(n) { let out = ''; for (let i = 0; i < 3; i++) out += i < n ? '\\u2665' : '\\u2661'; return out; }
function handleInterviewer(turns, state) {
  Room.session = state; Room._syncAt = Date.now();
  if (state.deathmatch) { const l = $('#hud-lives'), sc = $('#hud-score'); if (l) l.textContent = hearts(state.deathmatch.lives); if (sc) sc.textContent = `${state.deathmatch.score} pts · streak ${state.deathmatch.streak}${state.deathmatch.boss_pending ? ' · BOSS next' : ''}`; }"""),
    ("""    <div class="card" style="margin-bottom:16px"><b>${esc(o.readiness)}</b><div class="small dim" style="margin-top:4px">${esc(o.caveat)}</div></div>""",
     """    <div class="card" style="margin-bottom:16px"><b>${esc(o.readiness)}</b><div class="small dim" style="margin-top:4px">${esc(o.caveat)}</div>${d.pending_deep_grades?`<div class="small" style="color:var(--warn);margin-top:6px">${d.pending_deep_grades} answer(s) still carry a provisional (rule-based) grade; the model's deep grade is pending or unavailable. Reload to refresh.</div>`:''}</div>
    <div id="gamebanner"></div>
    ${d.callbacks && d.callbacks.length ? `<div class="card" style="margin-bottom:16px"><h3>Callbacks</h3>${d.callbacks.map(c=>`<div class="small">${c.success?'<span style="color:var(--good)">OK</span>':'<span style="color:var(--bad)">X</span>'} ${esc(c.skill)}: revisited later ${c.success?'and held up':'and still missed'} (${Math.round(c.score*100)})</div>`).join('')}</div>` : ''}"""),
    ("""      ${q.coach_notes?`<div class="small dim" style="margin-top:6px"><b>Coach notes:</b> ${esc(q.coach_notes)}</div>`:''}""",
     """      ${q.coach_notes?`<div class="small dim" style="margin-top:6px"><b>Coach notes:</b> ${esc(q.coach_notes)}</div>`:''}
      ${q.citation?`<div class="small dim" style="margin-top:4px">Source: ${esc(q.citation.short)} · ${esc(q.citation.section||'')} · p.${q.citation.page} <span class="pill ${q.citation.verification==='verified'?'good':'warn'}">${q.citation.verification}</span></div>`:''}
      ${q.callback_of?`<span class="pill info">callback</span>`:''}${q.provisional?`<span class="pill warn" title="rule-based grade; deep grade pending">provisional</span>`:''}
      ${q.skill?`<div class="row" style="margin-top:8px"><button class="small ghost" data-teach="${q.skill}">Teach me why</button>${q.evaluation_id?`<button class="small ghost" data-reattempt="${q.evaluation_id}">Reattempt concept</button>`:''}</div>`:''}"""),
    ("""  $('#retest').onclick = async () => { try { const r = await api(`/sessions/${sid}/retest`, {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e){ toast(e.message, true); } };""",
     """  $('#retest').onclick = async () => { try { const r = await api(`/sessions/${sid}/retest`, {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e){ toast(e.message, true); } };
  $$('[data-teach]').forEach(b => b.onclick = () => navigate('#/teach/' + b.dataset.teach));
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
  } catch(e) { console.warn(e); }"""),
])

patch("static/index.html", [
    ('<script src="/app.js"></script>', '<script src="/app.js"></script>\n<script src="/game.js"></script>'),
    ("""    <a class="item" href="#/home" data-route="home">Home</a>
    <a class="item" href="#/skills" data-route="skills">Skill map</a>""", """    <a class="item" href="#/home" data-route="home">Dashboard</a>
    <a class="item" href="#/career" data-route="career">Career mode</a>
    <a class="item" href="#/lab" data-route="lab">Weakness lab</a>
    <a class="item" href="#/modeling" data-route="modeling">Modeling lab</a>
    <a class="item" href="#/skills" data-route="skills">Skill graph</a>"""),
    ('<div class="brand">The Gauntlet<small>IB interview simulator</small></div>', '<div class="brand">The Gauntlet 2.0<small>Master the technicals. Survive the superday.</small></div>'),
    ("<title>The Gauntlet</title>", "<title>The Gauntlet 2.0</title>"),
])
print("frontend patched")
