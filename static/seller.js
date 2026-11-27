'use strict';
/* Telas do vendedor e telas compartilhadas (vendas, estoque, clientes, comissões). */

const MILESTONES = {
  0: 'Bora começar! Cada venda aproxima você da meta.',
  50: '🔥 Metade da meta alcançada! Continue assim!',
  75: '🚀 75% da meta! A reta final começou.',
  90: '⚡ Falta pouco! Mais uma venda e você chega lá.',
  100: '🏆 META BATIDA! Parabéns pelo resultado incrível!',
};

/* ------------------------------------------------ início do vendedor */
function heroHTML(d, u) {
  const goal = d.goal, pctv = d.pct ?? 0;
  const msg = goal ? MILESTONES[d.milestone ?? 0] : 'O administrador ainda não definiu sua meta deste mês.';
  const ticks = [50, 75, 90, 100].map(t => `<span class="${pctv >= t ? 'on' : ''}" style="left:${t}%">${t}%</span>`).join('');
  return `<section class="seller-hero">${wavesSVG()}
    <div class="hero-top">${avatar(u, 'xl')}<div><div class="m">${esc(monthName(d.month))}</div><h1>Olá, ${esc(first(u.name))}!</h1></div></div>
    <div class="hero-stats">
      <div class="hs"><div class="l">Meta do mês</div><div class="v">${goal != null ? brl(goal) : '—'}</div></div>
      <div class="hs"><div class="l">Vendido no mês</div><div class="v">${brl(d.sold)}</div></div>
      <div class="hs"><div class="l">Falta vender</div><div class="v">${d.remaining != null ? brl(d.remaining) : '—'}</div></div>
      <div class="hs"><div class="l">Vendas realizadas</div><div class="v">${d.count}</div></div>
    </div>
    ${goal ? `<div class="pool" role="progressbar" aria-valuenow="${Math.round(pctv)}" aria-valuemin="0" aria-valuemax="100"><div class="fill" style="width:0" data-w="${Math.min(pctv, 100)}"></div><div class="pct">${pct(pctv)} da meta</div></div><div class="ticks">${ticks}</div>` : ''}
    <div class="msg ${d.milestone === 100 ? 'win' : ''}">${esc(msg)}</div>
    ${d.milestone === 100 ? '' : ''}</section>`;
}

R.home = {
  title: 'Minha meta', roles: ['vendedor', 'admin'],
  async render(view, query, alive) {
    const load = () => GET('/api/dashboard/seller', S.user.role === 'admin' ? { seller_id: query.seller_id } : {});
    let d = await load();
    if (!alive()) return;
    const draw = animate => {
    const u = d.seller || S.user, c = d.commission;
    view.innerHTML = `${heroHTML(d, u)}
      <a class="cta" href="#/sale/new">${ic('plus')} NOVA VENDA</a>
      <div class="grid g3 mt">
        <div class="stat"><div class="l">Comissão prevista</div><div class="v">${brl(c.prevista)}</div><div class="s">Aguardando aprovação</div></div>
        <div class="stat"><div class="l">Comissão aprovada</div><div class="v">${brl(c.aprovada)}</div><div class="s">A receber</div></div>
        <div class="stat good"><div class="l">Comissão paga</div><div class="v">${brl(c.paga)}</div><div class="s">Já recebida neste mês</div></div>
      </div>
      <div class="card mt"><div class="card-h"><h2>Vendas recentes</h2><span class="grow"></span><a class="btn s" href="#/my-sales">Ver todas</a></div>
      ${table([
        { h: 'Nº', f: r => `<b>${esc(r.number)}</b>` }, { h: 'Data', f: r => fmtDT(r.created_at) }, { h: 'Cliente', f: r => esc(r.customer) },
        { h: 'Total', num: 1, f: r => brl(r.total) }, { h: 'Situação', f: r => badge(SALE_ST, r.status) },
      ], d.recent, { empty: 'Nenhuma venda ainda. Que tal registrar a primeira?', rowAttr: r => `class="click" tabindex="0" data-act="sale" data-id="${r.id}"` })}</div>`;
    if (!animate) { $$('.pool .fill', view).forEach(f => { f.style.transition = 'none'; f.style.width = f.dataset.w + '%'; }); return; }
    requestAnimationFrame(() => setTimeout(() => $$('.pool .fill', view).forEach(f => { f.style.width = f.dataset.w + '%'; }), 60));
    if (d.milestone === 100) confetti($('.seller-hero', view));
    };
    draw(true);
    // atualização automática: só redesenha se algo mudou, sem voltar ao topo nem repetir a animação
    every(30000, async () => {
      if (!location.hash.startsWith('#/home') || !alive() || document.querySelector('.modal')) return;
      try { const n = await load(); if (!alive() || JSON.stringify(n) === JSON.stringify(d)) return; d = n; draw(false); } catch (e) { /* tenta de novo no próximo ciclo */ }
    });
  },
};

