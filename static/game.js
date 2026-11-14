/* The Gauntlet 2.0: dashboard, career mode, weakness lab, modeling lab, teach pages, skill graph. */
(() => {
'use strict';
const { route, api, esc, chip, fmtPct, toast, LS, startSession, navigate, main } = window.G;
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
const STATE_COLOR = { untested: 'var(--dim)', learning: 'var(--bad)', developing: 'var(--warn)', proficient: 'var(--info)', mastered: 'var(--good)', review_due: 'var(--accent)' };
const stateChip = st => `<span class="pill" style="color:${STATE_COLOR[st]||'var(--muted)'};border-color:${STATE_COLOR[st]||'var(--line)'}">${esc(st.replace('_',' '))}</span>`;

/* ------------------------------------------------------------------ dashboard (replaces home) */
route('home', async () => {
  const [skills, game, sessions, modes] = await Promise.all([api('/skills'), api('/game/summary'), api('/sessions?limit=8'), api('/modes')]);
  const rd = skills.readiness; const lg = skills.longitudinal;
  const active = sessions.find(s => s.status === 'active');
  const areaStats = {};
  skills.skills.filter(s => !['behavioral','resume','deal'].includes(s.area)).forEach(s => { const a = areaStats[s.area] = areaStats[s.area] || {n:0, assessed:0, sum:0, states:{}}; a.n++; if (s.state==='assessed') { a.assessed++; a.sum += s.mastery; } a.states[s.mastery_state] = (a.states[s.mastery_state]||0)+1; });
  const weakest = skills.weaknesses.filter(w => !['behavioral','resume','deal'].includes(w.area)).slice(0,5);
  const rec = recommend(skills, game);
  const trend = lg.weekly_trend.slice(-6);
  main.innerHTML = `
    <div class="row"><div><h1>The Gauntlet 2.0</h1><p class="sub" style="margin:0">Master the technicals. Survive the superday.</p></div><span class="spacer"></span>
      <div class="row"><span class="pill acc">${esc(game.xp.name)} · Lv ${game.xp.level} · ${game.xp.xp} XP</span><span class="pill ${game.daily.completed?'good':'warn'}">Daily ${game.daily.completed?'done':'open'} · streak ${game.daily.streak}</span></div></div>
    ${active ? `<div class="card" style="border-color:var(--accent);margin:14px 0"><div class="row"><div><h4>Interview in progress: ${esc(active.mode_name)}</h4><p>State is saved after every turn.</p></div><span class="spacer"></span><button class="primary" onclick="location.hash='#/session/${active.id}'">Resume</button></div></div>` : ''}
    <div class="grid cols4" style="margin:16px 0">
      <div class="card"><h3>Technical readiness</h3>${rd.status==='estimate' ? `<div class="scorebox"><div class="big">${rd.estimate.toFixed(1)}<span class="muted" style="font-size:14px">/5</span></div>confidence ${Math.round(rd.confidence*100)}%</div>` : `<div class="scorebox"><div class="big" style="font-size:20px;color:var(--muted)">Not enough data</div>${rd.assessed} of ${rd.total} technical skills assessed</div>`}<div class="hint">${esc(rd.message)}</div></div>
      <div class="card"><h3>Curriculum coverage</h3><div class="scorebox"><div class="big">${Math.round(rd.coverage*100)}%</div>${rd.assessed}/${rd.total} skills assessed</div><div class="bar" style="margin-top:6px"><i style="width:${Math.round(rd.coverage*100)}%"></i></div><div class="hint">${Object.entries(rd.states||{}).map(([k,v])=>`${k.replace('_',' ')} ${v}`).join(' · ')||'no assessments yet'}</div></div>
      <div class="card"><h3>Recent performance</h3>${trend.length ? `<div class="small">${trend.map(w=>`<div class="row" style="gap:8px"><span class="mono muted" style="width:60px">${w.week.slice(5)}</span><div class="bar ${w.avg>=0.75?'good':w.avg>=0.5?'warn':'bad'}" style="flex:1"><i style="width:${Math.round(w.avg*100)}%"></i></div><span class="mono">${Math.round(w.avg*100)} <span class="dim">(${w.n})</span></span></div>`).join('')}</div>` : '<div class="muted small">No scored sessions yet.</div>'}<div class="hint">${lg.sessions_completed} sessions · ${lg.practice_hours}h · ${lg.answers_evaluated} answers</div></div>
      <div class="card"><h3>Career rank</h3><div class="scorebox"><div class="big">${esc(game.xp.name)}</div>Level ${game.xp.level}${game.xp.next_at?` · ${game.xp.next_at-game.xp.xp} XP to ${esc(game.xp.next_name)}`:''}</div><div class="bar" style="margin-top:6px"><i style="width:${Math.round(game.xp.progress*100)}%"></i></div><div class="hint">${Object.values(game.achievements).filter(a=>a.unlocked).length}/${Object.keys(game.achievements).length} achievements · ${game.career.offers.length} fictional offer(s)</div></div>
    </div>
    <div class="grid cols2">
      <div class="card"><h3>Technical mastery by area</h3>${Object.entries(areaStats).map(([a,s])=>`<div class="row small" style="gap:8px;margin:4px 0"><span style="width:110px" class="muted">${esc(skills.areas[a]||a)}</span><div class="bar ${s.assessed? (s.sum/s.assessed>=3.75?'good':s.sum/s.assessed>=2.5?'warn':'bad'):''}" style="flex:1"><i style="width:${s.assessed?Math.round(s.sum/s.assessed/5*100):0}%"></i></div><span class="mono" style="width:120px;text-align:right">${s.assessed?(s.sum/s.assessed).toFixed(1)+'/5':'untested'} <span class="dim">${s.assessed}/${s.n}</span></span></div>`).join('')}<div class="hint">Mastery moves only on evidence; XP never changes it.</div></div>
      <div class="card"><h3>Weakest skills</h3>${weakest.length ? weakest.map(w=>`<div class="row small" style="margin:4px 0"><span style="flex:1">${esc(w.name)}</span>${stateChip(w.mastery_state)}<span class="mono">${w.mastery}/5</span><button class="small ghost" data-drill="${w.skill}">drill</button></div>`).join('') : '<div class="muted small">Nothing assessed yet.</div>'}
        ${skills.due.length?`<h3 style="margin-top:12px">Due for review</h3><div class="row">${skills.due.slice(0,5).map(d=>`<button class="small" data-drill="${d.skill}">${esc(d.name)}</button>`).join('')}</div>`:''}</div>
    </div>
    <div class="card" style="margin:14px 0;border-color:var(--accent)"><div class="row"><div><h3 style="margin-top:0">Recommended challenge</h3><h4 style="margin:0">${esc(rec.title)}</h4><p>${esc(rec.why)}</p></div><span class="spacer"></span><button class="primary" id="recgo">${esc(rec.cta)}</button>${!game.daily.completed?`<button id="dailygo">Daily Draft</button>`:''}</div></div>
    <h2>Modes</h2>
    <div class="grid cols3">
      ${[['career','Career Mode','Campaign at a named bank, stage by stage. Fictional offers.','#/career'],['deathmatch','Technical Deathmatch','Three lives, rising difficulty, boss every fifth question.',null],['superday','Interview Room','Customizable realistic interview: length, focus, persona, pressure.',null],['weakness_lab','Weakness Lab','Diagnoses the real gap and teaches immediately.','#/lab'],['daily','Daily Draft','5–10 minutes built from your reviews and weak spots.',null],['modeling','Modeling Lab','Mental math arena and written modeling challenges.','#/modeling']].map(([k,n,d,h])=>`<div class="card click" data-go="${k}" data-href="${h||''}"><h4>${n}</h4><p>${d}</p></div>`).join('')}
    </div>
    <details style="margin-top:14px"><summary>All interview modes (${modes.length})</summary><div class="grid cols2" style="margin-top:10px">${modes.filter(m=>!['career','deathmatch','daily','weakness_lab'].includes(m.key)).map(m=>`<div class="card click" data-mode="${m.key}"><h4>${esc(m.name)}</h4><p>${esc(m.desc)}</p></div>`).join('')}</div><div id="setup"></div></details>
    <div class="card small muted" style="margin-top:14px">${esc(game.career.disclaimer)}</div>`;
  $$('[data-drill]').forEach(b => b.onclick = () => api('/lab/start', {method:'POST', body:{skill: b.dataset.drill}}).then(r => navigate('#/session/'+r.session.id)));
  $$('[data-go]').forEach(c => c.onclick = () => { const k = c.dataset.go; if (c.dataset.href) return navigate(c.dataset.href); if (k==='deathmatch') return api('/deathmatch/start',{method:'POST',body:{}}).then(r=>{ if (r.resumed) toast('Resuming your open Deathmatch run.'); navigate('#/session/'+r.session.id); }); if (k==='daily') return startDaily(); if (k==='superday') { location.hash = '#/home'; openSetup('superday', modes); } });
  $$('[data-mode]').forEach(el => el.onclick = () => openSetup(el.dataset.mode, modes));
  $('#recgo').onclick = rec.go;
  const dg = $('#dailygo'); if (dg) dg.onclick = startDaily;
});

function openSetup(mode, modes) { const det = $('details'); if (det) det.open = true; window.G.routes.__setup && window.G.routes.__setup(mode, modes); /* fallback: */ if (!window.G.routes.__setup) { startSession(mode, {}); } }
async function startDaily() { try { const r = await api('/daily/start', {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e) { toast(e.message, true); } }

function recommend(skills, game) {
  const rd = skills.readiness;
  if (!game.daily.completed) return { title: 'Daily Draft', why: 'Ten minutes on your due reviews, weak skills and untested foundations. Keeps the streak honest.', cta: 'Start Daily Draft', go: startDaily };
  if (rd.status !== 'estimate') return { title: 'Interview Room: 15-minute technical screen', why: 'Fewer than eight technical skills are assessed, so there is no readiness estimate yet. A short mixed technical session builds the evidence base.', cta: 'Start 15-min technical', go: () => startSession('superday', {persona:'associate', duration_min:15, technical_weight:0.95, difficulty:'medium', resume_questions:false}) };
  if (skills.weaknesses.length && skills.weaknesses[0].mastery < 2.5) return { title: 'Weakness Lab: ' + skills.weaknesses[0].name, why: 'Your weakest assessed skill is at ' + skills.weaknesses[0].mastery + '/5. The lab finds the prerequisite that is actually failing and teaches it.', cta: 'Open the lab', go: () => api('/lab/start',{method:'POST',body:{skill: skills.weaknesses[0].skill}}).then(r=>navigate('#/session/'+r.session.id)) };
  const camp = game.career.active[0] || game.career.banks[0];
  return { title: 'Career Mode: ' + camp.name + ' ' + (camp.stage_name||''), why: 'Readiness estimate ' + rd.estimate.toFixed(1) + '/5 at ' + Math.round(rd.coverage*100) + '% coverage. Test it under campaign conditions.', cta: 'Start the round', go: () => api('/career/'+camp.bank+'/start',{method:'POST'}).then(r=>navigate('#/session/'+r.session.id)) };
}

/* ------------------------------------------------------------------ career */
route('career', async () => {
  const c = await api('/career');
  main.innerHTML = `<h1>Career Mode</h1><p class="sub">${esc(c.disclaimer)}</p>
    <div class="row small muted" style="margin-bottom:12px">${c.stages.map((s,i)=>`<span class="pill">${i+1}. ${esc(s.name)} · ${s.minutes}m · pass ${Math.round(s.pass*100)}${s.boss?' · boss':''}</span>`).join('')}<span class="pill good">6. Fictional offer</span></div>
    <div class="grid cols3">${c.banks.map(b => `<div class="card"><div class="row"><h4 style="margin:0">${esc(b.name)}</h4><span class="spacer"></span>${b.offer?'<span class="pill good">OFFER</span>':`<span class="pill ${b.stage?'acc':''}">${esc(b.stage_name)}</span>`}</div>
      <div class="row" style="gap:4px;margin:8px 0">${c.stages.map((s,i)=>`<span title="${esc(s.name)}" style="flex:1;height:6px;border-radius:3px;background:${i<b.stage?'var(--good)':i===b.stage&&!b.offer?'var(--accent)':'var(--panel2)'}"></span>`).join('')}</div>
      <p class="small">${b.attempts} attempt(s) · ${b.passed} passed${b.research?' · firm research loaded':' · generic firm context'}</p>
      ${b.history.length?`<div class="small dim">${b.history.slice(-3).map(h=>`${esc(h.stage_key.replace('_',' '))}: ${Math.round(h.score*100)} ${h.passed?'pass':'fail'}`).join(' · ')}</div>`:''}
      <div class="row" style="margin-top:8px">${b.offer?`<span class="small muted">Offer earned ${new Date(b.offer*1000).toLocaleDateString()}</span>`:`<button class="small primary" data-start="${b.bank}">${b.stage?'Continue':'Start'}: ${esc(b.next.name)}</button>`}<select class="small" data-sector="${b.bank}" style="width:auto"><option value="">Generalist</option>${['healthcare','energy','fig','m&a','tmt','industrials'].map(s=>`<option>${s}</option>`).join('')}</select></div></div>`).join('')}</div>`;
  $$('[data-start]').forEach(b => b.onclick = async () => { const sec = $(`[data-sector="${b.dataset.start}"]`).value; try { const r = await api(`/career/${b.dataset.start}/start${sec?'?sector='+encodeURIComponent(sec):''}`, {method:'POST'}); if (r.resumed) toast('Resuming your open interview at this bank.'); navigate('#/session/'+r.session.id); } catch(e) { toast(e.message, true); } });
});

/* ------------------------------------------------------------------ weakness lab */
route('lab', async ([skill]) => {
  const plan = await api('/lab/plan' + (skill ? '?skill='+encodeURIComponent(skill) : ''));
  const skills = await api('/skills');
  const byId = Object.fromEntries(skills.skills.map(s=>[s.skill, s]));
  main.innerHTML = `<h1>Weakness Lab</h1><p class="sub">Finds the prerequisite that is actually failing, teaches it immediately, then tests transfer with new numbers. Unlike interviews, feedback here is instant.</p>
    <div class="card" style="border-color:var(--accent)"><h3 style="margin-top:0">Today's plan</h3>
      ${plan.diagnoses.length ? plan.diagnoses.map(d=>`<div class="small" style="margin:4px 0"><b>${esc(byId[d.skill]?.name||d.skill)}</b> → root cause <b>${esc(byId[d.root]?.name||d.root)}</b>. ${esc(d.advice)}</div>`).join('') : '<div class="small muted">No weaknesses assessed yet; the lab starts with foundations.</div>'}
      <div class="row" style="margin-top:8px">${plan.focus_skills.map(f=>`<span class="pill">${esc(byId[f]?.name||f)}</span>`).join('')}</div>
      <div class="row" style="margin-top:10px"><button class="primary" id="labgo">Start lab session (${plan.max_questions} questions)</button><span class="muted small">${plan.duration_min} min · ${esc(plan.persona)} persona</span></div></div>
    <h2>Pick a skill to diagnose or learn</h2>
    <div class="row"><select id="labskill" style="width:360px">${skills.skills.filter(s=>!['behavioral','resume','deal'].includes(s.area)).map(s=>`<option value="${s.skill}" ${s.skill===skill?'selected':''}>${esc(s.name)} (${s.mastery_state.replace('_',' ')})</option>`).join('')}</select><button id="diag">Diagnose</button><button id="teach">Teach me why</button><button class="ghost" id="labone">Lab on this skill</button></div>
    <div id="diagout" style="margin-top:12px"></div>`;
  $('#labgo').onclick = async () => { const r = await api('/lab/start',{method:'POST',body: skill?{skill}:{}}); navigate('#/session/'+r.session.id); };
  $('#labone').onclick = async () => { const r = await api('/lab/start',{method:'POST',body:{skill: $('#labskill').value}}); navigate('#/session/'+r.session.id); };
  $('#teach').onclick = () => navigate('#/teach/' + $('#labskill').value);
  $('#diag').onclick = async () => { const d = await api(`/skills/${$('#labskill').value}/diagnose`); $('#diagout').innerHTML = `<div class="card"><h4>${esc(d.name)}</h4><p>${esc(d.advice)}</p><h3>Prerequisite chain</h3>${d.chain.map(c=>`<div class="row small" style="margin:3px 0;padding-left:${c.depth*14}px"><span style="flex:1">${esc(c.name)}</span>${stateChip(c.state)}<span class="mono">${c.mastery!=null?c.mastery+'/5':'—'} · n=${c.n_obs}</span></div>`).join('')}
    ${d.recent_mistakes.length?`<h3>Recent mistakes</h3>${d.recent_mistakes.map(m=>`<div class="small" style="color:var(--warn)">· ${esc(m.key||'')}${m.misconceptions.length?' — '+m.misconceptions.map(esc).join('; '):''}</div>`).join('')}`:''}
    ${d.weakest_level?`<div class="small" style="margin-top:6px">Breaks down at level ${d.weakest_level} (${['','definition','mechanics','understanding','application','exceptions'][d.weakest_level]}).</div>`:''}</div>`; };
});

/* ------------------------------------------------------------------ teach me why */
route('teach', async ([skill]) => {
  const t = await api(`/skills/${skill}/teach`);
  main.innerHTML = `<div class="row"><h1>Teach me why: ${esc(t.name)}</h1><span class="spacer"></span><button onclick="history.back()">Back</button><button class="primary" id="practice">Practice this now</button></div>
    <p class="sub">${esc(t.note)}</p>
    <div class="card"><h3>In one breath</h3><p>${esc(t.short)||'<span class="muted">No authored summary for this skill yet; see the sources below.</span>'}</p></div>
    ${t.detailed.length?`<h2>Step by step</h2>${t.detailed.map(d=>`<details ${d.level<=2?'open':''}><summary>Level ${d.level}: ${esc(d.question)}</summary><p>${esc(d.explanation)}</p>${d.assumptions?`<div class="small dim">Assumptions: ${esc(d.assumptions)}</div>`:''}${d.misconceptions.length?`<div class="small" style="color:var(--warn)">Common errors: ${d.misconceptions.map(esc).join(' · ')}</div>`:''}</details>`).join('')}`:''}
    ${t.worked_example?`<h2>Worked example</h2><div class="card"><p><b>${esc(t.worked_example.prompt)}</b></p><p class="mono small">${esc(t.worked_example.solution)}</p></div>`:''}
    ${t.source_excerpts.length?`<h2>From your guides</h2>${t.source_excerpts.map(x=>`<details><summary>${esc(x.question)} <span class="badge-src">${esc(x.citation.short)} p.${x.citation.page} · L${x.level}</span></summary><p class="small">${esc(x.answer)}</p></details>`).join('')}<div class="hint">Excerpts are read from your local copies only; they are not published anywhere.</div>`:''}
    ${t.related.length?`<h2>Related concepts</h2><div class="row">${t.related.map(r=>`<button class="small ghost" onclick="location.hash='#/teach/${r.skill}'">${esc(r.name)}</button>`).join('')}</div>`:''}`;
  $('#practice').onclick = async () => { const r = await api('/lab/start',{method:'POST',body:{skill}}); navigate('#/session/'+r.session.id); };
});

/* ------------------------------------------------------------------ modeling lab */
route('modeling', async ([name, seed]) => {
  if (name) return modelingChallenge(name, seed ? +seed : undefined);
  const list = await api('/modeling/challenges');
  main.innerHTML = `<h1>Modeling Lab</h1><p class="sub">Two experiences: the Mental Math Arena (voice-first, no calculator, timed) and written challenges with a scratchpad, graded step by step.</p>
    <div class="grid cols2"><div class="card" style="border-color:var(--accent)"><h3 style="margin-top:0">Mental Math Arena</h3><p>Numeric-only rapid fire: IRR from MOIC, terminal values, EV bridges, WACC, accretion arithmetic, royalty checks. Speak the answer. No calculator.</p>
      <div class="row"><select id="arena_min" style="width:auto"><option value="5">5 min</option><option value="10">10 min</option></select><select id="arena_q" style="width:auto"><option value="10">10 questions</option><option value="20">20 questions</option></select><select id="arena_d" style="width:auto"><option value="easy">Easy</option><option value="medium" selected>Medium</option><option value="hard">Hard</option></select><button class="primary" id="arena">Enter the arena</button></div></div>
      <div class="card"><h3 style="margin-top:0">Written challenges</h3>${list.map(c=>`<div class="row small" style="margin:6px 0"><span style="flex:1"><b>${esc(c.title)}</b><br><span class="dim">${esc(c.skill)} · ~${c.minutes} min</span></span><button class="small" onclick="location.hash='#/modeling/${c.name}'">Start</button></div>`).join('')}<div class="hint">Every step is verified deterministically; a wrong step shows the expected figure and the hint, never a model's guess.</div></div></div>`;
  $('#arena').onclick = async () => { const r = await api('/arena/start',{method:'POST',body:{minutes:+$('#arena_min').value, questions:+$('#arena_q').value, difficulty:$('#arena_d').value}}); navigate('#/session/'+r.session.id); };
});

async function modelingChallenge(name, seed) {
  const ch = await api(`/modeling/new/${name}` + (seed!=null?`?seed=${seed}`:''));
  const t0 = Date.now();
  main.innerHTML = `<div class="row"><h1 style="font-size:20px">${esc(ch.title)}</h1><span class="spacer"></span><span class="pill">${ch.calculator?'calculator allowed':'mental math only'}</span><span class="pill">~${ch.minutes} min</span><span class="timer" id="mtimer">0:00</span></div>
    <div class="room"><div><div class="card"><h3>Givens</h3><div class="kv">${Object.entries(ch.givens).map(([k,v])=>`<div>${esc(k)}</div><div class="mono">${esc(String(v))}</div>`).join('')}</div></div>
      <div class="card" style="margin-top:12px"><h3>Your answers</h3>${ch.steps.map(s=>`<div class="row" style="margin:6px 0"><label style="flex:1;margin:0;text-transform:none;letter-spacing:0;font-size:13px;color:var(--text)">${esc(s.prompt)}</label><input data-step="${s.id}" type="number" step="any" style="width:160px"><button class="small ghost" data-hint="${esc(s.hint)}">hint</button></div>`).join('')}
        <div class="row" style="margin-top:10px"><button class="primary" id="grade">Grade</button><button class="ghost" onclick="location.hash='#/modeling/${name}'">New numbers</button></div></div>
      <div id="result" style="margin-top:12px"></div></div>
      <div class="side"><div class="card"><h3>Scratchpad</h3><textarea id="scratch" style="min-height:220px;font-family:var(--mono);font-size:13px" placeholder="Work it out here. Nothing typed here is graded."></textarea></div>
      ${ch.calculator?`<div class="card"><h3>Calculator</h3><input id="calc" class="mono" placeholder="e.g. 120*1.03/(0.09-0.03)"><div class="mono small" id="calcout" style="margin-top:6px;color:var(--accent2)"></div></div>`:''}</div></div>`;
  const timer = setInterval(() => { const el = $('#mtimer'); if (!el) return clearInterval(timer); const s = Math.round((Date.now()-t0)/1000); el.textContent = `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`; }, 1000);
  $$('[data-hint]').forEach(b => b.onclick = () => toast(b.dataset.hint));
  const calc = $('#calc'); if (calc) calc.oninput = () => { try { const expr = calc.value.replace(/[^0-9+\-*/().^ ]/g,'').replace(/\^/g,'**'); $('#calcout').textContent = expr ? String(Function('"use strict";return ('+expr+')')()) : ''; } catch(e) { $('#calcout').textContent = '…'; } };
  $('#grade').onclick = async () => {
    const answers = {}; $$('[data-step]').forEach(i => { if (i.value !== '') answers[i.dataset.step] = +i.value; });
    const g = await api('/modeling/grade', {method:'POST', body:{name, seed: ch.seed, answers, seconds: (Date.now()-t0)/1000}});
    $('#result').innerHTML = `<div class="card" style="border-color:${g.score>=0.8?'var(--good)':g.score>=0.5?'var(--warn)':'var(--bad)'}"><div class="row"><h3 style="margin:0">Result</h3><span class="spacer"></span>${chip(g.score)}<span class="pill acc">+${g.xp} XP</span>${g.repeat?'<span class="pill">already graded: no new XP or mastery</span>':''}</div>
      <table style="margin-top:8px"><thead><tr><th>Step</th><th>You</th><th>Expected</th><th></th></tr></thead><tbody>${g.results.map(r=>`<tr><td>${esc(r.prompt)}</td><td class="mono">${r.given==null?'—':r.given}</td><td class="mono">${r.expected}</td><td>${r.ok?'<span style="color:var(--good)">OK</span>':`<span style="color:var(--bad)">X</span> <span class="small dim">${esc(r.hint)}</span>`}</td></tr>`).join('')}</tbody></table>
      <div class="fix" style="margin-top:10px">${esc(g.solution_notes)}</div>
      ${g.solution_table?`<details style="margin-top:8px"><summary class="small">Full cash-flow table</summary><table class="small"><thead><tr>${Object.keys(g.solution_table[0]).map(k=>`<th>${k}</th>`).join('')}</tr></thead><tbody>${g.solution_table.map(r=>`<tr>${Object.values(r).map(v=>`<td class="mono">${v}</td>`).join('')}</tr>`).join('')}</tbody></table></details>`:''}</div>`;
    $('#result').scrollIntoView({behavior:'smooth'});
  };
}

/* ------------------------------------------------------------------ skill graph (replaces skills) */
route('skills', async ([skill]) => {
  const s = await api('/skills');
  const byId = Object.fromEntries(s.skills.map(k=>[k.skill,k]));
  const byArea = {}; s.skills.forEach(k => (byArea[k.area] = byArea[k.area] || []).push(k));
  const rd = s.readiness;
  main.innerHTML = `<h1>Skill graph</h1><p class="sub">States: ${s.states.map(stateChip).join(' ')}. Mastery is recency- and difficulty-weighted evidence with shrinkage; one answer never settles it. Arrows show prerequisites: a weak prerequisite blocks the skills above it.</p>
    <div class="grid cols4" style="margin-bottom:14px"><div class="card"><h3>Readiness</h3><div class="scorebox"><div class="big">${rd.status==='estimate'?rd.estimate.toFixed(1)+'/5':'n/a'}</div>${rd.assessed}/${rd.total} assessed</div></div><div class="card"><h3>Due</h3><div class="scorebox"><div class="big">${s.due.length}</div>skills due for review</div></div><div class="card"><h3>Blocked</h3><div class="scorebox"><div class="big">${s.skills.filter(k=>k.blocked_by.length).length}</div>skills with a weak prerequisite</div></div><div class="card"><h3>Trend</h3><div class="small">${s.longitudinal.weekly_trend.slice(-3).map(w=>`${w.week.slice(5)}: ${Math.round(w.avg*100)}`).join('<br>')||'—'}</div></div></div>
    <div id="skilldetail"></div>
    ${Object.entries(s.areas).map(([a,name]) => `<h2>${esc(name)}</h2><div class="heat">${(byArea[a]||[]).map(k => `<div class="cell ${k.state==='not_assessed'?'na':''}" data-skill="${k.skill}" style="cursor:pointer;border-left:3px solid ${STATE_COLOR[k.mastery_state]}"><b>${esc(k.name)}</b>
      <div class="row small" style="justify-content:space-between">${stateChip(k.mastery_state)}<span class="mono">${k.mastery!=null?k.mastery+'/5':''}${k.n_obs?' · n='+k.n_obs:''}</span></div>
      ${k.state==='assessed'?`<div class="bar ${k.mastery>=3.75?'good':k.mastery>=2.5?'warn':'bad'}" style="margin-top:4px"><i style="width:${k.mastery/5*100}%"></i></div>`:''}
      ${k.prereqs.length?`<div class="dim small" style="margin-top:4px">needs: ${k.prereqs.map(p=>esc(byId[p]?.name||p)).join(', ')}</div>`:''}
      ${k.blocked_by.length?`<div class="small" style="color:var(--warn)">blocked by ${k.blocked_by.map(p=>esc(byId[p]?.name||p)).join(', ')}</div>`:''}
      ${k.prior_hint?`<div class="small" style="color:var(--warn)">flagged in Oct notes</div>`:''}</div>`).join('')}</div>`).join('')}`;
  $$('[data-skill]').forEach(c => c.onclick = () => showSkill(c.dataset.skill, byId));
  if (skill && byId[skill]) showSkill(skill, byId);
});

async function showSkill(skill, byId) {
  const k = byId[skill];
  const [q, d] = await Promise.all([api(`/skills/${skill}/questions`), api(`/skills/${skill}/diagnose`)]);
  const levels = k.levels || {};
  $('#skilldetail').innerHTML = `<div class="card" style="border-color:var(--accent);margin-bottom:14px"><div class="row"><h3 style="margin:0">${esc(k.name)}</h3>${stateChip(k.mastery_state)}<span class="mono">${k.mastery!=null?k.mastery+'/5 · conf '+Math.round(k.confidence*100)+'%':'untested'}</span><span class="spacer"></span><button class="small" onclick="location.hash='#/teach/${skill}'">Teach me why</button><button class="small primary" data-lab="${skill}">Practice</button><button class="small ghost" onclick="document.getElementById('skilldetail').innerHTML=''">close</button></div>
    <div class="grid cols3" style="margin-top:10px">
      <div><h3>By cognitive level</h3>${[1,2,3,4,5].map(l=>{const v=levels[String(l)];return `<div class="row small" style="gap:6px"><span class="muted" style="width:120px">L${l} ${['','definition','mechanics','understanding','application','exceptions'][l]}</span><div class="bar ${v&&v.avg>=0.75?'good':v&&v.avg>=0.5?'warn':'bad'}" style="flex:1"><i style="width:${v&&v.avg!=null?Math.round(v.avg*100):0}%"></i></div><span class="mono dim">${v?`${Math.round(v.avg*100)} (${v.n})`:'—'}</span></div>`;}).join('')}</div>
      <div><h3>Evidence</h3>${q.evidence.length?q.evidence.slice(0,8).map(e=>`<div class="row small"><span class="mono dim" style="width:90px">${new Date(e.when*1000).toLocaleDateString()}</span>${chip(e.score)}<span class="dim">${esc(e.verdict)}</span></div>`).join(''):'<div class="small muted">No answers recorded yet.</div>'}</div>
      <div><h3>Diagnosis</h3><div class="small">${esc(d.advice)}</div>${k.prereqs.length?`<div class="small dim" style="margin-top:6px">Prerequisites: ${k.prereqs.map(p=>`<a href="#/skills/${p}">${esc(byId[p]?.name||p)}</a>`).join(', ')}</div>`:''}${k.dependents.length?`<div class="small dim">Unlocks: ${k.dependents.map(p=>`<a href="#/skills/${p}">${esc(byId[p]?.name||p)}</a>`).join(', ')}</div>`:''}</div></div>
    <details style="margin-top:8px"><summary class="small">${q.questions.length} questions on this skill (authored + guides)</summary><table class="small"><tbody>${q.questions.slice(0,40).map(x=>`<tr><td>${esc(x.text)}</td><td class="mono">L${x.level}</td><td class="dim">${x.origin==='source'?esc(x.citation.short)+' p.'+x.citation.page:'authored'}</td><td class="mono dim">${x.times_asked?`${x.times_asked}× · best ${fmtPct(x.best_score)}`:''}</td></tr>`).join('')}</tbody></table></details></div>`;
  $$('[data-lab]').forEach(b => b.onclick = async () => { const r = await api('/lab/start',{method:'POST',body:{skill: b.dataset.lab}}); navigate('#/session/'+r.session.id); });
  $('#skilldetail').scrollIntoView({behavior:'smooth'});
}
})();
