'use strict';
/* Núcleo: utilitários, API, componentes de UI, shell, roteador. */
const S = { user: null, csrf: null, brand: {}, settings: {}, timers: [] };
const R = {};            // rotas: R[path] = {title, roles, render(view, query)}
const ACT = {};          // ações de clique: ACT[nome](elemento, evento)
const NAV = [];          // itens do menu

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const brl = c => (c == null ? '—' : (c / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }));
const num = (n, d = 3) => n == null ? '—' : Number(n).toLocaleString('pt-BR', { maximumFractionDigits: d });
const pct = n => n == null ? '—' : Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';
const fmtDate = s => s ? s.slice(0, 10).split('-').reverse().join('/') : '—';
const fmtDT = s => s ? fmtDate(s) + ' ' + s.slice(11, 16) : '—';
const pad = n => String(n).padStart(2, '0');
const isoDate = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const today = () => isoDate(new Date());
const monthStart = () => today().slice(0, 8) + '01';
const monthName = m => { const [y, mo] = m.split('-'); return new Date(+y, +mo - 1, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' }); };
const moneyIn = c => c == null ? '' : (c / 100).toFixed(2).replace('.', ',');
const parseMoney = v => {
  if (typeof v === 'number') return Math.round(v * 100);
  let s = String(v ?? '').replace(/[^\d,.-]/g, '').trim();
  if (!s) return 0;
  if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
  const n = parseFloat(s);
  return isNaN(n) ? 0 : Math.round(n * 100);
};
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : 'k' + Date.now() + Math.random().toString(16).slice(2));
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const first = n => (n || '').split(' ')[0];
const initials = n => (n || '?').split(' ').filter(Boolean).slice(0, 2).map(x => x[0]).join('').toUpperCase();

const ICONS = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  plus: '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
  cart: '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 7H6"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
  box: '<path d="M21 8l-9-5-9 5v8l9 5 9-5V8z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.8.6 3.1 2.3 3.5 5.2"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4 4-6 8-6s7.2 2 8 6"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
  percent: '<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>',
  dollar: '<path d="M12 2v20M17 6.5C16 5 14.3 4.2 12 4.2c-3 0-4.8 1.4-4.8 3.4 0 4.8 9.8 2.2 9.8 7 0 2.1-2 3.6-5 3.6-2.5 0-4.4-.9-5.4-2.6"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/>',
  bars: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  drop: '<path d="M12 2.5S5 11 5 15.5a7 7 0 0 0 14 0C19 11 12 2.5 12 2.5z"/>',
  print: '<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="7"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  alert: '<path d="M12 3l10 18H2L12 3z"/><path d="M12 10v5M12 18v.5"/>',
  check: '<path d="M4 12l5 5L20 6"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>',
  camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M10.8 12.2L20 3M16 7l3 3"/>',
  wallet: '<path d="M20 7H5a2 2 0 0 1 0-4h13v4zM3 5v14a2 2 0 0 0 2 2h15V7"/><circle cx="16.5" cy="14" r="1.2"/>',
  trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
  tag: '<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><circle cx="7" cy="7" r="1.3"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
};
const ic = (n, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;

/* ---------- API ---------- */
class ApiErr extends Error { constructor(m, status, field) { super(m); this.status = status; this.field = field; } }
async function api(method, url, body) {
  const o = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
  if (method !== 'GET') { o.headers['Content-Type'] = 'application/json'; o.headers['X-CSRF-Token'] = S.csrf; o.body = JSON.stringify(body || {}); }
  let r;
  try { r = await fetch(url, o); } catch (e) { throw new ApiErr('Sem conexão com o servidor. Verifique a internet e tente novamente.', 0); }
  let d = null; try { d = await r.json(); } catch (e) { /* sem corpo */ }
  if (!r.ok) {
    if (r.status === 401 && S.user) { S.user = null; showLogin('Sua sessão expirou. Entre novamente.'); }
    throw new ApiErr(d?.error || `Erro ${r.status}`, r.status, d?.field);
  }
  return d;
}
const qs = p => { const u = new URLSearchParams(); Object.entries(p || {}).forEach(([k, v]) => { if (v !== '' && v != null) u.set(k, v); }); const s = u.toString(); return s ? '?' + s : ''; };
const GET = (u, p) => api('GET', u + qs(p));
const POST = (u, b) => api('POST', u, b);
const PUT = (u, b) => api('PUT', u, b);
const DEL = u => api('DELETE', u);

/* ---------- UI ---------- */
function toast(msg, type = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + type; t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), type === 'bad' ? 7000 : 4000);
}
const fail = e => toast(e.message || String(e), 'bad');