/* ------------------------------------------------ nova venda */
const PAY_OPTS = [['dinheiro', 'Dinheiro'], ['pix', 'Pix'], ['debito', 'Cartão de débito'], ['cartao_credito', 'Cartão de crédito'], ['boleto', 'Boleto'], ['carne', 'Carnê'], ['transferencia', 'Transferência']];

function customerFields() {
  return [
    { name: 'name', label: 'Nome ou razão social', required: 1, full: 1, max: 120 },
    { name: 'doc', label: 'CPF ou CNPJ', ph: 'Somente números', max: 18 },
    { name: 'phone', label: 'Telefone', type: 'tel', max: 20 },
    { name: 'whatsapp', label: 'WhatsApp', type: 'tel', max: 20 },
    { name: 'email', label: 'E-mail', type: 'email', max: 100 },
    { name: 'address', label: 'Endereço de entrega', full: 1, max: 300 },
    { name: 'city', label: 'Cidade', max: 80 },
    { name: 'notes', label: 'Observações', type: 'textarea', full: 1 },
  ];
}
function customerForm(c, done) {
  return formModal({
    title: c ? 'Editar cliente' : 'Novo cliente', fields: customerFields(), values: c || {}, size: 'mid',
    onSubmit: async (v, m) => { const r = c ? await PUT('/api/customers/' + c.id, v) : await POST('/api/customers', v); m.close(); toast('Cliente salvo', 'ok'); done && done(c ? { id: c.id, name: v.name } : r); },
  });
}

