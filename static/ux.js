/* The Gauntlet 2.0 prep command center: Today, Prepare, Practice, Fix a Weakness, Mock launcher, Progress, Library. */
(() => {
'use strict';
const { route, api, esc, chip, fmtPct, toast, LS, startSession, navigate, main, routes } = window.G;
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
const STATE_COLOR = { untested: 'var(--dim)', learning: 'var(--bad)', developing: 'var(--warn)', proficient: 'var(--info)', mastered: 'var(--good)', review_due: 'var(--accent)' };
const stateChip = st => `<span class="pill" style="color:${STATE_COLOR[st]||'var(--muted)'};border-color:${STATE_COLOR[st]||'var(--line)'}">${esc((st||'untested').replace('_',' '))}</span>`;
const launch = async (mode, config) => { try { const r = await api('/launch', {method:'POST', body:{mode, config}}); navigate('#/session/'+r.session.id); } catch(e) { toast(e.message, true); } };
const startDaily = async () => { try { const r = await api('/daily/start', {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e) { toast(e.message, true); } };
const ago = t => { const d = (Date.now()/1000 - t); return d < 3600 ? `${Math.round(d/60)} min ago` : d < 86400 ? `${Math.round(d/3600)} h ago` : `${Math.round(d/86400)} d ago`; };
const roundName = (rounds, key) => (rounds.find(r=>r.key===key)||{}).name || key || '';
let MODES_CACHE = null;
async function modes() { return MODES_CACHE || (MODES_CACHE = await api('/modes')); }
window.G.launch = launch;

/* ------------------------------------------------------------------ Today */
route('home', () => routes.today());
route('today', async () => {
  const t = await api('/today');
  const rd = t.readiness;
  const ctx = t.next_context;
  const mock = t.mock;
  main.innerHTML = `
    <div class="row" style="align-items:flex-end"><div><h1>Today</h1><p class="sub" style="margin:0">${new Date().toLocaleDateString(undefined,{weekday:'long', month:'long', day:'numeric'})}${ctx ? ` · next: <b>${esc(ctx.bank_name||ctx.bank||'interview')}</b> ${esc(ctx.round||'')}${ctx.days_until!=null?` in ${ctx.days_until} day(s)`:''}` : ''}</p></div><span class="spacer"></span><span class="pill">${esc(t.xp.name)} · ${t.xp.xp} XP</span><span class="pill ${t.daily.completed?'good':'warn'}">Daily ${t.daily.completed?'done':'open'} · streak ${t.daily.streak}</span></div>
    ${t.active_session ? `<div class="card" style="border-color:var(--accent);margin:14px 0"><div class="row"><div><h4 style="margin:0">Unfinished: ${esc(t.active_session.mode_name)}</h4><p>Started ${ago(t.active_session.created)}. Everything is saved; pick up where you left off.</p></div><span class="spacer"></span><button class="primary" onclick="location.hash='#/session/${t.active_session.id}'">Resume session</button><button class="ghost" id="endActive">End it</button></div></div>` : ''}
    <div class="grid cols4" style="margin:16px 0">
      <div class="card click act" data-act="daily"><div class="kicker">1</div><h4>Quick Practice</h4><p>${t.daily.completed ? 'Today’s Draft is done. Run another personalized 10-minute set.' : 'Daily Draft: due reviews, weak skills, untested foundations. 5–10 min.'}</p><div class="cta">${t.daily.completed?'Another set':'Start Daily Draft'} →</div></div>
      <div class="card click act" data-act="prepare"><div class="kicker">2</div><h4>Prepare for an Interview</h4><p>${ctx ? `${esc(ctx.bank_name||ctx.bank||'Interview')} · ${esc(ctx.round||'')}${ctx.days_until!=null?` · ${ctx.days_until} day(s) out`:''}. Plan and recommended sessions ready.` : 'Tell it the bank, round and date; get a plan built from real research and your evidence.'}</p><div class="cta">${ctx?'Continue plan':'Create a plan'} →</div></div>
      <div class="card click act" data-act="fix"><div class="kicker">3</div><h4>Fix a Weakness</h4><p>${t.top_weakness ? `Top weakness: <b>${esc(t.top_weakness.name)}</b> (${t.top_weakness.mastery}/5). Teach, practice, pressure-test or re-test.` : 'Search any skill or concept; diagnose the root cause and fix it.'}</p><div class="cta">${t.top_weakness?'Fix '+esc(t.top_weakness.name.split(' ')[0]):'Pick a skill'} →</div></div>
      <div class="card click act" data-act="mock"><div class="kicker">4</div><h4>Run a Full Mock</h4><p>${mock.source==='context' ? `Defaults from your ${esc(mock.context.bank_name||'upcoming')} prep: ${mock.config.duration_min} min, ${esc(mock.config.persona)}, scores hidden.` : mock.source==='last' ? `Last setup: ${mock.config.duration_min} min, ${esc(mock.config.persona)}${mock.config.bank?', '+esc(mock.config.bank):''}.` : 'Realistic Superday, 30 min, VP persona, scores hidden. Customize if you want.'}</p><div class="cta">Start mock →</div></div>
    </div>
    <div class="grid cols2">
      <div class="card"><h3>Focus queue</h3>${t.queue.length ? t.queue.map(q=>`<div class="row qrow" style="margin:6px 0;padding:8px 0;border-bottom:1px solid var(--line)"><span class="pill ${q.kind==='resume'?'acc':q.kind==='review'?'warn':q.kind==='weak'?'bad':q.kind==='context'?'info':''}">${esc(q.kind)}</span><div style="flex:1"><div style="font-weight:500">${esc(q.title)}</div><div class="small muted">${esc(q.detail)}</div></div><button class="small" data-q='${JSON.stringify(q.action).replace(/'/g,"&#39;")}'>Go</button></div>`).join('') : '<p class="muted small">Nothing queued. Run a Quick Practice to generate evidence.</p>'}</div>
      <div class="card"><h3>Where you stand</h3>
        <div class="kv" style="margin-bottom:8px"><div>Readiness</div><div>${rd.status==='estimate' ? `<b>${rd.estimate.toFixed(1)}/5</b> · confidence ${Math.round(rd.confidence*100)}% · coverage ${Math.round(rd.coverage*100)}%` : `<b>Not enough data</b> · ${rd.assessed}/${rd.total} technical skills assessed`}</div>
          <div>Top weakness</div><div>${t.top_weakness ? `${esc(t.top_weakness.name)} ${stateChip(t.top_weakness.mastery_state)} ${t.top_weakness.mastery}/5` : '—'}</div>
          <div>Last session</div><div>${t.last_session ? `${esc(t.last_session.mode_name)} · ${chip(t.last_session.avg)} over ${t.last_session.n} answers · <a href="#/debrief/${t.last_session.id}">debrief</a>` : '—'}</div></div>
        ${t.trend.length ? `<div class="small muted" style="margin-top:6px">Weekly trend</div>${t.trend.map(w=>`<div class="row small" style="gap:8px"><span class="mono muted" style="width:60px">${w.week.slice(5)}</span><div class="bar ${w.avg>=0.75?'good':w.avg>=0.5?'warn':'bad'}" style="flex:1"><i style="width:${Math.round(w.avg*100)}%"></i></div><span class="mono">${Math.round(w.avg*100)} <span class="dim">(${w.n})</span></span></div>`).join('')}` : ''}
        <div class="row" style="margin-top:10px"><a class="small" href="#/progress">Full progress →</a><span class="spacer"></span><a class="small muted" href="#/career">Career mode</a></div></div>
    </div>
    ${t.recent_misses.length ? `<div class="card" style="margin-top:14px"><h3>Recently missed</h3><div class="row">${t.recent_misses.map(m=>`<button class="small ghost" onclick="location.hash='#/fix/${m.skill}'" title="${esc(m.key||'')}">${esc(m.name)} · ${Math.round(m.score*100)}</button>`).join('')}</div></div>` : ''}`;
  $$('.act').forEach(c => c.onclick = () => { const a = c.dataset.act; if (a==='daily') return startDaily(); if (a==='prepare') return navigate(ctx ? '#/prepare/'+ctx.id : '#/prepare'); if (a==='fix') return navigate(t.top_weakness ? '#/fix/'+t.top_weakness.skill : '#/fix'); if (a==='mock') return navigate('#/mock'); });
  $$('[data-q]').forEach(b => b.onclick = () => doAction(JSON.parse(b.dataset.q)));
  const ea = $('#endActive'); if (ea) ea.onclick = async () => { await api(`/sessions/${t.active_session.id}/end`, {method:'POST'}); window.G.render(); };
});
function doAction(a) { if (a.type==='session') navigate('#/session/'+a.id); else if (a.type==='daily') startDaily(); else if (a.type==='fix') navigate('#/fix/'+a.skill); else if (a.type==='prepare') navigate('#/prepare/'+a.id); }

/* ------------------------------------------------------------------ Prepare */
route('prepare', async ([cid]) => {
  const data = await api('/prep/contexts');
  const banksList = await api('/banks');
  const skillsList = (await api('/skills')).skills.filter(s=>!['behavioral','resume','deal'].includes(s.area));
  const ctx = cid ? data.contexts.find(c=>c.id===cid) || await api('/prep/contexts').then(()=>null) : null;
  if (cid && !ctx) { toast('That prep plan was not found.', true); navigate('#/prepare'); return; }
  const form = (c) => `<div class="grid cols3">
      <div><label>Bank</label><select id="p_bank"><option value="">— generalist / unknown —</option>${banksList.map(b=>`<option value="${b.slug}" ${c&&c.bank===b.slug?'selected':''}>${esc(b.name)}${b.has_research?'':' (no research)'}</option>`).join('')}</select>
        <label>Group / coverage</label><select id="p_sector"><option value="">Generalist</option>${['healthcare','energy','power','fig','m&a','tmt','industrials','consumer'].map(s=>`<option ${c&&c.sector===s?'selected':''}>${s}</option>`).join('')}</select></div>
      <div><label>Round</label><select id="p_round">${data.rounds.map(r=>`<option value="${r.key}" ${c&&c.round===r.key?'selected':(!c&&r.key==='first_round'?'selected':'')}>${esc(r.name)} · ${r.minutes}m</option>`).join('')}</select>
        <label>Date (if known)</label><input id="p_date" type="date" value="${c&&c.date?c.date:''}"></div>
      <div><label>Interviewer tone</label><select id="p_persona"><option value="">Round default</option>${['analyst','associate','vp','md'].map(p=>`<option ${c&&c.persona===p?'selected':''}>${p}</option>`).join('')}</select>
        <label>Technical share <span id="p_twv" class="dim">${c&&c.technical_weight!=null?Math.round(c.technical_weight*100)+'%':'round default'}</span></label><input id="p_tw" type="range" min="10" max="100" value="${c&&c.technical_weight!=null?Math.round(c.technical_weight*100):65}" oninput="document.getElementById('p_twv').textContent=this.value+'%'"></div>
      <div style="grid-column:span 2"><label>Emphasize these skills (optional)</label><select id="p_emph" multiple size="5">${skillsList.map(s=>`<option value="${s.skill}" ${c&&c.emphasis.includes(s.skill)?'selected':''}>${esc(s.name)}</option>`).join('')}</select><div class="hint">Cmd-click to select several.</div></div>
      <div><label>Notes / research</label><textarea id="p_notes" style="min-height:120px" placeholder="People you spoke with, what they said to expect, deals to read up on…">${c?esc(c.notes||''):''}</textarea>
        <label style="text-transform:none;letter-spacing:0"><input type="checkbox" id="p_health" style="width:auto;margin-right:6px" ${c&&c.include_health_story?'checked':''}>Allow the sensitive health story in this prep</label></div>
    </div>`;
  if (!ctx) {
    main.innerHTML = `<h1>Prepare for an interview</h1><p class="sub">Describe the interview once. The app turns it into a plan from your evidence, BankVault research and your resume, and remembers it as the default for mocks.</p>
      ${data.contexts.length ? `<h2>Your plans</h2><div class="grid cols3">${data.contexts.map(c=>`<div class="card click" onclick="location.hash='#/prepare/${c.id}'"><h4>${esc(c.bank_name||c.bank||'Generalist')} <span class="pill">${esc(roundName(data.rounds,c.round))}</span></h4><p>${c.sector?esc(c.sector)+' · ':''}${c.date?`${c.date} (${c.days_until} day(s))`:'undated'}${c.last_used?' · last used '+ago(c.last_used):''}</p></div>`).join('')}</div>` : ''}
      <h2>New plan</h2><div class="card">${form(null)}<div class="row" style="margin-top:12px"><button class="primary" id="p_save">Create plan</button></div></div>`;
    $('#p_save').onclick = async () => { const c = await api('/prep/contexts', {method:'POST', body: readForm()}); navigate('#/prepare/'+c.id); };
    return;
  }
  const plan = await api(`/prep/contexts/${ctx.id}/plan`);
  main.innerHTML = `<div class="row"><div><h1>${esc(ctx.bank_name||ctx.bank||'Generalist interview')} <span class="pill acc">${esc(plan.round.name)}</span>${ctx.sector?`<span class="pill">${esc(ctx.sector)}</span>`:''}</h1><p class="sub" style="margin:0">${ctx.date?`${ctx.date} · ${ctx.days_until} day(s) away`:'No date set'} · ${esc(ctx.persona||plan.round.persona)} persona · ${Math.round((ctx.technical_weight!=null?ctx.technical_weight:plan.round.technical_weight)*100)}% technical</p></div><span class="spacer"></span><button class="ghost small" id="p_custom">Customize</button><button class="ghost small danger" id="p_arch">Archive</button></div>
    <div class="grid cols3" style="margin:14px 0">${plan.options.map(o=>`<div class="card ${o.key==='mix25'?'':''}" style="${o.key==='mix25'?'border-color:var(--accent)':''}"><h4>${esc(o.label)}</h4><p>${esc(o.desc)}</p><div style="margin-top:8px"><button class="${o.key==='mix25'?'primary':''}" data-opt="${o.key}">Start ${o.key==='mix25'?'recommended ':''}${o.minutes}-min</button></div></div>`).join('')}</div>
    <div id="customize" class="card hidden" style="margin-bottom:14px">${form(ctx)}<div class="row" style="margin-top:12px"><button class="primary" id="p_save">Save changes</button><button class="ghost" onclick="document.getElementById('customize').classList.add('hidden')">Cancel</button></div></div>
    <div class="grid cols2">
      <div class="card"><h3>Technical areas to prepare</h3>${plan.technical.map(t=>`<div class="row small" style="margin:4px 0"><span style="flex:1"><b>${esc(t.name)}</b> <span class="dim">${esc(t.why)}</span></span>${stateChip(t.state)}<button class="small ghost" onclick="location.hash='#/fix/${t.skill}'">fix</button></div>`).join('')||'<p class="muted small">Nothing flagged.</p>'}</div>
      <div class="card"><h3>Bank and group angles</h3>${plan.bank_angles.length ? plan.bank_angles.map(a=>`<div class="small" style="margin:6px 0"><span class="pill ${a.kind==='deal'?'info':a.kind==='your_notes'?'acc':''}">${esc(a.kind.replace('_',' '))}</span> ${esc(a.text)}${a.verification?` <span class="pill ${a.verification==='verified'?'good':'warn'}">${a.verification}</span>`:''}</div>`).join('') : '<p class="muted small">No bank selected or no BankVault research for it; firm questions stay generic.</p>'}${ctx.notes?`<div class="small" style="margin-top:8px"><b>Your notes:</b> ${esc(ctx.notes)}</div>`:''}</div>
      <div class="card"><h3>Behavioral to pressure-test</h3>${plan.behavioral.skills.map(s=>`<div class="small">· ${esc(s.name)} <button class="small ghost" onclick="G.launch('behavioral',{behavioral_category:null,max_questions:4,duration_min:12,focus_skills:['${s.skill}']})">drill</button></div>`).join('')||'<div class="small muted">Why-IB / why-bank / TMAY look solid on evidence.</div>'}<div class="small muted" style="margin-top:6px">Stories on file: ${plan.behavioral.stories.map(s=>esc(s.title)).join(' · ')||'none verified'}</div></div>
      <div class="card"><h3>Resume bullets to defend</h3>${plan.resume_bullets.map(b=>`<div class="small" style="margin:4px 0">· <b>${esc(b.org)}</b>: ${esc(b.text)}${b.open_unknowns?` <span class="pill warn">${b.open_unknowns} fact(s) to fill</span>`:''}${b.discrepancies?` <span class="pill bad">${b.discrepancies} discrepancy</span>`:''}</div>`).join('')}<div class="row" style="margin-top:8px"><button class="small" onclick="location.hash='#/resume'">Fill in facts</button><button class="small ghost" onclick="G.launch('resume_defense',{persona:'vp',duration_min:15,context_id:'${ctx.id}'})">Drill resume</button></div></div>
      <div class="card"><h3>Deal and market discussion</h3>${plan.deal_defense.map(d=>`<div class="small">· ${esc(d.text)}</div>`).join('')}<div style="margin-top:8px"><button class="small ghost" onclick="G.launch('deal_defense',{duration_min:15,context_id:'${ctx.id}'})">Deal defense session</button></div></div>
    </div>`;
  $$('[data-opt]').forEach(b => b.onclick = async () => { b.disabled = true; try { const r = await api(`/prep/contexts/${ctx.id}/start/${b.dataset.opt}`, {method:'POST'}); navigate('#/session/'+r.session.id); } catch(e) { toast(e.message, true); b.disabled = false; } });
  $('#p_custom').onclick = () => $('#customize').classList.toggle('hidden');
  $('#p_save').onclick = async () => { await api(`/prep/contexts/${ctx.id}`, {method:'PUT', body: readForm()}); window.G.render(); };
  $('#p_arch').onclick = async () => { if (!confirm('Archive this prep plan?')) return; await api(`/prep/contexts/${ctx.id}`, {method:'DELETE'}); navigate('#/prepare'); };
});
function readForm() { return { bank: $('#p_bank').value || null, sector: $('#p_sector').value || null, round: $('#p_round').value, date: $('#p_date').value || null, persona: $('#p_persona').value || null, technical_weight: +$('#p_tw').value/100, emphasis: $$('#p_emph option:checked').map(o=>o.value), notes: $('#p_notes').value, include_health_story: $('#p_health').checked }; }

/* ------------------------------------------------------------------ Fix a weakness */
route('fix', async ([skill]) => {
  const q = new URLSearchParams(location.hash.split('?')[1] || '').get('q') || '';
  const data = await api('/weakness/search?q=' + encodeURIComponent(q));
  main.innerHTML = `<h1>Fix a weakness</h1><p class="sub">Pick what is broken; the app shows why it is weak, the prerequisite underneath it, and the right way to fix it.</p>
    <div class="row"><input id="fx_q" placeholder="Search a skill, concept or question (WACC, deferred taxes, accretion, terminal value…)" style="max-width:520px" value="${esc(q)}"><button id="fx_go">Search</button></div>
    <div id="fx_detail" style="margin:14px 0"></div>
    <div class="grid cols2">
      <div class="card"><h3>Recommended from your evidence</h3>${data.recommended.length ? data.recommended.map(w=>`<div class="row small" style="margin:4px 0"><span style="flex:1">${esc(w.name)}</span>${stateChip(w.mastery_state)}<span class="mono">${w.mastery}/5 · n=${w.n_obs}</span><button class="small" onclick="location.hash='#/fix/${w.skill}'">Open</button></div>`).join('') : '<p class="muted small">No weaknesses assessed yet.</p>'}</div>
      <div class="card"><h3>Recently missed</h3>${data.recent.length ? data.recent.map(m=>`<div class="row small" style="margin:4px 0"><span style="flex:1"><b>${esc(m.name)}</b><br><span class="dim">${esc((m.key||'').slice(0,110))}</span></span>${chip(m.score)}<button class="small" onclick="location.hash='#/fix/${m.skill}'">Open</button></div>`).join('') : '<p class="muted small">No misses recorded yet.</p>'}</div>
    </div>
    ${q ? `<h2>Results for “${esc(q)}”</h2><div class="card">${data.results.length ? data.results.map(r=>`<div class="row small" style="margin:4px 0"><span style="flex:1"><b>${esc(r.name)}</b> <span class="dim">${esc(r.match)}</span></span>${stateChip(r.state)}<button class="small" onclick="location.hash='#/fix/${r.skill}'">Open</button></div>`).join('') : '<p class="muted small">No match.</p>'}</div>` : ''}`;
  const go = () => navigate('#/fix?q=' + encodeURIComponent($('#fx_q').value.trim()));
  $('#fx_go').onclick = go; $('#fx_q').onkeydown = e => { if (e.key === 'Enter') go(); };
  if (skill && !skill.includes('?')) showFix(skill);
});
async function showFix(skill) {
  let d; try { d = await api(`/weakness/${skill}`); } catch(e) { toast('Unknown skill', true); return; }
  $('#fx_detail').innerHTML = `<div class="card" style="border-color:var(--accent)"><div class="row"><h3 style="margin:0">${esc(d.name)}</h3>${stateChip(d.state)}<span class="mono">${d.mastery!=null?d.mastery+'/5 · n='+d.n_obs:'no evidence'}</span><span class="spacer"></span><span class="pill">~${d.minutes} min</span></div>
    <div class="grid cols2" style="margin-top:10px">
      <div><div class="small"><b>Why it is weak:</b> ${esc(d.why)}</div><div class="small" style="margin-top:6px"><b>Root cause:</b> ${d.root_cause!==skill?`<a href="#/fix/${d.root_cause}">${esc(d.root_name)}</a>`:'this skill itself'}${d.weakest_level?` · breaks at level ${d.weakest_level} (${['','definition','mechanics','understanding','application','exceptions'][d.weakest_level]})`:''}</div><div class="small dim" style="margin-top:4px">${esc(d.advice)}</div>
        ${d.weak_prerequisites.length?`<div class="small" style="margin-top:6px;color:var(--warn)">Weak prerequisites: ${d.weak_prerequisites.map(p=>`<a href="#/fix/${p.skill}">${esc(p.name)}</a>`).join(', ')}</div>`:''}</div>
      <div><div class="small muted">Recent evidence</div>${d.evidence.length ? d.evidence.slice(0,6).map(e=>`<div class="row small"><span class="mono dim" style="width:90px">${new Date(e.when*1000).toLocaleDateString()}</span>${chip(e.score)}<span class="dim" style="flex:1">${esc((e.key||e.verdict||'').slice(0,80))}</span><a class="small" href="#/debrief/${e.session_id}">debrief</a></div>`).join('') : '<div class="small muted">None yet.</div>'}</div></div>
    <div class="grid cols4" style="margin-top:12px">${d.actions.map(a=>`<div class="card click" data-act="${a.key}"><h4>${esc(a.label)}</h4><p>${esc(a.desc)}</p></div>`).join('')}</div></div>`;
  $$('#fx_detail [data-act]').forEach(c => c.onclick = () => { const a = d.actions.find(x=>x.key===c.dataset.act); if (a.route) navigate(a.route); else launch(a.mode, a.config); });
  $('#fx_detail').scrollIntoView({behavior:'smooth', block:'start'});
}

/* ------------------------------------------------------------------ Full mock launcher */
route('mock', async () => {
  const d = await api('/mock/defaults');
  const [personas, banksList] = await Promise.all([api('/personas'), api('/banks')]);
  const cfg = d.config;
  const summary = () => `<div class="kv"><div>Format</div><div>${d.mode==='bank_specific'?'Bank-specific interview':'Realistic Superday'} · ${cfg.duration_min} min</div><div>Interviewer</div><div>${esc(personas.find(p=>p.key===cfg.persona)?.name||cfg.persona)}</div><div>Bank / context</div><div>${cfg.bank?esc(banksList.find(b=>b.slug===cfg.bank)?.name||cfg.bank)+(cfg.sector?' · '+esc(cfg.sector):''):'none (generalist)'}${d.context?` · from plan “${esc(d.context.bank_name||'')} ${esc(d.context.round||'')}”`:d.source==='last'?' · your last setup':''}</div><div>Mix</div><div>${Math.round((cfg.technical_weight||0.7)*100)}% technical · resume questions ${cfg.resume_questions===false?'off':'on'}</div><div>Input</div><div>Voice (hands-free ${LS.get('handsFree',true)?'on':'off'}) or text</div><div>Scores</div><div>Hidden until the debrief</div></div>`;
  main.innerHTML = `<h1>Run a full mock</h1><p class="sub">One click. Defaults come from your upcoming prep plan, else your last setup.</p>
    <div class="card" style="border-color:var(--accent)">${summary()}<div class="row" style="margin-top:14px"><button class="primary" id="m_start" style="font-size:16px;padding:12px 22px">Start mock</button><button class="ghost" id="m_custom">Customize</button>${d.context?`<a class="small" href="#/prepare/${d.context.id}">Edit the prep plan</a>`:'<a class="small" href="#/prepare">Create a prep plan</a>'}</div></div>
    <div id="m_panel" class="card hidden" style="margin-top:12px"><div class="grid cols3">
      <div><label>Bank</label><select id="m_bank"><option value="">none</option>${banksList.map(b=>`<option value="${b.slug}" ${cfg.bank===b.slug?'selected':''}>${esc(b.name)}</option>`).join('')}</select><label>Sector</label><select id="m_sector"><option value="">Generalist</option>${['healthcare','energy','power','fig','m&a','tmt','industrials'].map(s=>`<option ${cfg.sector===s?'selected':''}>${s}</option>`).join('')}</select></div>
      <div><label>Interviewer</label><select id="m_persona">${personas.filter(p=>p.key!=='hot_seat').map(p=>`<option value="${p.key}" ${cfg.persona===p.key?'selected':''}>${esc(p.name)}</option>`).join('')}</select><label>Duration</label><select id="m_dur">${[15,20,30,45,60].map(x=>`<option ${cfg.duration_min==x?'selected':''}>${x}</option>`).join('')}</select></div>
      <div><label>Difficulty</label><select id="m_diff">${['easy','medium','hard','brutal'].map(x=>`<option ${cfg.difficulty===x?'selected':''}>${x}</option>`).join('')}</select><label>Technical share <span id="m_twv" class="dim">${Math.round((cfg.technical_weight||0.7)*100)}%</span></label><input id="m_tw" type="range" min="10" max="100" value="${Math.round((cfg.technical_weight||0.7)*100)}" oninput="document.getElementById('m_twv').textContent=this.value+'%'"><label style="text-transform:none;letter-spacing:0"><input type="checkbox" id="m_resume" style="width:auto;margin-right:6px" ${cfg.resume_questions===false?'':'checked'}>Resume questions</label></div>
    </div></div>`;
  $('#m_custom').onclick = () => $('#m_panel').classList.toggle('hidden');
  $('#m_start').onclick = async () => {
    const c = {...cfg};
    if (!$('#m_panel').classList.contains('hidden')) { c.bank = $('#m_bank').value || null; c.sector = $('#m_sector').value || null; c.persona = $('#m_persona').value; c.duration_min = +$('#m_dur').value; c.difficulty = $('#m_diff').value; c.technical_weight = +$('#m_tw').value/100; c.resume_questions = $('#m_resume').checked; }
    const mode = c.bank ? 'bank_specific' : 'superday';
    $('#m_start').disabled = true;
    await launch(mode, c);
  };
});

/* ------------------------------------------------------------------ Practice (all modes by intent) */
route('practice', async () => {
  const ms = await modes();
  const groups = [['quick','Quick and adaptive','Short, no setup, live scores.'],['full','Full simulations','Realistic formats; most hide scores until the end.'],['targeted','Targeted improvement','Learning modes with instant feedback.'],['pressure','Pressure and challenge','Stakes, depth, and campaigns.']];
  main.innerHTML = `<h1>Practice</h1><p class="sub">Every format, grouped by why you would use it. The four actions on Today cover most days; these are the rest.</p>
    ${groups.map(([g,name,desc])=>`<h2>${name} <span class="muted small" style="font-weight:400">${desc}</span></h2><div class="grid cols3">${ms.filter(m=>m.meta.group===g).map(m=>`<div class="card click" data-mode="${m.key}"><div class="row"><h4 style="margin:0">${esc(m.name)}</h4><span class="spacer"></span><span class="pill ${m.meta.scores==='hidden'?'warn':'good'}">${m.meta.scores==='hidden'?'scores hidden':'live scores'}</span></div><p style="margin:6px 0">${esc(m.desc)}</p><div class="small dim"><b>When:</b> ${esc(m.meta.when||'')}</div><div class="small dim"><b>Improves:</b> ${esc(m.meta.improves||'')}</div><div class="row small" style="margin-top:6px"><span class="pill">${esc(m.meta.minutes||'')} min</span><span class="pill">${esc(m.meta.voice||'both')}</span></div></div>`).join('')}</div>`).join('')}
    <h2>Modeling Lab <span class="muted small" style="font-weight:400">Arithmetic under pressure and written models.</span></h2><div class="grid cols3"><div class="card click" onclick="location.hash='#/modeling'"><h4>Mental Math Arena</h4><p>Voice-first numeric drill, no calculator.</p><div class="row small"><span class="pill">5–10 min</span><span class="pill">voice-first</span><span class="pill good">live scores</span></div></div><div class="card click" onclick="location.hash='#/modeling'"><h4>Written challenges</h4><p>Mini DCF, accretion/dilution, sources & uses, paper LBO; every step graded.</p><div class="row small"><span class="pill">8–12 min</span><span class="pill">text</span><span class="pill good">live scores</span></div></div></div>
    <div id="setup"></div>`;
  $$('[data-mode]').forEach(c => c.onclick = () => { const k = c.dataset.mode; if (k==='daily') return startDaily(); if (k==='deathmatch') return api('/deathmatch/start',{method:'POST',body:{}}).then(r=>navigate('#/session/'+r.session.id)); if (k==='career') return navigate('#/career'); if (k==='weakness_lab') return navigate('#/lab'); if (k==='superday'||k==='bank_specific') return navigate('#/mock'); window.G.showSetup(k, ms.find(m=>m.key===k)); });
});

/* ------------------------------------------------------------------ Progress (skill graph + history) and Library */
function tabBar(title, base, tabs, active) {
  return `<div class="row" style="margin-bottom:6px"><h1 style="margin:0">${title}</h1><span class="spacer"></span><div class="row">${tabs.map(([k,n])=>`<a class="btn-tab ${active===k?'active':''}" href="#/${base}/${k}">${n}</a>`).join('')}</div></div>`;
}
async function withTabs(title, base, tabs, active, fn, args) {
  await fn(args || []);                       // the existing screen renders and binds its handlers
  const h1 = main.querySelector('h1'); if (h1) h1.remove();   // replace its title with the tab bar
  main.insertAdjacentHTML('afterbegin', tabBar(title, base, tabs, active));
}
const PROGRESS_TABS = [['skills','Skill graph'],['history','History'],['game','Career & records']];
route('progress', async ([tab]) => {
  tab = tab || 'skills';
  const fn = tab === 'history' ? routes.history : tab === 'game' ? routes.career : routes.skills;
  await withTabs('Progress', 'progress', PROGRESS_TABS, tab, fn, []);
});
const LIBRARY_TABS = [['bank','Question bank'],['resume','Resume defense'],['sources','Sources'],['profile','Profile & KB']];
route('library', async ([tab]) => {
  tab = tab || 'bank';
  if (tab === 'sources') {
    const s = await api('/sources');
    main.innerHTML = tabBar('Library', 'library', LIBRARY_TABS, tab) + `<div class="card"><h3>Ingested guides (local only)</h3>${Object.entries(s.report.sources||{}).map(([k,v])=>`<div class="small">· <b>${esc(v.short||k)}</b>: ${v.records||0} records from ${esc((v.path||'').split('/').pop())}</div>`).join('')}<div class="small muted" style="margin-top:6px">${s.core_records} core technical records with page citations. Excerpts go to the model only when the disclosed setting is on (currently ${s.send_guide_excerpts?'on':'off'}).</div></div>`;
    return;
  }
  const fn = tab === 'resume' ? routes.resume : tab === 'profile' ? routes.profile : routes.bank;
  await withTabs('Library', 'library', LIBRARY_TABS, tab, fn, []);
});
})();