const modals = [];
function modal({ title, body, footer = '', size = '', dismissable = true, onClose }) {
  const ov = document.createElement('div'); ov.className = 'ov';
  ov.innerHTML = `<div class="modal ${size}" role="dialog" aria-modal="true"><header><h2>${esc(title)}</h2>${dismissable ? `<button class="x" data-close aria-label="Fechar">${ic('x')}</button>` : ''}</header><div class="bd">${body}</div>${footer ? `<footer>${footer}</footer>` : ''}</div>`;
  document.body.appendChild(ov);
  ov.close = () => { const i = modals.indexOf(ov); if (i >= 0) modals.splice(i, 1); ov.remove(); onClose && onClose(); };
  ov.dismissable = dismissable;
  ov.addEventListener('mousedown', e => { if (e.target === ov && dismissable) ov.close(); });
  $$('[data-close]', ov).forEach(b => b.addEventListener('click', ov.close));
  modals.push(ov);
  const f = $('input:not([type=hidden]),select,textarea', ov); if (f && !matchMedia('(pointer:coarse)').matches) f.focus();
  return ov;
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && modals.length) { const m = modals[modals.length - 1]; if (m.dismissable) m.close(); } });
const closeAllModals = () => [...modals].forEach(m => m.close());

function confirmBox(msg, { title = 'Confirmar', ok = 'Confirmar', danger = false } = {}) {
  return new Promise(res => {
    const m = modal({ title, body: `<p>${esc(msg)}</p>`, footer: `<button class="btn" data-close>Cancelar</button><button class="btn ${danger ? 'd' : 'p'}" data-ok>${esc(ok)}</button>`, onClose: () => res(false) });
    $('[data-ok]', m).onclick = () => { res(true); m.onClose = null; m.close(); };
  });
}

function fieldHTML(f, val) {
  const id = 'f_' + f.name, v = val ?? f.value ?? '';
  const req = f.required ? ' <span class="bad">*</span>' : '';
  let input;
  if (f.type === 'select') {
    input = `<select id="${id}" name="${f.name}" ${f.int ? 'data-int' : ''} ${f.attrs || ''}>${(f.options || []).map(o => `<option value="${esc(o.v)}" ${String(o.v) === String(v) ? 'selected' : ''}>${esc(o.l)}</option>`).join('')}</select>`;
  } else if (f.type === 'textarea') {
    input = `<textarea id="${id}" name="${f.name}" rows="${f.rows || 3}" maxlength="${f.max || 1000}" ${f.attrs || ''}>${esc(v)}</textarea>`;
  } else if (f.type === 'checkbox') {
    return `<div class="field ${f.full ? 'full' : ''}"><label class="chk"><input type="checkbox" id="${id}" name="${f.name}" ${v === 1 || v === true || v === '1' ? 'checked' : ''}> ${esc(f.label)}</label>${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ''}</div>`;
  } else if (f.type === 'money') {
    input = `<input id="${id}" name="${f.name}" data-money inputmode="decimal" autocomplete="off" value="${v === '' || v == null ? '' : moneyIn(v)}" placeholder="0,00" ${f.attrs || ''}>`;
  } else {
    input = `<input id="${id}" name="${f.name}" type="${f.type || 'text'}" value="${esc(v)}" ${f.type === 'number' ? `step="${f.step || 'any'}" min="${f.min ?? ''}" inputmode="decimal"` : ''} ${f.max ? `maxlength="${f.max}"` : ''} ${f.ph ? `placeholder="${esc(f.ph)}"` : ''} ${f.attrs || ''} ${f.type === 'password' ? 'autocomplete="new-password"' : ''}>`;
  }
  return `<div class="field ${f.full ? 'full' : ''}"><label for="${id}">${esc(f.label)}${req}</label>${input}${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ''}<span class="ferr" data-err="${f.name}"></span></div>`;
}
function formValues(form) {
  const o = {};
  $$('[name]', form).forEach(el => {
    if (el.type === 'checkbox') o[el.name] = el.checked ? 1 : 0;
    else if (el.hasAttribute('data-money')) o[el.name] = parseMoney(el.value);
    else if (el.type === 'number') o[el.name] = el.value === '' ? null : Number(el.value);
    else if (el.hasAttribute('data-int')) o[el.name] = el.value === '' ? null : parseInt(el.value, 10);
    else o[el.name] = el.value.trim();
  });
  return o;
}
function showFieldError(form, e) {
  $$('.err', form).forEach(x => x.classList.remove('err')); $$('[data-err]', form).forEach(x => x.textContent = '');
  if (e.field) { const el = $(`[name="${e.field}"]`, form), er = $(`[data-err="${e.field}"]`, form); if (el) { el.classList.add('err'); el.focus(); } if (er) { er.textContent = e.message; return true; } }
  return false;
}
document.addEventListener('focusout', e => { if (e.target.matches && e.target.matches('[data-money]') && e.target.value.trim()) e.target.value = moneyIn(parseMoney(e.target.value)); });