R['sale/new'] = {
  title: 'Nova venda', roles: ['vendedor', 'admin'],
  async render(view, query, alive) {
    const admin = S.user.role === 'admin';
    const [pkgs, prods, sellers] = await Promise.all([GET('/api/packages'), GET('/api/products', { kind: '' }), admin ? GET('/api/sellers') : []]);
    if (!alive()) return;
    const st = { key: uuid(), customer: null, cart: [], discount: 0, freight: 0, install: 0, other: 0, method: '', installments: 1, down: 0, notes: '', seller_id: '', busy: false };
    const activePk = pkgs.filter(p => p.active);
    view.innerHTML = `<div class="sale-grid"><div>
      ${admin ? `<div class="card mb"><div class="step"><span class="n">★</span><h3>Vendedor responsável</h3></div>${sel('seller_id', 'Vendedor', [{ v: '', l: 'Eu mesmo (administrador)' }, ...sellers.map(s => ({ v: s.id, l: s.name }))], '')}</div>` : ''}
      <div class="card mb"><div class="step"><span class="n">1</span><h3>Cliente</h3></div><div id="custbox"></div></div>
      <div class="card mb"><div class="step"><span class="n">2</span><h3>Pacote de piscina</h3></div>
        <div class="pk-grid">${activePk.map(p => `<button type="button" class="pk ${p.available === 0 ? 'off' : ''}" data-act="addpk" data-id="${p.id}"><b>${esc(p.name)}</b><span class="sm muted">${esc(p.description || '')}</span><span class="pr">${brl(p.sale_price)}</span><span class="xs ${p.available === 0 ? 'bad b' : 'muted'}">${p.available == null ? 'Sem controle de estoque' : p.available === 0 ? 'Sem estoque completo' : p.available + ' disponível(is)'}</span></button>`).join('') || '<div class="empty">Nenhum pacote ativo.</div>'}</div></div>
      <div class="card mb"><div class="step"><span class="n">3</span><h3>Produtos avulsos</h3></div>
        <div class="search" style="position:relative">${ic('search')}<input id="psearch" placeholder="Buscar por nome ou código" autocomplete="off"><div class="dd" id="pdd" hidden></div></div></div>
      <div class="card mb"><div class="step"><span class="n">4</span><h3>Itens da venda</h3></div><div class="list" id="cart"></div></div>
      <div class="card mb"><div class="step"><span class="n">5</span><h3>Valores e pagamento</h3></div>
        <div class="fgrid">${sel('discount_mode', 'Tipo do desconto geral', [{ v: '', l: 'Em reais (R$)' }, { v: 'pct', l: 'Em percentual (%)' }], '')}${fieldHTML({ name: 'discount', label: 'Desconto geral (no total)', type: 'money', hint: S.user.role === 'admin' ? 'O desconto por item é informado em cada item da venda.' : `Máximo autorizado: ${S.settings.seller_max_discount_pct ?? 0}% do valor dos itens, somando este desconto e os descontos por item.` })}
        ${fieldHTML({ name: 'freight', label: 'Frete cobrado do cliente', type: 'money' })}${fieldHTML({ name: 'install', label: 'Instalação cobrada', type: 'money' })}${fieldHTML({ name: 'other', label: 'Outros serviços', type: 'money' })}
        ${sel('payment_method', 'Forma de pagamento', [{ v: '', l: 'Selecione…' }, ...PAY_OPTS.map(([v, l]) => ({ v, l }))], '', { required: 1 })}
        <div class="field" id="instbox" hidden><label for="f_installments">Parcelas</label><input id="f_installments" name="installments" type="number" min="1" max="24" value="1"></div>
        <div id="downbox" hidden>${fieldHTML({ name: 'down_payment', label: 'Entrada', type: 'money' })}</div>
        ${fieldHTML({ name: 'notes', label: 'Observações', type: 'textarea', full: 1 })}</div></div></div>
      <aside class="sticky"><div class="card"><h3>Resumo</h3><div id="sum"><div class="muted sm">Adicione itens para ver o total.</div></div>
        <div class="errbox mt" id="sale-err" hidden></div>
        <button class="btn p xl mt" id="confirm" style="width:100%;font-size:17px;padding:14px" disabled>Confirmar venda</button></div></aside></div>`;

    // cliente
    const cb = $('#custbox', view);
    const drawCust = () => {
      if (st.customer) { cb.innerHTML = `<div class="row between"><div><b>${esc(st.customer.name)}</b><div class="sm muted">${esc(st.customer.phone || st.customer.doc || '')}</div></div><button class="btn s" data-act="chcust">Trocar</button></div>`; return; }
      cb.innerHTML = `<div class="row" style="gap:10px;align-items:flex-start"><div class="search grow" style="position:relative">${ic('search')}<input id="csearch" placeholder="Buscar cliente por nome, CPF/CNPJ ou telefone" autocomplete="off"><div class="dd" id="cdd" hidden></div></div><button class="btn p" data-act="newcust">${ic('plus')} Novo</button></div>`;
      const inp = $('#csearch', cb), dd = $('#cdd', cb);
      const run = debounce(async () => {
        const v = inp.value.trim(); if (v.length < 2) { dd.hidden = true; return; }
        try {
          const rows = await GET('/api/customers', { q: v });
          dd.innerHTML = rows.slice(0, 8).map(c => `<button type="button" data-c='${esc(JSON.stringify({ id: c.id, name: c.name, phone: c.phone, doc: c.doc }))}'><b>${esc(c.name)}</b><div class="xs muted">${esc(c.phone || '')} ${esc(c.doc || '')}</div></button>`).join('') || '<div style="padding:12px" class="sm muted">Nenhum cliente encontrado. Use “Novo”.</div>';
          dd.hidden = false;
          $$('button', dd).forEach(b => b.onclick = () => { st.customer = JSON.parse(b.dataset.c); drawCust(); refresh(); });
        } catch (e) { fail(e); }
      }, 250);
      inp.addEventListener('input', run);
    };
    ACT.chcust = () => { st.customer = null; drawCust(); refresh(); };
    ACT.newcust = () => customerForm(null, c => { st.customer = { id: c.id, name: c.name }; drawCust(); refresh(); });
    drawCust();

    // itens
    const cartEl = $('#cart', view);
    const drawCart = () => {
      cartEl.innerHTML = st.cart.length ? st.cart.map((it, i) => `<div class="li"><div class="grow"><b>${esc(it.name)}</b>${it.type === 'package' ? `<div class="xs muted">${it.removed.length ? it.removed.length + ' item(ns) removido(s) · ' : ''}${it.extras.length ? it.extras.length + ' adicional(is) · ' : ''}<a href="#" data-act="custpk" data-i="${i}">personalizar</a></div>` : `<div class="xs muted">${brl(it.price)} / ${esc(it.unit || 'un')}</div>`}</div>
        <div class="idisc"><button type="button" class="btn s" data-act="dmode" data-i="${i}" title="Alternar entre desconto em reais e em percentual" aria-label="Tipo de desconto do item: ${it.dpct ? 'percentual' : 'reais'}. Clique para alternar">Desc. ${it.dpct ? '%' : 'R$'}</button><input data-money data-d="${i}" inputmode="decimal" autocomplete="off" placeholder="0,00" value="${it.discount ? moneyIn(it.discount) : ''}" aria-label="Desconto neste item" title="Desconto neste item"></div>
        <div class="qty"><button type="button" data-act="qdec" data-i="${i}" aria-label="Diminuir">−</button><input type="number" min="0.001" step="${it.type === 'package' ? 1 : 'any'}" value="${it.qty}" data-i="${i}" aria-label="Quantidade"><button type="button" data-act="qinc" data-i="${i}" aria-label="Aumentar">+</button></div>
        <button class="btn s g" data-act="rm" data-i="${i}" aria-label="Remover">${ic('trash')}</button></div>`).join('') : '<div class="empty">Escolha um pacote ou busque um produto.</div>';
      $$('input[data-i]', cartEl).forEach(inp => inp.onchange = () => { const n = parseFloat(String(inp.value).replace(',', '.')); st.cart[+inp.dataset.i].qty = n > 0 ? n : 1; drawCart(); refresh(); });
      $$('input[data-d]', cartEl).forEach(inp => { const upd = () => { st.cart[+inp.dataset.d].discount = parseMoney(inp.value) || 0; rf(); }; inp.oninput = upd; inp.onchange = upd; });
    };
    ACT.addpk = el => {
      const p = pkgs.find(x => x.id === +el.dataset.id), ex = st.cart.find(c => c.type === 'package' && c.package_id === p.id && !c.removed.length && !c.extras.length);
      if (ex) ex.qty += 1; else st.cart.push({ type: 'package', package_id: p.id, name: p.name, qty: 1, removed: [], extras: [], pk: p });
      drawCart(); refresh();
    };
    const addProd = p => { const ex = st.cart.find(c => c.type === 'product' && c.product_id === p.id); if (ex) ex.qty += 1; else st.cart.push({ type: 'product', product_id: p.id, name: p.name, qty: 1, price: p.sale_price, unit: p.unit }); drawCart(); refresh(); };
    ACT.qinc = el => { st.cart[+el.dataset.i].qty = +(st.cart[+el.dataset.i].qty + 1).toFixed(3); drawCart(); refresh(); };
    ACT.qdec = el => { const it = st.cart[+el.dataset.i]; it.qty = Math.max(+(it.qty - 1).toFixed(3), it.type === 'package' ? 1 : 0.001); drawCart(); refresh(); };
    ACT.dmode = el => { const it = st.cart[+el.dataset.i]; it.dpct = !it.dpct; it.discount = 0; drawCart(); refresh(); };
    ACT.rm = el => { st.cart.splice(+el.dataset.i, 1); drawCart(); refresh(); };
    ACT.custpk = el => {
      const it = st.cart[+el.dataset.i], p = it.pk, rem = new Set(it.removed), extras = it.extras.map(x => ({ ...x }));
      const body = `<p class="muted sm">Itens que podem ser removidos geram crédito no preço do pacote.</p>
        ${p.items.map(c => `<label class="chk li"><input type="checkbox" data-rid="${c.id}" ${c.removable ? '' : 'disabled'} ${rem.has(c.id) ? '' : 'checked'}> <span class="grow">${esc(c.name)} × ${num(c.qty)}</span>${c.removable ? `<span class="xs muted">crédito ${brl(c.credit)}</span>` : '<span class="xs muted">obrigatório</span>'}</label>`).join('')}
        ${p.allow_extras ? `<h4 class="mt">Itens adicionais</h4><div class="row"><select id="exsel" class="grow">${prods.filter(x => x.kind === 'product').map(x => `<option value="${x.id}">${esc(x.name)} — ${brl(x.sale_price)}</option>`).join('')}</select><input id="exqty" type="number" min="1" value="1" style="width:80px"><button class="btn" id="exadd" type="button">Adicionar</button></div><div id="exlist"></div>` : '<p class="sm muted mt">Este pacote não aceita itens adicionais.</p>'}`;
      const m = modal({ title: 'Personalizar: ' + it.name, body, footer: '<button class="btn" data-close>Cancelar</button><button class="btn p" id="exok">Aplicar</button>' });
      const drawEx = () => { const l = $('#exlist', m); if (l) l.innerHTML = extras.map((x, k) => `<div class="li"><span class="grow">${esc(x.name)} × ${num(x.qty)}</span><button class="btn s g" data-k="${k}">${ic('x')}</button></div>`).join(''); $$('[data-k]', m).forEach(b => b.onclick = () => { extras.splice(+b.dataset.k, 1); drawEx(); }); };
      drawEx();
      const add = $('#exadd', m); if (add) add.onclick = () => { const pr = prods.find(x => x.id === +$('#exsel', m).value); extras.push({ product_id: pr.id, name: pr.name, qty: Math.max(1, +$('#exqty', m).value || 1) }); drawEx(); };
      $('#exok', m).onclick = () => { it.removed = $$('[data-rid]', m).filter(c => !c.checked && !c.disabled).map(c => +c.dataset.rid); it.extras = extras; m.close(); drawCart(); refresh(); };
    };
    drawCart();

    const ps = $('#psearch', view), pdd = $('#pdd', view);
    ps.addEventListener('input', debounce(async () => {
      const v = ps.value.trim(); if (!v) { pdd.hidden = true; return; }
      try {
        const rows = (await GET('/api/products', { q: v })).slice(0, 10);
        pdd.innerHTML = rows.map(p => `<button type="button" data-p="${p.id}"><b>${esc(p.name)}</b> <span class="xs muted">${esc(p.sku)}</span><div class="xs">${brl(p.sale_price)} · ${p.kind === 'service' ? 'Serviço' : 'estoque: ' + num(p.stock_qty) + ' ' + esc(p.unit)}${p.low ? ' <span class="warn b">baixo</span>' : ''}</div></button>`).join('') || '<div style="padding:12px" class="sm muted">Nada encontrado.</div>';
        pdd.hidden = false;
        $$('button', pdd).forEach(b => b.onclick = () => { addProd(rows.find(x => x.id === +b.dataset.p)); pdd.hidden = true; ps.value = ''; });
      } catch (e) { fail(e); }
    }, 250));
    document.addEventListener('click', e => { if (!e.target.closest('.search')) $$('.dd', view).forEach(d => d.hidden = true); });

    // formulário e resumo
    const val = n => { const el = $(`[name="${n}"]`, view); return el.hasAttribute('data-money') ? parseMoney(el.value) : el.value; };
    // em modo percentual o campo guarda centésimos de ponto percentual (10,00 → 10%)
    const disc = (v, pct) => pct ? { discount_pct: (v || 0) / 100 } : { discount: v || 0 };
    const payload = () => ({
      idempotency_key: st.key, customer_id: st.customer?.id, seller_id: admin ? (val('seller_id') || null) : undefined,
      items: st.cart.map(c => c.type === 'package' ? { type: 'package', package_id: c.package_id, qty: c.qty, removed: c.removed, extras: c.extras.map(x => ({ product_id: x.product_id, qty: x.qty })), ...disc(c.discount, c.dpct) } : { type: 'product', product_id: c.product_id, qty: c.qty, ...disc(c.discount, c.dpct) }),
      ...disc(val('discount'), val('discount_mode') === 'pct'), freight: val('freight'), install: val('install'), other: val('other'), payment_method: val('payment_method'),
      installments: +val('installments') || 1, down_payment: val('down_payment'), notes: val('notes'),
    });
    const sum = $('#sum', view), errb = $('#sale-err', view), btn = $('#confirm', view);
    let seq = 0;
    const refresh = async () => {
      const method = val('payment_method'), imm = ['dinheiro', 'pix', 'debito', ''].includes(method);
      $('#instbox', view).hidden = imm; $('#downbox', view).hidden = imm;
      btn.disabled = true; errb.hidden = true;
      if (!st.cart.length) { sum.innerHTML = '<div class="muted sm">Adicione itens para ver o total.</div>'; return; }
      if (!st.customer) { sum.innerHTML = '<div class="warnbox">Selecione o cliente para calcular o total.</div>'; return; }
      const my = ++seq;
      try {
        const p = await POST('/api/sales/preview', { ...payload(), payment_method: method || 'pix' });
        if (my !== seq) return;
        sum.innerHTML = `${p.lines.map(l => `<div class="sum-row"><span>${num(l.qty)}× ${esc(l.name)}</span><b>${brl(l.total)}</b></div>${l.discount ? `<div class="sum-row xs muted"><span>desconto no item</span><span>− ${brl(l.discount)}</span></div>` : ''}`).join('')}<hr style="border:0;border-top:1px solid var(--line)">
          <div class="sum-row"><span>Itens</span><span>${brl(p.gross)}</span></div>${p.items_discount ? `<div class="sum-row"><span>Desconto nos itens</span><span>− ${brl(p.items_discount)}</span></div>` : ''}${p.general_discount ? `<div class="sum-row"><span>Desconto geral</span><span>− ${brl(p.general_discount)}</span></div>` : ''}
          ${p.freight ? `<div class="sum-row"><span>Frete</span><span>${brl(p.freight)}</span></div>` : ''}${p.install ? `<div class="sum-row"><span>Instalação</span><span>${brl(p.install)}</span></div>` : ''}${p.other ? `<div class="sum-row"><span>Outros</span><span>${brl(p.other)}</span></div>` : ''}
          <div class="sum-row"><span class="b">TOTAL</span><span class="sum-total">${brl(p.total)}</span></div>
          <div class="sum-row"><span class="muted">Sua comissão estimada</span><b class="ok">${brl(p.commission)}</b></div>
          ${admin ? `<div class="sum-row"><span class="muted">Lucro bruto estimado</span><b>${brl(p.gross_profit)}</b></div>` : ''}
          ${p.stock_issues?.length ? `<div class="warnbox mt">${p.stock_issues.map(i => `Estoque insuficiente: ${esc(i.name)} (disponível ${num(i.available)}, necessário ${num(i.needed)} ${esc(i.unit)})`).join('<br>')}</div>` : ''}`;
        btn.disabled = !st.customer || !method;
      } catch (e) { if (my !== seq) return; sum.innerHTML = ''; errb.textContent = e.message; errb.hidden = false; }
    };
    const rf = debounce(refresh, 300);
    $$('[name]', view).forEach(el => { el.addEventListener('input', rf); el.addEventListener('change', rf); });
    btn.onclick = async () => {
      if (st.busy) return; st.busy = true; btn.disabled = true; btn.textContent = 'Registrando…';
      try {
        const r = await POST('/api/sales', payload());
        st.busy = true;   // trava definitiva: a chave já foi usada
        const s = await GET('/api/sales/' + r.id);
        const m = modal({ title: 'Venda registrada ✔', dismissable: false, body: `<div class="center"><div class="sum-total">${brl(r.total)}</div><p>Venda <b>${esc(r.number)}</b> confirmada${r.duplicate ? ' (já havia sido registrada)' : ''}. Estoque, meta e comissão foram atualizados.</p></div>`,
          footer: '<button class="btn" data-print>Imprimir comprovante</button><button class="btn" data-new>Nova venda</button><button class="btn p" data-home>Voltar ao início</button>' });
        $('[data-print]', m).onclick = () => printHTML(receiptHTML(s));
        $('[data-new]', m).onclick = () => { m.close(); route(); };
        $('[data-home]', m).onclick = () => { m.close(); location.hash = admin ? '#/sales' : '#/home'; };
      } catch (e) { st.busy = false; btn.textContent = 'Confirmar venda'; errb.textContent = e.message; errb.hidden = false; refresh(); }
    };
    drawCart();
  },
};