function formModal({ title, fields, values = {}, submit = 'Salvar', size = '', onSubmit, before = '', after = '', dismissable = true }) {
  const fid = 'form_' + Math.random().toString(36).slice(2);
  const m = modal({
    title, size, dismissable,
    body: `${before}<div class="errbox" data-top hidden></div><form id="${fid}" class="fgrid" novalidate>${fields.map(f => fieldHTML(f, values[f.name])).join('')}</form>${after}`,
    footer: `${dismissable ? '<button class="btn" data-close>Cancelar</button>' : ''}<button class="btn p" form="${fid}" type="submit">${esc(submit)}</button>`,
  });
  const form = $('#' + fid, m), top = $('[data-top]', m);
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    const btn = $('button[type=submit]', m); btn.disabled = true; top.hidden = true;
    try { await onSubmit(formValues(form), m, form); }
    catch (e) { if (!showFieldError(form, e)) { top.textContent = e.message; top.hidden = false; } }
    finally { btn.disabled = false; }
  });
  return m;
}

function table(cols, rows, { empty = 'Nada por aqui ainda.', foot = '', rowAttr, id = '' } = {}) {
  if (!rows.length) return `<div class="tw"><div class="empty">${ic('drop')}<div>${esc(empty)}</div></div></div>`;
  return `<div class="tw"><table ${id ? `id="${id}"` : ''}><thead><tr>${cols.map(c => `<th class="${c.num ? 'num' : ''}">${c.h}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr ${rowAttr ? rowAttr(r) : ''}>${cols.map(c => `<td class="${c.num ? 'num' : ''} ${c.cls || ''}">${c.f(r)}</td>`).join('')}</tr>`).join('')}</tbody>${foot ? `<tfoot>${foot}</tfoot>` : ''}</table></div>`;
}
const SALE_ST = { confirmed: ['Confirmada', 'ok'], cancelled: ['Cancelada', 'bad'], refunded: ['Estornada', 'bad'] };
const COMM_ST = { prevista: ['Prevista', 'warn'], aprovada: ['Aprovada', ''], paga: ['Paga', 'ok'], cancelada: ['Cancelada', 'mut'] };
const PAY_LBL = { dinheiro: 'Dinheiro', pix: 'Pix', debito: 'Cartão de débito', cartao_credito: 'Cartão de crédito', boleto: 'Boleto', carne: 'Carnê', transferencia: 'Transferência', entrada: 'Entrada' };
const badge = (map, k) => { const [l, c] = map[k] || [k, 'mut']; return `<span class="badge ${c}">${esc(l)}</span>`; };
const avatar = (u, cls = '') => `<span class="avatar ${cls}">${u?.avatar ? `<img src="${esc(u.avatar)}" alt="">` : esc(initials(u?.name))}</span>`;
const spinner = '<div class="spin" role="status" aria-label="Carregando"></div>';
const logoHTML = () => `<span class="logo">${S.brand.logo ? `<img src="${esc(S.brand.logo)}" alt="">` : ic('drop')}</span>`;