/* ------------------------------------------------ vendas */
async function salesPage(view, query, alive, mine) {
  const admin = S.user.role === 'admin';
  const sellers = admin ? await GET('/api/sellers') : [];
  view.innerHTML = `<div class="card"><form class="filters" id="fl">${periodFilters({ from: query.from })}
    ${admin ? sel('seller_id', 'Vendedor', [{ v: '', l: 'Todos' }, ...sellers.map(s => ({ v: s.id, l: s.name }))], '') : ''}
    ${sel('status', 'Situação', [{ v: '', l: 'Todas' }, { v: 'confirmed', l: 'Confirmadas' }, { v: 'cancelled', l: 'Canceladas' }, { v: 'refunded', l: 'Estornadas' }], '')}
    <div class="field"><label>Busca</label><input name="q" placeholder="Nº ou cliente"></div><button class="btn p" type="submit">Filtrar</button></form><div id="res">${spinner}</div></div>`;
  const load = async () => {
    const res = $('#res', view);
    try {
      const rows = await GET('/api/sales', filterValues($('#fl', view)));
      const tot = rows.filter(r => r.status === 'confirmed').reduce((a, r) => a + r.total, 0);
      const cols = [{ h: 'Nº', f: r => `<b>${esc(r.number)}</b>` }, { h: 'Data', f: r => fmtDT(r.created_at) }, { h: 'Cliente', f: r => esc(r.customer) }];
      if (admin) cols.push({ h: 'Vendedor', f: r => esc(r.seller) });
      cols.push({ h: 'Total', num: 1, f: r => brl(r.total) });
      if (admin) cols.push({ h: 'Lucro bruto', num: 1, f: r => brl(r.gross_profit) });
      cols.push({ h: 'Comissão', num: 1, f: r => r.commission != null ? brl(r.commission) : '—' }, { h: 'Situação', f: r => badge(SALE_ST, r.status) });
      res.innerHTML = `<p class="sm muted">${rows.length} venda(s) · total confirmado <b>${brl(tot)}</b></p>` + table(cols, rows, { empty: 'Nenhuma venda no período.', rowAttr: r => `class="click" tabindex="0" data-act="sale" data-id="${r.id}"` });
    } catch (e) { res.innerHTML = `<div class="errbox">${esc(e.message)}</div>`; }
  };
  $('#fl', view).addEventListener('submit', e => { e.preventDefault(); load(); });
  load();
}
R['my-sales'] = { title: 'Minhas vendas', roles: ['vendedor'], render: (v, q, a) => salesPage(v, q, a, true) };
R.sales = { title: 'Vendas', roles: ['admin'], render: (v, q, a) => salesPage(v, q, a, false) };