function every(ms, fn) { S.timers.push(setInterval(() => { if (!document.hidden && !modals.length) fn(); }, ms)); }
function confetti(host, n = 46) {
  const cols = ['#fbbf24', '#22d3ee', '#fff', '#f472b6', '#34d399', '#a78bfa'];
  const w = document.createElement('div'); w.className = 'confetti';
  for (let i = 0; i < n; i++) { const p = document.createElement('i'); p.style.cssText = `left:${Math.random() * 100}%;background:${cols[i % cols.length]};animation-delay:${Math.random() * 3}s;animation-duration:${2.6 + Math.random() * 2}s;transform:rotate(${Math.random() * 360}deg)`; w.appendChild(p); }
  host.appendChild(w);
}
function wavesSVG() {
  return `<div class="waves" aria-hidden="true"><svg class="w1" viewBox="0 0 1200 200" preserveAspectRatio="none"><path fill="rgba(255,255,255,.14)" d="M0 100 C150 40 300 160 450 100 S750 40 900 100 S1050 160 1200 100 V200 H0Z"/></svg><svg class="w2" viewBox="0 0 1200 200" preserveAspectRatio="none"><path fill="rgba(34,211,238,.28)" d="M0 130 C150 80 300 180 450 130 S750 80 900 130 S1050 180 1200 130 V200 H0Z"/></svg></div>`;
}

/* ---------- cliques/atalhos ---------- */
document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]');
  if (el && ACT[el.dataset.act]) { e.preventDefault(); ACT[el.dataset.act](el, e); }
});
document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('tr.click[tabindex]')) { e.preventDefault(); e.target.click(); }
});

/* ---------- impressão ---------- */
function printHTML(html) { $('#print-area').innerHTML = html; setTimeout(() => window.print(), 60); }

/* ---------- shell e roteador ---------- */
function showLogin(msg) {
  S.timers.forEach(clearInterval); S.timers = []; closeAllModals();
  document.title = (S.brand.store_name || 'Gestão de Piscinas');
  const bubbles = Array.from({ length: 9 }, (_, i) => `<span style="left:${8 + i * 10}%;width:${10 + (i * 7) % 26}px;height:${10 + (i * 7) % 26}px;animation-delay:${i * 1.1}s;animation-duration:${7 + (i % 4) * 2}s"></span>`).join('');
  $('#app').innerHTML = `<div class="login"><section class="hero"><div class="bubbles">${bubbles}</div>
    <div class="row" style="gap:14px">${logoHTML()}<div><b style="font-size:20px">${esc(S.brand.store_name || 'Piscinas')}</b><div class="sm" style="opacity:.8">${esc(S.brand.tagline || '')}</div></div></div>
    <div><h2>Cada venda leva você mais perto da meta.</h2><p>Estoque, pacotes, comissões e financeiro da loja em um só lugar — no computador, no tablet ou no celular.</p></div>${wavesSVG()}</section>
    <section class="formside"><form id="loginf" novalidate><div><h1>Entrar</h1><p class="muted">Use o e-mail e a senha fornecidos pelo administrador.</p></div>
    <div class="errbox" id="lerr" ${msg ? '' : 'hidden'}>${esc(msg || '')}</div>
    <div class="field"><label for="le">E-mail</label><input id="le" type="email" autocomplete="username" required autofocus></div>
    <div class="field"><label for="lp">Senha</label><input id="lp" type="password" autocomplete="current-password" required></div>
    <button class="btn p xl" style="font-size:16px;padding:14px" id="lb" type="submit">Entrar</button></form></section></div>`;
  $('#loginf').addEventListener('submit', async ev => {
    ev.preventDefault(); const b = $('#lb'); b.disabled = true; $('#lerr').hidden = true;
    try {
      S.csrf = (await GET('/api/me')).csrf;   // a sessão pode ter expirado: pega um token novo
      const d = await POST('/api/login', { email: $('#le').value, password: $('#lp').value });
      applyMe(d); startApp();
    } catch (e) { $('#lerr').textContent = e.message; $('#lerr').hidden = false; b.disabled = false; $('#lp').select(); }
  });
}
function applyMe(d) { S.user = d.user; S.csrf = d.csrf; S.brand = d.branding || {}; S.settings = d.settings || {}; }