/* ------------------------------------------------ estoque (consulta) */
R.stock = {
  title: 'Estoque disponível', roles: ['vendedor'],
  async render(view) {
    const cats = await categories();
    view.innerHTML = `<div class="card"><form class="filters" id="fl"><div class="field grow"><label>Buscar</label><input name="q" placeholder="Nome, código, marca ou modelo"></div>${sel('category_id', 'Categoria', [{ v: '', l: 'Todas' }, ...cats.map(c => ({ v: c.id, l: c.name }))], '')}
      <label class="chk" style="padding-bottom:10px"><input type="checkbox" name="low"> Só estoque baixo</label></form><div id="res">${spinner}</div></div>`;
    const load = async () => {
      const f = filterValues($('#fl', view)); f.low = $('[name=low]', view).checked ? '1' : '';
      const rows = await GET('/api/products', f);
      $('#res', view).innerHTML = table([
        { h: 'Código', f: r => esc(r.sku) }, { h: 'Produto', f: r => `<b>${esc(r.name)}</b><div class="xs muted">${esc([r.brand, r.model].filter(Boolean).join(' · '))}</div>` }, { h: 'Categoria', f: r => esc(r.category || '—') },
        { h: 'Preço', num: 1, f: r => brl(r.sale_price) },
        { h: 'Disponível', num: 1, f: r => r.kind === 'service' ? '<span class="muted">Serviço</span>' : `${num(r.stock_qty)} ${esc(r.unit)} ${r.low ? '<span class="badge warn">Baixo</span>' : r.stock_qty <= 0 ? '<span class="badge bad">Zerado</span>' : ''}` },
      ], rows, { empty: 'Nenhum produto encontrado.' });
    };
    $('#fl', view).addEventListener('input', debounce(() => load().catch(fail), 250)); load().catch(fail);
  },
};