function startApp() {
  const u = S.user, admin = u.role === 'admin';
  document.title = S.brand.store_name || 'Gestão de Piscinas';
  const items = NAV.filter(n => n.roles.includes(u.role));
  let nav = '', lastSep = null;
  items.forEach(n => { if (n.sep && n.sep !== lastSep) { nav += `<div class="sep">${esc(n.sep)}</div>`; lastSep = n.sep; } nav += `<a href="#/${n.path}" data-nav="${n.path}">${ic(n.icon)}<span>${esc(n.label)}</span></a>`; });
  $('#app').innerHTML = `<div class="shell"><aside class="side" id="side"><div class="brand">${logoHTML()}<div><b>${esc(S.brand.store_name)}</b><span>${esc(S.brand.tagline || '')}</span></div></div><nav class="nav" id="nav">${nav}</nav></aside>
  <div class="scrim" id="scrim"></div>
  <div class="main"><header class="top"><button class="burger" id="burger" aria-label="Menu">${ic('menu')}</button><h1 id="ptitle"></h1><span class="grow"></span>
    <button class="user-btn" id="ubtn" aria-haspopup="true">${avatar(u)}<span class="nm">${esc(first(u.name))}</span></button></header>
    <main class="view" id="view"></main></div></div>
    ${admin ? '' : `<a class="fab" href="#/sale/new">${ic('plus')} NOVA VENDA</a>`}`;
  $('#burger').onclick = () => { $('#side').classList.toggle('open'); $('#scrim').classList.toggle('open'); };
  $('#scrim').onclick = closeSide;
  $('#ubtn').onclick = e => { e.stopPropagation(); userMenu(); };
  if (u.must_change_pw) forcePasswordChange();
  if (!location.hash || location.hash === '#/' || location.hash === '#') location.hash = admin ? '#/dashboard' : '#/home';
  route();
}
function closeSide() { $('#side')?.classList.remove('open'); $('#scrim')?.classList.remove('open'); }
function userMenu() {
  $('.menu')?.remove();
  const m = document.createElement('div'); m.className = 'menu';
  m.innerHTML = `<div style="padding:10px 12px"><b>${esc(S.user.name)}</b><div class="xs muted">${esc(S.user.email)} · ${S.user.role === 'admin' ? 'Administrador' : 'Vendedor'}</div></div><button data-act="avatar">${ic('camera')} Alterar foto</button><button data-act="chpw">${ic('key')} Alterar senha</button><button data-act="logout">${ic('logout')} Sair</button><input type="file" id="avfile" accept="image/png,image/jpeg,image/webp" hidden>`;
  document.body.appendChild(m);
  setTimeout(() => document.addEventListener('click', function h() { m.remove(); document.removeEventListener('click', h); }, { once: true }), 0);
}
ACT.logout = async () => { try { await POST('/api/logout'); } catch (e) { /* ignora */ } S.user = null; location.hash = ''; const d = await GET('/api/me'); applyMe(d); showLogin(); };
ACT.avatar = () => {
  const f = $('#avfile'); f.onchange = () => {
    const file = f.files[0]; if (!file) return;
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = async () => {
      const c = document.createElement('canvas'), s = 160, r = Math.min(img.width, img.height);
      c.width = c.height = s; c.getContext('2d').drawImage(img, (img.width - r) / 2, (img.height - r) / 2, r, r, 0, 0, s, s);
      try { await POST('/api/me/avatar', { avatar: c.toDataURL('image/jpeg', 0.85) }); const d = await GET('/api/me'); applyMe(d); startApp(); toast('Foto atualizada', 'ok'); } catch (e) { fail(e); }
      URL.revokeObjectURL(url);
    };
    img.src = url;
  };
  f.click();
};
const pwFields = [{ name: 'current', label: 'Senha atual', type: 'password', required: 1, full: 1 }, { name: 'new', label: 'Nova senha (mín. 8 caracteres)', type: 'password', required: 1, full: 1 }];
ACT.chpw = () => formModal({ title: 'Alterar senha', fields: pwFields, submit: 'Alterar senha', onSubmit: async (v, m) => { await POST('/api/me/password', v); S.user.must_change_pw = 0; m.close(); toast('Senha alterada', 'ok'); } });
function forcePasswordChange() {
  formModal({ title: 'Defina uma nova senha', fields: pwFields, submit: 'Salvar nova senha', dismissable: false,
    before: '<p class="muted">Por segurança, troque a senha temporária antes de continuar.</p>',
    onSubmit: async (v, m) => { await POST('/api/me/password', v); S.user.must_change_pw = 0; m.close(); toast('Senha alterada', 'ok'); } });
}