/* ------------------------------------------------ comissões (vendedor) */
R['my-commissions'] = {
  title: 'Minhas comissões', roles: ['vendedor'],
  async render(view) {
    const d = await GET('/api/commissions', { from: monthStart().slice(0, 4) + '-01-01' });
    const t = d.totals;
    view.innerHTML = `<div class="grid g3 mb"><div class="stat"><div class="l">Previstas</div><div class="v">${brl(t.prevista)}</div></div><div class="stat"><div class="l">Aprovadas</div><div class="v">${brl(t.aprovada)}</div></div><div class="stat good"><div class="l">Pagas</div><div class="v">${brl(t.paga)}</div></div></div>
    <div class="note mb">Valores do ano corrente, conforme as regras definidas pelo administrador. Comissões de vendas canceladas são ajustadas pela política da loja.</div>
    <div class="card">${table([{ h: 'Venda', f: r => `<b>${esc(r.number)}</b>` }, { h: 'Data', f: r => fmtDate(r.sale_date) }, { h: 'Cliente', f: r => esc(r.customer) }, { h: 'Total da venda', num: 1, f: r => brl(r.total) }, { h: 'Comissão', num: 1, f: r => `<b>${brl(r.amount)}</b>` }, { h: 'Situação', f: r => badge(COMM_ST, r.status) }, { h: 'Obs.', f: r => esc(r.kind === 'estorno' ? 'Estorno' : r.note || '') }], d.rows, { empty: 'Nenhuma comissão ainda.' })}</div>`;
  },
};