async function route() {
  if (!S.user) return;
  S.timers.forEach(clearInterval); S.timers = []; closeSide(); $('.menu')?.remove();
  const [path, query] = location.hash.replace(/^#\//, '').split('?');
  const r = R[path] || R[S.user.role === 'admin' ? 'dashboard' : 'home'];
  const key = R[path] ? path : (S.user.role === 'admin' ? 'dashboard' : 'home');
  if (!r.roles.includes(S.user.role)) { location.hash = S.user.role === 'admin' ? '#/dashboard' : '#/home'; return; }
  $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.nav === key));
  const fab = $('.fab'); if (fab) fab.style.display = (key === 'home' || key === 'sale/new') ? 'none' : '';
  $('#ptitle').textContent = typeof r.title === 'function' ? r.title() : r.title;
  const view = $('#view'); view.innerHTML = spinner; window.scrollTo(0, 0);
  const token = (route.t = (route.t || 0) + 1);
  try { await r.render(view, Object.fromEntries(new URLSearchParams(query || '')), () => token === route.t); }
  catch (e) { if (token === route.t) view.innerHTML = `<div class="errbox">${esc(e.message)}</div>`; }
}
window.addEventListener('hashchange', route);

/* ---------- componentes compartilhados ---------- */
const sel = (name, label, opts, val, extra = {}) => fieldHTML({ name, label, type: 'select', options: opts, ...extra }, val);
function periodFilters(v = {}) {
  return `<div class="field"><label>De</label><input type="date" name="from" value="${v.from || monthStart()}"></div><div class="field"><label>Até</label><input type="date" name="to" value="${v.to || today()}"></div>`;
}
function filterValues(bar) { const o = {}; $$('[name]', bar).forEach(el => { o[el.name] = el.value; }); return o; }
let _cats = null;
async function categories() { return _cats || (_cats = await GET('/api/categories')); }
function barChart(data, { fmt = brl, h = 180 } = {}) {
  if (!data.length) return `<div class="empty">Sem dados no período.</div>`;
  const max = Math.max(...data.map(d => d.value), 1);
  const step = Math.ceil(data.length / 12);
  return `<div class="bars" style="height:${h}px">${data.map((d, i) => `<div class="bc"><span class="tip">${esc(d.label)}: ${esc(fmt(d.value))}</span><i style="height:${Math.max(d.value / max * 100, 1.5)}%"></i><small>${i % step === 0 ? esc(d.short ?? d.label) : '&nbsp;'}</small></div>`).join('')}</div>`;
}
function hbars(items, fmt = brl) {
  if (!items.length) return `<div class="empty">Sem dados no período.</div>`;
  const max = Math.max(...items.map(i => i.value), 1);
  return items.map(i => `<div class="hb"><span title="${esc(i.label)}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(i.label)}</span><div class="t"><i style="width:${i.value / max * 100}%"></i></div><b class="nowrap">${esc(fmt(i.value))}</b></div>`).join('');
}
const progBar = p => `<div class="prog ${p >= 100 ? 'done' : ''}"><i style="width:${Math.min(p || 0, 100)}%"></i></div>`;