/* ------------------------------------------------ histórico de metas */
R.history = {
  title: 'Histórico de metas', roles: ['vendedor'],
  async render(view) {
    const rows = await GET('/api/goals/history');
    view.innerHTML = `<div class="card">${table([{ h: 'Mês', f: r => `<span style="text-transform:capitalize">${esc(monthName(r.month))}</span>` }, { h: 'Meta', num: 1, f: r => brl(r.goal) }, { h: 'Vendido', num: 1, f: r => brl(r.sold) }, { h: 'Vendas', num: 1, f: r => r.count }, { h: 'Atingido', f: r => r.pct == null ? '—' : `<div style="min-width:120px">${pct(r.pct)}${progBar(r.pct)}</div>` }], rows, { empty: 'Sem histórico ainda.' })}</div>`;
  },
};

/* ------------------------------------------------ clientes (vendedor e admin) */
R.customers = {
  title: 'Clientes', roles: ['vendedor', 'admin'],
  async render(view) {
    view.innerHTML = `<div class="card"><div class="filters"><div class="field grow search"><label>Buscar</label><input id="cq" placeholder="Nome, CPF/CNPJ ou telefone"></div><button class="btn p" id="cnew">${ic('plus')} Novo cliente</button></div><div id="res">${spinner}</div></div>`;
    const load = async () => {
      const rows = await GET('/api/customers', { q: $('#cq', view).value });
      $('#res', view).innerHTML = table([{ h: 'Nome', f: r => `<b>${esc(r.name)}</b>` }, { h: 'Telefone', f: r => esc(r.phone || r.whatsapp || '—') }, { h: 'Cidade', f: r => esc(r.city || '—') }, { h: 'Compras', num: 1, f: r => r.purchases }, { h: 'Última compra', f: r => fmtDate(r.last_purchase) }], rows,
        { empty: 'Nenhum cliente encontrado.', rowAttr: r => `class="click" tabindex="0" data-act="cust" data-id="${r.id}"` });
    };
    ACT.cust = async el => {
      try {
        const c = await GET('/api/customers/' + el.dataset.id);
        const m = modal({ title: c.name, size: 'mid', body: `<div class="sm"><div>${c.doc ? 'CPF/CNPJ: ' + esc(c.doc) + '<br>' : ''}Tel: ${esc(c.phone || '—')} · WhatsApp: ${esc(c.whatsapp || '—')}<br>${esc(c.email || '')}<br>Entrega: ${esc([c.address, c.city].filter(Boolean).join(' — ') || '—')}</div>${c.notes ? `<p><b>Obs.:</b> ${esc(c.notes)}</p>` : ''}</div><h3 class="mt">Histórico de compras</h3>${table([{ h: 'Nº', f: r => `<b>${esc(r.number)}</b>` }, { h: 'Data', f: r => fmtDate(r.created_at) }, { h: 'Vendedor', f: r => esc(r.seller) }, { h: 'Total', num: 1, f: r => brl(r.total) }, { h: 'Situação', f: r => badge(SALE_ST, r.status) }], c.sales, { empty: 'Sem compras.', rowAttr: r => `class="click" data-act="sale" data-id="${r.id}"` })}`, footer: '<button class="btn" data-close>Fechar</button><button class="btn p" data-edit>Editar</button>' });
        $('[data-edit]', m).onclick = () => { m.close(); customerForm(c, load); };
      } catch (e) { fail(e); }
    };
    $('#cq', view).addEventListener('input', debounce(() => load().catch(fail), 250));
    $('#cnew', view).onclick = () => customerForm(null, load);
    load().catch(fail);
  },
};

/* ------------------------------------------------ menu */
NAV.push(
  { path: 'home', label: 'Minha meta', icon: 'target', roles: ['vendedor'] },
  { path: 'sale/new', label: 'Nova venda', icon: 'plus', roles: ['vendedor'] },
  { path: 'my-sales', label: 'Minhas vendas', icon: 'cart', roles: ['vendedor'] },
  { path: 'stock', label: 'Estoque', icon: 'box', roles: ['vendedor'] },
  { path: 'customers', label: 'Clientes', icon: 'users', roles: ['vendedor'] },
  { path: 'my-commissions', label: 'Comissões', icon: 'percent', roles: ['vendedor'] },
  { path: 'history', label: 'Histórico de metas', icon: 'trophy', roles: ['vendedor'] },
);