function receiptHTML(s) {
  const comps = id => s.items.filter(i => i.parent_id === id);
  const idisc = s.items.reduce((a, i) => a + (i.discount || 0), 0), gdisc = s.discount - idisc;
  const rows = s.items.filter(i => i.kind !== 'component').map(i => `<tr><td>${esc(i.name)}${i.kind === 'package' ? `<div style="font-size:11px;color:#444">Inclui: ${comps(i.id).map(c => `${esc(c.name)} (${num(c.qty)})`).join(', ')}</div>` : ''}</td><td class="num">${num(i.qty)}</td><td class="num">${brl(i.unit_price)}</td>${idisc ? `<td class="num">${i.discount ? '- ' + brl(i.discount) : ''}</td>` : ''}<td class="num">${brl(i.line_total - (i.discount || 0))}</td></tr>`).join('');
  const st = s.store || {};
  return `<div class="rcpt"><div class="hd">${st.logo ? `<img src="${esc(st.logo)}" alt="">` : ''}<div><h1>${esc(st.store_name || '')}</h1><div>${esc(st.store_tagline || '')}</div></div><div style="margin-left:auto;text-align:right"><b>COMPROVANTE DE VENDA</b><div>Nº ${esc(s.number)}</div><div>${fmtDT(s.created_at)}</div>${s.status !== 'confirmed' ? `<div><b>${esc(SALE_ST[s.status][0].toUpperCase())}</b></div>` : ''}</div></div>
  <p><b>Cliente:</b> ${esc(s.customer?.name)} ${s.customer?.doc ? '· CPF/CNPJ ' + esc(s.customer.doc) : ''}<br>${s.customer?.phone ? 'Tel: ' + esc(s.customer.phone) + ' · ' : ''}${esc([s.customer?.address, s.customer?.city].filter(Boolean).join(' — '))}<br><b>Vendedor:</b> ${esc(s.seller_name)}</p>
  <table><thead><tr><th>Item</th><th class="num">Qtd.</th><th class="num">Unitário</th>${idisc ? '<th class="num">Desconto</th>' : ''}<th class="num">Total</th></tr></thead><tbody>${rows}</tbody></table>
  <table style="margin-top:8px"><tbody><tr><td>Subtotal</td><td class="num">${brl(s.subtotal)}</td></tr>${idisc ? `<tr><td>Desconto nos itens</td><td class="num">- ${brl(idisc)}</td></tr>` : ''}${gdisc ? `<tr><td>${idisc ? 'Desconto geral' : 'Desconto'}</td><td class="num">- ${brl(gdisc)}</td></tr>` : ''}${s.freight ? `<tr><td>Frete</td><td class="num">${brl(s.freight)}</td></tr>` : ''}${s.install ? `<tr><td>Instalação</td><td class="num">${brl(s.install)}</td></tr>` : ''}${s.other ? `<tr><td>Outros serviços</td><td class="num">${brl(s.other)}</td></tr>` : ''}<tr><td><b>TOTAL</b></td><td class="num"><b>${brl(s.total)}</b></td></tr></tbody></table>
  <p><b>Pagamento:</b> ${esc(PAY_LBL[s.payment_method] || s.payment_method)}${s.installments > 1 ? ` em ${s.installments}x` : ''}${s.down_payment ? ` · entrada de ${brl(s.down_payment)}` : ''}</p>${s.notes ? `<p><b>Observações:</b> ${esc(s.notes)}</p>` : ''}
  <div class="sig"><div>Cliente</div><div>${esc(st.store_name || 'Loja')}</div></div></div>`;
}
async function openSale(id, onChange) {
  const s = await GET('/api/sales/' + id), admin = S.user.role === 'admin';
  const comps = pid => s.items.filter(i => i.parent_id === pid);
  const idisc = s.items.reduce((a, i) => a + (i.discount || 0), 0);
  const items = s.items.filter(i => i.kind !== 'component').map(i => `<tr><td>${esc(i.name)}${i.kind === 'package' ? `<div class="xs muted">${comps(i.id).map(c => esc(c.name) + ' ×' + num(c.qty)).join(' · ')}</div>` : ''}</td><td class="num">${num(i.qty)}</td><td class="num">${brl(i.unit_price)}</td>${idisc ? `<td class="num">${i.discount ? '− ' + brl(i.discount) : ''}</td>` : ''}<td class="num">${brl(i.line_total - (i.discount || 0))}</td>${admin ? `<td class="num">${brl(i.cost_total)}</td>` : ''}</tr>`).join('');
  const cm = s.commission;
  const body = `<div class="row between mb"><div><b>${esc(s.number)}</b> ${badge(SALE_ST, s.status)}<div class="sm muted">${fmtDT(s.created_at)} · Vendedor: ${esc(s.seller_name)}</div></div><div class="sm"><b>${esc(s.customer.name)}</b><br>${esc(s.customer.phone || '')}</div></div>
  <div class="tw"><table><thead><tr><th>Item</th><th class="num">Qtd.</th><th class="num">Unit.</th>${idisc ? '<th class="num">Desc.</th>' : ''}<th class="num">Total</th>${admin ? '<th class="num">Custo</th>' : ''}</tr></thead><tbody>${items}</tbody></table></div>
  <div class="grid g2 mt"><div class="stat"><div class="l">Total</div><div class="v">${brl(s.total)}</div><div class="s">Itens ${brl(s.subtotal)} − desconto ${brl(s.discount)}${idisc ? ` (${brl(idisc)} nos itens${s.discount - idisc ? ` + ${brl(s.discount - idisc)} geral` : ''})` : ''} + frete/instalação/outros ${brl(s.freight + s.install + s.other)}</div></div>
  <div class="stat"><div class="l">Pagamento</div><div class="v" style="font-size:17px">${esc(PAY_LBL[s.payment_method] || s.payment_method)}${s.installments > 1 ? ` · ${s.installments}x` : ''}</div><div class="s">${s.down_payment ? 'Entrada ' + brl(s.down_payment) : ''}</div></div>
  ${cm ? `<div class="stat"><div class="l">Comissão</div><div class="v">${brl(cm.amount)}</div><div class="s">${badge(COMM_ST, cm.status)}</div></div>` : ''}
  ${admin ? `<div class="stat"><div class="l">Lucro bruto estimado</div><div class="v">${brl(s.gross_profit)}</div><div class="s">Custos ${brl(s.cost_total + s.freight_cost + s.install_cost + s.other_cost)} ${s.costs_confirmed ? '' : '· <span class="warn b">frete/instalação a confirmar</span>'}</div></div>` : ''}</div>
  ${s.notes ? `<p class="mt"><b>Obs.:</b> ${esc(s.notes)}</p>` : ''}${s.status !== 'confirmed' ? `<div class="errbox mt">${esc(SALE_ST[s.status][0])} em ${fmtDT(s.cancelled_at)} — ${esc(s.cancel_reason || '')}</div>` : ''}
  ${admin && s.receivables?.length ? `<h3 class="mt">Parcelas</h3>${table([{ h: 'Parcela', f: r => r.installment_no ? `${r.installment_no}/${r.installments_total}` : 'Entrada' }, { h: 'Vencimento', f: r => fmtDate(r.due_date) }, { h: 'Valor', num: 1, f: r => brl(r.amount) }, { h: 'Situação', f: r => esc(r.status) }], s.receivables)}` : ''}`;
  const foot = `<button class="btn" data-close>Fechar</button><button class="btn" data-print>${ic('print')} Imprimir comprovante</button>${admin ? `<button class="btn" data-costs>${ic('dollar')} Custos frete/instalação</button>${s.status === 'confirmed' ? '<button class="btn d" data-cancel>Cancelar / estornar</button>' : ''}` : ''}`;
  const m = modal({ title: 'Venda ' + s.number, body, footer: foot, size: 'mid' });
  $('[data-print]', m).onclick = () => printHTML(receiptHTML(s));
  if (admin) {
    const c = $('[data-cancel]', m); if (c) c.onclick = () => formModal({
      title: 'Cancelar / estornar venda', submit: 'Confirmar cancelamento',
      before: '<p class="muted">O estoque volta ao saldo, a venda deixa de contar na meta e as comissões/recebimentos são ajustados conforme a política configurada.</p>',
      fields: [{ name: 'status', label: 'Tipo', type: 'select', options: [{ v: 'cancelled', l: 'Cancelamento' }, { v: 'refunded', l: 'Estorno (houve pagamento ao cliente)' }], full: 1 }, { name: 'reason', label: 'Motivo', type: 'textarea', required: 1, full: 1 }],
      onSubmit: async (v, mm) => { await POST(`/api/sales/${id}/cancel`, v); mm.close(); m.close(); toast('Venda cancelada', 'ok'); onChange && onChange(); },
    });
    $('[data-costs]', m).onclick = () => formModal({ title: 'Custos de frete e instalação', submit: 'Salvar custos',
      before: '<p class="muted">Informe quanto a loja realmente gastou. O lucro bruto da venda é recalculado.</p>',
      fields: [{ name: 'freight_cost', label: 'Custo do frete', type: 'money' }, { name: 'install_cost', label: 'Custo da instalação', type: 'money' }, { name: 'other_cost', label: 'Outros custos', type: 'money' }],
      values: { freight_cost: s.freight_cost, install_cost: s.install_cost, other_cost: s.other_cost },
      onSubmit: async (v, mm) => { await PUT(`/api/sales/${id}/costs`, v); mm.close(); m.close(); toast('Custos salvos', 'ok'); onChange && onChange(); } });
  }
  return m;
}
ACT.sale = el => openSale(el.dataset.id, () => route()).catch(fail);
