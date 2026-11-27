'use strict';
/* Telas do administrador. */

const A = ['admin'];
const tabsHTML = (items, cur) => `<div class="tabs" role="tablist">${items.map(([k, l]) => `<button role="tab" class="${k === cur ? 'on' : ''}" data-tab="${k}">${esc(l)}</button>`).join('')}</div>`;
const sellerOpts = async (all = 'Todos') => [{ v: '', l: all }, ...(await GET('/api/sellers')).map(s => ({ v: s.id, l: s.name }))];
const qstr = o => qs(o);

/* ------------------------------------------------ dashboard */
R.dashboard = {
  title: 'Painel do administrador', roles: A,
  async render(view, query, alive) {
    const [cats, sellers, prods] = await Promise.all([categories(), sellerOpts(), GET('/api/products')]);
    if (!alive()) return;
    view.innerHTML = `<div class="card mb"><form class="filters" id="fl">${periodFilters()}${sel('seller_id', 'Vendedor', sellers, '')}${sel('category_id', 'Categoria', [{ v: '', l: 'Todas' }, ...cats.map(c => ({ v: c.id, l: c.name }))], '')}${sel('product_id', 'Produto', [{ v: '', l: 'Todos' }, ...prods.map(p => ({ v: p.id, l: p.name }))], '')}<button class="btn p" type="submit">Aplicar</button></form></div><div id="dash">${spinner}</div>`;
    const load = async () => {
      const d = await GET('/api/dashboard/admin', filterValues($('#fl', view)));
      if (!alive()) return;
      const k = d.kpi, c = d.cash, cm = d.commissions, g = d.goals;
      $('#dash', view).innerHTML = `
      ${d.alerts.costs_unconfirmed ? `<div class="warnbox mb">${d.alerts.costs_unconfirmed} venda(s) com custos de frete/instalação ainda estimados. Confirme em Vendas para um lucro bruto preciso.</div>` : ''}
      ${d.scope === 'itens' ? '<div class="note mb">Filtro por produto/categoria ativo: os valores consideram apenas os itens filtrados.</div>' : ''}
      <h3 class="mb">Faturamento e lucro bruto</h3><div class="grid g5 mb">
        <div class="stat hi"><div class="l">Faturamento do período</div><div class="v">${brl(k.revenue)}</div><div class="s">${k.count} venda(s) · ticket médio ${brl(k.ticket)}</div></div>
        <div class="stat"><div class="l">Hoje</div><div class="v">${brl(k.today.v)}</div><div class="s">${k.today.n} venda(s)</div></div>
        <div class="stat"><div class="l">No mês</div><div class="v">${brl(k.month.v)}</div><div class="s">${k.month.n} venda(s)</div></div>
        <div class="stat"><div class="l">Custos registrados</div><div class="v">${brl(k.cost)}</div><div class="s">Produtos, frete e instalação</div></div>
        <div class="stat good"><div class="l">Lucro bruto estimado</div><div class="v">${brl(k.gross_profit)}</div><div class="s">Margem bruta ${pct(k.margin)} · antes de despesas e comissões</div></div></div>
      <h3 class="mb">Resultado financeiro (caixa)</h3><div class="note mb">Faturamento não é dinheiro em caixa nem lucro líquido: vendas parceladas só entram no caixa quando as parcelas são recebidas.</div>
      <div class="grid g6 mb"><div class="stat"><div class="l">Recebido no período</div><div class="v">${brl(c.received)}</div></div><div class="stat"><div class="l">Pago no período</div><div class="v">${brl(c.paid)}</div><div class="s">Contas + comissões pagas</div></div>
        <div class="stat ${c.result >= 0 ? 'good' : 'badx'}"><div class="l">Resultado de caixa</div><div class="v">${brl(c.result)}</div></div>
        <div class="stat"><div class="l">A receber</div><div class="v">${brl(c.to_receive)}</div><div class="s ${c.to_receive_late ? 'bad b' : ''}">${brl(c.to_receive_late)} em atraso</div></div>
        <div class="stat"><div class="l">A pagar</div><div class="v">${brl(c.to_pay)}</div><div class="s ${c.to_pay_late ? 'bad b' : ''}">${brl(c.to_pay_late)} em atraso</div></div>
        <div class="stat"><div class="l">Comissões</div><div class="v">${brl(cm.prevista + cm.aprovada)}</div><div class="s">previstas/aprovadas · ${brl(cm.paga)} pagas</div></div></div>
      <div class="grid g-main mb"><div class="card"><div class="card-h"><h3>Faturamento por dia</h3></div>${barChart(d.series.map(s => ({ label: fmtDate(s.day), short: s.day.slice(8), value: s.value })))}</div>
        <div class="card"><div class="card-h"><h3>Produtos mais vendidos</h3></div>${hbars(d.top_products.map(p => ({ label: p.name, value: p.revenue })))}</div></div>
      <div class="card mb"><div class="card-h"><h3>Desempenho dos vendedores</h3><span class="muted sm">Metas ${esc(monthName(g.month))}: ${g.achieved} atingida(s) · ${g.pending} pendente(s)${g.without_goal ? ` · ${g.without_goal} sem meta` : ''}</span></div>
        ${table([{ h: 'Vendedor', f: r => `<span class="row">${avatar(r)} <b>${esc(r.name)}</b></span>` }, { h: 'Vendas', num: 1, f: r => r.count }, { h: 'Faturamento', num: 1, f: r => brl(r.sold) }, { h: 'Lucro bruto', num: 1, f: r => brl(r.profit) }, { h: 'Meta do mês', num: 1, f: r => r.goal ? brl(r.goal) : '—' }, { h: 'Progresso', f: r => r.goal ? `<div style="min-width:130px">${pct(r.pct)}${progBar(r.pct)}</div>` : '<span class="muted">Sem meta</span>' }], d.sellers)}</div>
      <div class="grid g2"><div class="card"><div class="card-h"><h3>${ic('alert')} Estoque baixo</h3></div>${table([{ h: 'Produto', f: r => esc(r.name) }, { h: 'Estoque', num: 1, f: r => `<b class="${r.stock_qty <= 0 ? 'bad' : 'warn'}">${num(r.stock_qty)}</b> ${esc(r.unit)}` }, { h: 'Mínimo', num: 1, f: r => num(r.min_stock) }], d.low_stock, { empty: 'Nenhum produto abaixo do mínimo.' })}</div>
        <div class="card"><div class="card-h"><h3>Últimas movimentações</h3></div>${table([{ h: 'Data', f: r => fmtDT(r.created_at) }, { h: 'Produto', f: r => esc(r.product) }, { h: 'Tipo', f: r => esc(r.type) }, { h: 'Qtd.', num: 1, f: r => (r.qty > 0 ? '+' : '') + num(r.qty) }], d.movements, { empty: 'Sem movimentações.' })}</div></div>`;
    };
    $('#fl', view).addEventListener('submit', e => { e.preventDefault(); load().catch(fail); });
    await load();
    every(60000, () => load().catch(() => { }));
  },
};

/* ------------------------------------------------ metas */
R.goals = {
  title: 'Metas e desempenho', roles: A,
  async render(view, query, alive) {
    const month = query.month || today().slice(0, 7);
    const d = await GET('/api/goals', { month });
    if (!alive()) return;
    view.innerHTML = `<div class="card mb"><form class="filters" id="fl"><div class="field"><label>Mês de referência</label><input type="month" name="month" value="${esc(month)}"></div><button class="btn p">Ver</button></form>
      <div class="note">Defina metas de meses futuros escolhendo o mês acima. Vendas canceladas ou estornadas não contam para a meta.</div></div>
      <div class="grid g3">${d.rows.map(r => `<div class="card"><div class="row">${avatar(r, 'xl')}<div><b>${esc(r.name)}</b><div class="xs muted">${r.count} venda(s)</div></div></div>
        <div class="grid g2 mt"><div class="stat"><div class="l">Meta</div><div class="v">${r.goal != null ? brl(r.goal) : '—'}</div></div><div class="stat"><div class="l">Vendido</div><div class="v">${brl(r.sold)}</div></div></div>
        ${r.goal ? `<div class="mt">${pct(r.pct)} atingido${progBar(r.pct)}</div>` : '<p class="muted sm mt">Sem meta definida.</p>'}
        <div class="row mt"><button class="btn s" data-act="setgoal" data-id="${r.id}" data-name="${esc(r.name)}" data-amount="${r.goal ?? ''}">${ic('target')} Definir meta</button><button class="btn s g" data-act="goalhist" data-id="${r.id}" data-name="${esc(r.name)}">Histórico</button></div></div>`).join('') || '<div class="empty">Nenhum vendedor ativo. Cadastre em Usuários.</div>'}</div>`;
    $('#fl', view).addEventListener('submit', e => { e.preventDefault(); location.hash = '#/goals?month=' + $('[name=month]', view).value; });
    ACT.setgoal = el => formModal({ title: `Meta de ${el.dataset.name} — ${monthName(month)}`, fields: [{ name: 'amount', label: 'Meta do mês (R$)', type: 'money', required: 1, full: 1 }], values: { amount: el.dataset.amount ? +el.dataset.amount : '' }, submit: 'Salvar meta',
      onSubmit: async (v, m) => { await PUT('/api/goals', { seller_id: +el.dataset.id, month, amount: v.amount }); m.close(); toast('Meta salva', 'ok'); route(); } });
    ACT.goalhist = async el => { try { const h = await GET('/api/goals/history', { seller_id: el.dataset.id }); modal({ title: 'Histórico — ' + el.dataset.name, size: 'mid', body: table([{ h: 'Mês', f: r => esc(monthName(r.month)) }, { h: 'Meta', num: 1, f: r => brl(r.goal) }, { h: 'Vendido', num: 1, f: r => brl(r.sold) }, { h: '%', num: 1, f: r => pct(r.pct) }], h, { empty: 'Sem histórico.' }) }); } catch (e) { fail(e); } };
  },
};

/* ------------------------------------------------ produtos e estoque */
function productFields(cats, sups, creating) {
  return [
    { name: 'sku', label: 'Código / SKU', required: 1, max: 40 }, { name: 'name', label: 'Nome do produto', required: 1, max: 120 },
    { name: 'kind', label: 'Tipo', type: 'select', options: [{ v: 'product', l: 'Produto (controla estoque)' }, { v: 'service', l: 'Serviço (sem estoque)' }] },
    { name: 'category_id', label: 'Categoria', type: 'select', options: [{ v: '', l: '—' }, ...cats.map(c => ({ v: c.id, l: c.name }))] },
    { name: 'brand', label: 'Marca' }, { name: 'model', label: 'Modelo' },
    { name: 'cost_price', label: 'Preço de custo', type: 'money', required: 1 }, { name: 'sale_price', label: 'Preço de venda', type: 'money', required: 1 },
    ...(creating ? [{ name: 'stock_qty', label: 'Estoque inicial', type: 'number', min: 0 }] : []),
    { name: 'min_stock', label: 'Estoque mínimo', type: 'number', min: 0 }, { name: 'unit', label: 'Unidade de medida', ph: 'un, m, kg, L, m²…' },
    { name: 'supplier_id', label: 'Fornecedor', type: 'select', options: [{ v: '', l: '—' }, ...sups.map(s => ({ v: s.id, l: s.name }))] },
    { name: 'description', label: 'Descrição', type: 'textarea', full: 1 }, { name: 'active', label: 'Produto ativo', type: 'checkbox', full: 1 },
  ];
}
R.products = {
  title: 'Produtos e estoque', roles: A,
  async render(view, query, alive) {
    const tab = query.tab || 'list';
    const [cats, sups] = await Promise.all([categories(), GET('/api/suppliers')]);
    if (!alive()) return;
    view.innerHTML = tabsHTML([['list', 'Produtos'], ['moves', 'Movimentações'], ['sups', 'Fornecedores']], tab) + '<div id="tab"></div>';
    $$('[data-tab]', view).forEach(b => b.onclick = () => { location.hash = '#/products?tab=' + b.dataset.tab; });
    const box = $('#tab', view);
    if (tab === 'list') {
      box.innerHTML = `<div class="card"><form class="filters" id="fl"><div class="field grow"><label>Buscar</label><input name="q" placeholder="Nome ou código"></div>${sel('category_id', 'Categoria', [{ v: '', l: 'Todas' }, ...cats.map(c => ({ v: c.id, l: c.name }))], '')}${sel('active', 'Situação', [{ v: '', l: 'Todos' }, { v: '1', l: 'Ativos' }, { v: '0', l: 'Inativos' }], '')}<label class="chk" style="padding-bottom:10px"><input type="checkbox" name="low"> Estoque baixo</label><button type="button" class="btn p" id="pnew">${ic('plus')} Novo produto</button></form><div id="res">${spinner}</div></div>`;
      const load = async () => {
        const f = filterValues($('#fl', view)); f.low = $('[name=low]', view).checked ? '1' : '';
        const rows = await GET('/api/products', f);
        $('#res', view).innerHTML = table([{ h: 'Código', f: r => esc(r.sku) }, { h: 'Produto', f: r => `<b>${esc(r.name)}</b><div class="xs muted">${esc(r.category || '')} ${esc([r.brand, r.model].filter(Boolean).join(' · '))}</div>` },
          { h: 'Custo', num: 1, f: r => brl(r.cost_price) }, { h: 'Venda', num: 1, f: r => brl(r.sale_price) },
          { h: 'Estoque', num: 1, f: r => r.kind === 'service' ? '<span class="muted">Serviço</span>' : `<b class="${r.stock_qty <= r.min_stock ? 'bad' : ''}">${num(r.stock_qty)}</b> ${esc(r.unit)}${r.stock_qty <= r.min_stock ? ' <span class="badge warn">Baixo</span>' : ''}` },
          { h: 'Situação', f: r => r.active ? '<span class="badge ok">Ativo</span>' : '<span class="badge mut">Inativo</span>' },
          { h: '', f: r => `<span class="row nowrap">${r.kind === 'product' ? `<button class="btn s" data-act="move" data-id="${r.id}">Movimentar</button>` : ''}<button class="btn s g" data-act="pedit" data-id="${r.id}">${ic('edit')}</button></span>` }], rows, { empty: 'Nenhum produto encontrado.' });
        window._prods = rows;
      };
      $('#fl', view).addEventListener('input', debounce(() => load().catch(fail), 250));
      $('#pnew', view).onclick = () => formModal({ title: 'Novo produto', size: 'mid', fields: productFields(cats, sups, true), values: { kind: 'product', unit: 'un', active: 1 }, onSubmit: async (v, m) => { v.supplier_id = v.supplier_id || null; await POST('/api/products', v); m.close(); toast('Produto cadastrado', 'ok'); load(); } });
      ACT.pedit = el => { const p = window._prods.find(x => x.id === +el.dataset.id); formModal({ title: 'Editar produto', size: 'mid', fields: productFields(cats, sups, false), values: p, before: '<p class="muted sm">O estoque só muda por movimentações, para manter o histórico.</p>', onSubmit: async (v, m) => { v.supplier_id = v.supplier_id || null; await PUT('/api/products/' + p.id, v); m.close(); toast('Produto atualizado', 'ok'); load(); } }); };
      ACT.move = el => {
        const p = window._prods.find(x => x.id === +el.dataset.id);
        formModal({ title: `Movimentar: ${p.name}`, submit: 'Registrar', before: `<p>Saldo atual: <b>${num(p.stock_qty)} ${esc(p.unit)}</b></p>`,
          fields: [{ name: 'type', label: 'Tipo', type: 'select', options: [{ v: 'entrada', l: 'Entrada de mercadoria' }, { v: 'saida', l: 'Saída' }, { v: 'ajuste', l: 'Ajuste (informar quantidade contada)' }], full: 1 }, { name: 'qty', label: 'Quantidade', type: 'number', min: 0, required: 1 }, { name: 'unit_cost', label: 'Novo custo unitário (entrada)', type: 'money' }, { name: 'reason', label: 'Motivo / observação', type: 'textarea', full: 1, hint: 'Obrigatório para saída e ajuste' }],
          onSubmit: async (v, m) => { if (!v.unit_cost) delete v.unit_cost; await POST('/api/stock/move', { ...v, product_id: p.id }); m.close(); toast('Movimentação registrada', 'ok'); load(); } });
      };
      await load();
    } else if (tab === 'moves') {
      box.innerHTML = `<div class="card"><form class="filters" id="fl">${periodFilters({ from: today().slice(0, 4) + '-01-01' })}${sel('type', 'Tipo', [{ v: '', l: 'Todos' }, { v: 'entrada', l: 'Entrada' }, { v: 'saida', l: 'Saída' }, { v: 'ajuste', l: 'Ajuste' }, { v: 'venda', l: 'Venda' }, { v: 'estorno', l: 'Estorno' }], '')}${sel('category_id', 'Categoria', [{ v: '', l: 'Todas' }, ...cats.map(c => ({ v: c.id, l: c.name }))], '')}<button class="btn p">Filtrar</button></form><div id="res">${spinner}</div></div>`;
      const load = async () => { const rows = await GET('/api/stock/movements', filterValues($('#fl', view))); $('#res', view).innerHTML = table([{ h: 'Data', f: r => fmtDT(r.created_at) }, { h: 'Produto', f: r => `<b>${esc(r.product)}</b><div class="xs muted">${esc(r.sku)}</div>` }, { h: 'Tipo', f: r => esc(r.type) }, { h: 'Qtd.', num: 1, f: r => `<b class="${r.qty < 0 ? 'bad' : 'ok'}">${r.qty > 0 ? '+' : ''}${num(r.qty)}</b>` }, { h: 'Saldo', num: 1, f: r => num(r.balance_after) }, { h: 'Motivo', f: r => esc(r.reason || '') }, { h: 'Usuário', f: r => esc(r.user || '') }], rows, { empty: 'Sem movimentações no período.' }); };
      $('#fl', view).addEventListener('submit', e => { e.preventDefault(); load().catch(fail); }); await load();
    } else {
      const supF = [{ name: 'name', label: 'Nome', required: 1, full: 1 }, { name: 'doc', label: 'CNPJ/CPF' }, { name: 'phone', label: 'Telefone' }, { name: 'email', label: 'E-mail', type: 'email' }, { name: 'notes', label: 'Observações', type: 'textarea', full: 1 }, { name: 'active', label: 'Ativo', type: 'checkbox' }];
      box.innerHTML = `<div class="card"><div class="card-h"><h3>Fornecedores</h3><span class="grow"></span><button class="btn p" id="snew">${ic('plus')} Novo</button></div>${table([{ h: 'Nome', f: r => `<b>${esc(r.name)}</b>` }, { h: 'Contato', f: r => esc([r.phone, r.email].filter(Boolean).join(' · ')) }, { h: 'Situação', f: r => r.active ? '<span class="badge ok">Ativo</span>' : '<span class="badge mut">Inativo</span>' }, { h: '', f: r => `<button class="btn s g" data-act="sedit" data-id="${r.id}">${ic('edit')}</button>` }], sups, { empty: 'Nenhum fornecedor.' })}</div>`;
      $('#snew', view).onclick = () => formModal({ title: 'Novo fornecedor', fields: supF, values: { active: 1 }, onSubmit: async (v, m) => { await POST('/api/suppliers', v); m.close(); route(); } });
      ACT.sedit = el => { const s = sups.find(x => x.id === +el.dataset.id); formModal({ title: 'Editar fornecedor', fields: supF, values: s, onSubmit: async (v, m) => { await PUT('/api/suppliers/' + s.id, v); m.close(); route(); } }); };
    }
  },
};

/* ------------------------------------------------ pacotes */
R.packages = {
  title: 'Pacotes de piscinas', roles: A,
  async render(view, query, alive) {
    const [pkgs, prods] = await Promise.all([GET('/api/packages'), GET('/api/products')]);
    if (!alive()) return;
    view.innerHTML = `<div class="row mb"><span class="muted grow">Cada componente permanece separado no estoque, no custo e na comissão. O vendedor escolhe o pacote com um clique.</span><button class="btn p" id="pknew">${ic('plus')} Novo pacote</button></div>
      <div class="grid g2">${pkgs.map(p => `<div class="card ${p.active ? '' : 'flat'}" style="${p.active ? '' : 'opacity:.65'}"><div class="card-h"><h3>${esc(p.name)}</h3>${p.active ? '' : '<span class="badge mut">Inativo</span>'}<span class="grow"></span><button class="btn s" data-act="pkedit" data-id="${p.id}">${ic('edit')} Editar</button></div>
        <p class="sm muted">${esc(p.description || '')}</p>
        <div class="grid g3 pkstats"><div class="stat"><div class="l">Preço</div><div class="v">${brl(p.sale_price)}</div></div><div class="stat"><div class="l">Custo</div><div class="v">${brl(p.cost_total)}</div></div><div class="stat good"><div class="l">Lucro bruto</div><div class="v">${brl(p.gross_profit)}</div></div></div>
        <p class="sm mt"><b>${p.items.length} componentes:</b> ${p.items.map(i => esc(i.name) + ' ×' + num(i.qty)).join(', ')}</p>
        <p class="xs muted">Comissão: ${p.commission_rule ? (p.commission_rule.type === 'percent' ? pct(p.commission_rule.value) + ' sobre ' + (p.commission_rule.base === 'eligible' ? 'itens elegíveis' : 'o total') : brl(Math.round(p.commission_rule.value * 100)) + ' fixa') : 'regra padrão'} · Disponível: ${p.available ?? '—'}</p></div>`).join('') || '<div class="empty">Nenhum pacote cadastrado.</div>'}</div>`;
    const edit = p => {
      const items = p ? p.items.map(i => ({ ...i })) : [{ product_id: prods[0]?.id, qty: 1, cost_override: null, price_alloc: 0, commission_eligible: 1, removable: 0 }];
      const cr = p?.commission_rule || null;
      const m = modal({ title: p ? 'Editar pacote' : 'Novo pacote', size: 'wide', body: `<div class="errbox" data-top hidden></div><form class="fgrid" id="pkf" novalidate>${fieldHTML({ name: 'name', label: 'Nome do pacote', required: 1, full: 1 }, p?.name)}${fieldHTML({ name: 'description', label: 'Descrição', type: 'textarea', rows: 2, full: 1 }, p?.description)}${fieldHTML({ name: 'sale_price', label: 'Preço final de venda', type: 'money', required: 1 }, p?.sale_price)}
        ${fieldHTML({ name: 'allow_extras', label: 'Permitir itens adicionais na venda', type: 'checkbox' }, p ? p.allow_extras : 1)}${fieldHTML({ name: 'active', label: 'Pacote ativo', type: 'checkbox' }, p ? p.active : 1)}
        <div class="full"><h4>Componentes</h4><div class="note mb">Custo: usa o custo do produto, ou o valor informado. “Valor no preço” é o quanto o componente representa no preço final (usado como crédito se o vendedor o remover). “Elegível” define se entra na base de comissão por itens.</div><div id="pkitems"></div><button type="button" class="btn s mt-s" id="pkadd">${ic('plus')} Adicionar componente</button></div>
        <div class="full"><h4>Regra de comissão do pacote</h4></div>
        ${fieldHTML({ name: 'ctype', label: 'Tipo', type: 'select', options: [{ v: '', l: 'Usar regra padrão' }, { v: 'percent', l: 'Percentual' }, { v: 'fixed', l: 'Valor fixo (R$)' }] }, cr?.type || '')}
        ${fieldHTML({ name: 'cvalue', label: 'Valor (% ou R$)', type: 'number', min: 0 }, cr?.value ?? '')}${fieldHTML({ name: 'cbase', label: 'Base de cálculo', type: 'select', options: [{ v: 'total', l: 'Valor total do pacote' }, { v: 'eligible', l: 'Somente componentes elegíveis' }] }, cr?.base || 'total')}</form>`,
        footer: '<button class="btn" data-close>Cancelar</button><button class="btn p" id="pksave">Salvar pacote</button>' });
      const box = $('#pkitems', m);
      const draw = () => {
        box.innerHTML = items.map((it, i) => `<div class="li" style="flex-wrap:wrap;align-items:flex-end"><div class="field grow" style="min-width:200px"><label>Produto/serviço</label><select data-k="product_id" data-i="${i}">${prods.map(x => `<option value="${x.id}" ${x.id === it.product_id ? 'selected' : ''}>${esc(x.name)} (${brl(x.cost_price)})</option>`).join('')}</select></div>
          <div class="field" style="width:80px"><label>Qtd.</label><input type="number" step="any" min="0.001" data-k="qty" data-i="${i}" value="${it.qty}"></div>
          <div class="field" style="width:120px"><label>Custo unit.</label><input data-money data-k="cost_override" data-i="${i}" value="${it.cost_override == null ? '' : moneyIn(it.cost_override)}" placeholder="do produto"></div>
          <div class="field" style="width:120px"><label>Valor no preço (un.)</label><input data-money data-k="price_alloc" data-i="${i}" value="${moneyIn(it.price_alloc || 0)}"></div>
          <label class="chk"><input type="checkbox" data-k="commission_eligible" data-i="${i}" ${it.commission_eligible ? 'checked' : ''}> Elegível</label><label class="chk"><input type="checkbox" data-k="removable" data-i="${i}" ${it.removable ? 'checked' : ''}> Removível</label>
          <button type="button" class="btn s g" data-rm="${i}" aria-label="Remover">${ic('trash')}</button></div>`).join('');
        $$('[data-k]', box).forEach(el => el.onchange = () => { const it = items[+el.dataset.i], k = el.dataset.k; it[k] = el.type === 'checkbox' ? (el.checked ? 1 : 0) : el.hasAttribute('data-money') ? (el.value.trim() === '' && k === 'cost_override' ? null : parseMoney(el.value)) : k === 'product_id' ? +el.value : parseFloat(el.value) || 1; });
        $$('[data-rm]', box).forEach(b => b.onclick = () => { items.splice(+b.dataset.rm, 1); draw(); });
      };
      draw(); $('#pkadd', m).onclick = () => { items.push({ product_id: prods[0]?.id, qty: 1, cost_override: null, price_alloc: 0, commission_eligible: 1, removable: 0 }); draw(); };
      $('#pksave', m).onclick = async () => {
        const f = formValues($('#pkf', m)), top = $('[data-top]', m); top.hidden = true;
        const body = { name: f.name, description: f.description, sale_price: f.sale_price, allow_extras: f.allow_extras, active: f.active, items, commission: f.ctype ? { type: f.ctype, value: f.cvalue, base: f.cbase } : {} };
        try { if (p) await PUT('/api/packages/' + p.id, body); else await POST('/api/packages', body); m.close(); toast('Pacote salvo', 'ok'); route(); } catch (e) { top.textContent = e.message; top.hidden = false; }
      };
    };
    $('#pknew', view).onclick = () => edit(null);
    ACT.pkedit = el => edit(pkgs.find(x => x.id === +el.dataset.id));
  },
};

/* ------------------------------------------------ comissões */
R.commissions = {
  title: 'Comissões', roles: A,
  async render(view, query, alive) {
    const tab = query.tab || 'list';
    view.innerHTML = tabsHTML([['list', 'Comissões geradas'], ['rules', 'Regras']], tab) + '<div id="tab"></div>';
    $$('[data-tab]', view).forEach(b => b.onclick = () => { location.hash = '#/commissions?tab=' + b.dataset.tab; });
    const box = $('#tab', view);
    if (tab === 'list') {
      const sellers = await sellerOpts();
      box.innerHTML = `<div class="card"><form class="filters" id="fl">${periodFilters()}${sel('seller_id', 'Vendedor', sellers, '')}${sel('status', 'Situação', [{ v: '', l: 'Todas' }, { v: 'prevista', l: 'Prevista' }, { v: 'aprovada', l: 'Aprovada' }, { v: 'paga', l: 'Paga' }, { v: 'cancelada', l: 'Cancelada' }], '')}<button class="btn p">Filtrar</button></form><div id="res">${spinner}</div></div>`;
      const load = async () => {
        const d = await GET('/api/commissions', filterValues($('#fl', view)));
        $('#res', view).innerHTML = `<div class="grid g3 mb"><div class="stat"><div class="l">Previstas</div><div class="v">${brl(d.totals.prevista)}</div></div><div class="stat"><div class="l">Aprovadas (a pagar)</div><div class="v">${brl(d.totals.aprovada)}</div></div><div class="stat good"><div class="l">Pagas</div><div class="v">${brl(d.totals.paga)}</div></div></div>
          <div class="row mb"><button class="btn s" data-bulk="aprovada">Aprovar selecionadas</button><button class="btn s" data-bulk="paga">Marcar como pagas</button><button class="btn s d" data-bulk="cancelada">Cancelar selecionadas</button></div>
          ${table([{ h: '<input type="checkbox" id="ckall" aria-label="Selecionar todas">', f: r => `<input type="checkbox" class="ck" value="${r.id}">` }, { h: 'Venda', f: r => `<a href="#" data-act="sale" data-id="${r.sale_id}"><b>${esc(r.number)}</b></a>` }, { h: 'Data', f: r => fmtDate(r.sale_date) }, { h: 'Vendedor', f: r => esc(r.seller) }, { h: 'Cliente', f: r => esc(r.customer) }, { h: 'Base', num: 1, f: r => brl(r.base) }, { h: 'Comissão', num: 1, f: r => `<b class="${r.amount < 0 ? 'bad' : ''}">${brl(r.amount)}</b>` }, { h: 'Situação', f: r => badge(COMM_ST, r.status) + (r.kind === 'estorno' ? ' <span class="badge mut">estorno</span>' : '') }], d.rows, { empty: 'Nenhuma comissão no período.' })}`;
        const all = $('#ckall', view); if (all) all.onchange = () => $$('.ck', view).forEach(c => c.checked = all.checked);
        $$('[data-bulk]', view).forEach(b => b.onclick = async () => {
          const ids = $$('.ck:checked', view).map(c => +c.value); if (!ids.length) return toast('Selecione ao menos uma comissão', 'bad');
          if (!await confirmBox(`Alterar ${ids.length} comissão(ões) para “${b.dataset.bulk}”?`, { danger: b.dataset.bulk === 'cancelada' })) return;
          try { const r = await POST('/api/commissions/status', { ids, status: b.dataset.bulk }); toast(`${r.changed} comissão(ões) alterada(s)`, 'ok'); load(); } catch (e) { fail(e); }
        });
      };
      $('#fl', view).addEventListener('submit', e => { e.preventDefault(); load().catch(fail); }); await load();
    } else {
      const [rules, cats, prods, pkgs] = await Promise.all([GET('/api/commission-rules'), categories(), GET('/api/products'), GET('/api/packages')]);
      const SC = { default: 'Padrão', category: 'Categoria', product: 'Produto', package: 'Pacote' };
      const BASE = { line: 'Valor do item', total: 'Valor total', eligible: 'Itens elegíveis' };
      box.innerHTML = `<div class="note mb">Ordem de prioridade: pacote → produto → categoria → padrão. A regra aplicada fica gravada em cada venda; mudar regras não altera comissões já geradas.</div>
        <div class="card"><div class="card-h"><h3>Regras</h3><span class="grow"></span><button class="btn p" id="rnew">${ic('plus')} Nova regra</button></div>${table([{ h: 'Escopo', f: r => SC[r.scope] }, { h: 'Item', f: r => esc(r.ref_name || '—') }, { h: 'Comissão', num: 1, f: r => r.type === 'percent' ? pct(r.value) : brl(Math.round(r.value * 100)) }, { h: 'Base', f: r => BASE[r.base] || r.base }, { h: 'Situação', f: r => r.active ? '<span class="badge ok">Ativa</span>' : '<span class="badge mut">Inativa</span>' }, { h: '', f: r => `<span class="row"><button class="btn s g" data-act="redit" data-id="${r.id}">${ic('edit')}</button>${r.scope !== 'default' ? `<button class="btn s g" data-act="rdel" data-id="${r.id}">${ic('trash')}</button>` : ''}</span>` }], rules)}</div>`;
      const form = r => {
        const f = [{ name: 'scope', label: 'Aplicar a', type: 'select', options: Object.entries(SC).map(([v, l]) => ({ v, l })) }, { name: 'ref_id', label: 'Item', type: 'select', options: [] },
          { name: 'type', label: 'Tipo', type: 'select', options: [{ v: 'percent', l: 'Percentual (%)' }, { v: 'fixed', l: 'Valor fixo (R$)' }] }, { name: 'value', label: 'Valor (% ou R$)', type: 'number', min: 0, required: 1 },
          { name: 'base', label: 'Base de cálculo', type: 'select', options: Object.entries(BASE).map(([v, l]) => ({ v, l })) }, { name: 'note', label: 'Nota', max: 200 }, { name: 'active', label: 'Regra ativa', type: 'checkbox' }];
        const m = formModal({ title: r ? 'Editar regra' : 'Nova regra', fields: f, values: r || { scope: 'category', type: 'percent', base: 'line', active: 1 }, onSubmit: async (v, mm) => { await PUT('/api/commission-rules', v); mm.close(); toast('Regra salva', 'ok'); route(); } });
        const sc = $('[name=scope]', m), rf = $('[name=ref_id]', m);
        const fill = () => { const s = sc.value, src = s === 'category' ? cats : s === 'product' ? prods : s === 'package' ? pkgs : []; rf.innerHTML = src.map(x => `<option value="${x.id}" ${r && r.ref_id === x.id ? 'selected' : ''}>${esc(x.name)}</option>`).join(''); rf.disabled = s === 'default'; };
        sc.onchange = fill; fill(); if (r) sc.disabled = true;
        if (r) { sc.disabled = false; sc.onchange = null; sc.setAttribute('disabled', ''); const hid = document.createElement('input'); hid.type = 'hidden'; hid.name = 'scope'; hid.value = r.scope; sc.removeAttribute('name'); sc.after(hid); rf.setAttribute('disabled', ''); const h2 = document.createElement('input'); h2.type = 'hidden'; h2.name = 'ref_id'; h2.value = r.ref_id; rf.removeAttribute('name'); rf.after(h2); }
      };
      $('#rnew', view).onclick = () => form(null);
      ACT.redit = el => form(rules.find(x => x.id === +el.dataset.id));
      ACT.rdel = async el => { if (await confirmBox('Remover esta regra? Vendas já registradas não são afetadas.', { danger: true, ok: 'Remover' })) { try { await DEL('/api/commission-rules/' + el.dataset.id); route(); } catch (e) { fail(e); } } };
    }
  },
};

/* ------------------------------------------------ financeiro */
R.finance = {
  title: 'Financeiro', roles: A,
  async render(view, query, alive) {
    const tab = query.tab || 'cash';
    view.innerHTML = tabsHTML([['cash', 'Fluxo de caixa'], ['rec', 'Contas a receber'], ['pay', 'Contas a pagar']], tab) + '<div id="tab"></div>';
    $$('[data-tab]', view).forEach(b => b.onclick = () => { location.hash = '#/finance?tab=' + b.dataset.tab; });
    const box = $('#tab', view);
    const wide = { from: today().slice(0, 4) + '-01-01', to: (today().slice(0, 4) * 1 + 1) + '-12-31' };
    if (tab === 'cash') {
      box.innerHTML = `<div class="card"><form class="filters" id="fl">${periodFilters()}${sel('group', 'Agrupar por', [{ v: 'day', l: 'Dia' }, { v: 'month', l: 'Mês' }], 'day')}<button class="btn p">Atualizar</button></form><div id="res">${spinner}</div></div>`;
      const load = async () => {
        const d = await GET('/api/finance/cashflow', filterValues($('#fl', view))), t = d.totals;
        $('#res', view).innerHTML = `<div class="note mb">“Vendido” é o faturamento. “Recebido” é o dinheiro efetivamente entrado (parcelas pagas). Vendas a prazo não são caixa até serem recebidas.</div><div class="grid g5 mb"><div class="stat"><div class="l">Vendido</div><div class="v">${brl(t.sold)}</div></div><div class="stat good"><div class="l">Recebido</div><div class="v">${brl(t.received)}</div></div><div class="stat"><div class="l">Pago</div><div class="v">${brl(t.paid)}</div></div><div class="stat ${t.net >= 0 ? 'good' : 'badx'}"><div class="l">Saldo do período</div><div class="v">${brl(t.net)}</div></div><div class="stat"><div class="l">Previsto (entradas − saídas)</div><div class="v">${brl(t.expected_in - t.expected_out)}</div></div></div>
          ${barChart(d.rows.map(r => ({ label: r.key, short: r.key.slice(d.group === 'day' ? 8 : 5), value: Math.max(r.received, 0) })), { h: 140 })}
          ${table([{ h: d.group === 'day' ? 'Dia' : 'Mês', f: r => esc(d.group === 'day' ? fmtDate(r.key) : r.key) }, { h: 'Vendido', num: 1, f: r => brl(r.sold) }, { h: 'Recebido', num: 1, f: r => brl(r.received) }, { h: 'Pago', num: 1, f: r => brl(r.paid) }, { h: 'Saldo', num: 1, f: r => brl(r.balance) }, { h: 'A receber', num: 1, f: r => brl(r.expected_in) }, { h: 'A pagar', num: 1, f: r => brl(r.expected_out) }], d.rows, { empty: 'Sem movimentos no período.' })}`;
      };
      $('#fl', view).addEventListener('submit', e => { e.preventDefault(); load().catch(fail); }); await load();
    } else if (tab === 'rec') {
      const sellers = await sellerOpts();
      box.innerHTML = `<div class="card"><form class="filters" id="fl">${periodFilters(wide)}${sel('status', 'Situação', [{ v: '', l: 'Todas' }, { v: 'pendente', l: 'Pendentes' }, { v: 'atrasado', l: 'Atrasadas' }, { v: 'recebido', l: 'Recebidas' }], '')}${sel('seller_id', 'Vendedor', sellers, '')}<button class="btn p">Filtrar</button></form><div id="res">${spinner}</div></div>`;
      const load = async () => {
        const d = await GET('/api/finance/receivables', filterValues($('#fl', view)));
        $('#res', view).innerHTML = `<div class="grid g3 mb"><div class="stat"><div class="l">Pendente</div><div class="v">${brl(d.totals.pendente)}</div></div><div class="stat badx"><div class="l">Em atraso</div><div class="v">${brl(d.totals.atrasado)}</div></div><div class="stat good"><div class="l">Recebido</div><div class="v">${brl(d.totals.recebido)}</div></div></div>
          ${table([{ h: 'Venda', f: r => `<a href="#" data-act="sale" data-id="${r.sale_id}"><b>${esc(r.number)}</b></a>` }, { h: 'Cliente', f: r => esc(r.customer) }, { h: 'Parcela', f: r => r.installment_no ? `${r.installment_no}/${r.installments_total}` : 'Entrada' }, { h: 'Vencimento', f: r => fmtDate(r.due_date) }, { h: 'Valor', num: 1, f: r => brl(r.amount) }, { h: 'Situação', f: r => r.overdue ? '<span class="badge bad">Atrasada</span>' : r.status === 'recebido' ? '<span class="badge ok">Recebida</span>' : `<span class="badge ${r.status === 'pendente' ? 'warn' : 'mut'}">${esc(r.status)}</span>` }, { h: '', f: r => r.status === 'pendente' ? `<button class="btn s" data-act="recv" data-id="${r.id}">Receber</button>` : '' }], d.rows, { empty: 'Nenhuma parcela encontrada.' })}`;
      };
      ACT.recv = async el => { if (!await confirmBox('Confirmar o recebimento desta parcela?', { ok: 'Confirmar recebimento' })) return; try { await POST(`/api/finance/receivables/${el.dataset.id}/receive`); toast('Recebimento registrado', 'ok'); load(); } catch (e) { fail(e); } };
      $('#fl', view).addEventListener('submit', e => { e.preventDefault(); load().catch(fail); }); await load();
    } else {
      const sups = await GET('/api/suppliers');
      box.innerHTML = `<div class="card"><form class="filters" id="fl">${periodFilters(wide)}${sel('status', 'Situação', [{ v: '', l: 'Todas' }, { v: 'pendente', l: 'Pendentes' }, { v: 'atrasado', l: 'Atrasadas' }, { v: 'pago', l: 'Pagas' }], '')}<button class="btn p">Filtrar</button><button type="button" class="btn" id="pnew">${ic('plus')} Nova conta</button></form><div id="res">${spinner}</div></div>`;
      const F = [{ name: 'description', label: 'Descrição', required: 1, full: 1 }, { name: 'category', label: 'Categoria', type: 'select', options: [['despesa', 'Despesa operacional'], ['fornecedor', 'Fornecedor'], ['frete', 'Frete'], ['instalacao', 'Instalação'], ['outros', 'Outros']].map(([v, l]) => ({ v, l })) }, { name: 'amount', label: 'Valor', type: 'money', required: 1 }, { name: 'due_date', label: 'Vencimento', type: 'date', required: 1 }, { name: 'supplier_id', label: 'Fornecedor', type: 'select', options: [{ v: '', l: '—' }, ...sups.map(s => ({ v: s.id, l: s.name }))] }, { name: 'notes', label: 'Observações', type: 'textarea', full: 1 }];
      let rows = [];
      const load = async () => {
        const d = await GET('/api/finance/payables', filterValues($('#fl', view))); rows = d.rows;
        $('#res', view).innerHTML = `<div class="grid g3 mb"><div class="stat"><div class="l">Pendente</div><div class="v">${brl(d.totals.pendente)}</div></div><div class="stat badx"><div class="l">Em atraso</div><div class="v">${brl(d.totals.atrasado)}</div></div><div class="stat good"><div class="l">Pago</div><div class="v">${brl(d.totals.pago)}</div></div></div>
          ${table([{ h: 'Descrição', f: r => `<b>${esc(r.description)}</b><div class="xs muted">${esc(r.category)}${r.supplier ? ' · ' + esc(r.supplier) : ''}${r.sale_number ? ' · venda ' + esc(r.sale_number) : ''}</div>` }, { h: 'Vencimento', f: r => fmtDate(r.due_date) }, { h: 'Valor', num: 1, f: r => brl(r.amount) }, { h: 'Situação', f: r => r.overdue ? '<span class="badge bad">Atrasada</span>' : r.status === 'pago' ? '<span class="badge ok">Paga</span>' : `<span class="badge ${r.status === 'pendente' ? 'warn' : 'mut'}">${esc(r.status)}</span>` }, { h: '', f: r => r.status === 'pendente' ? `<span class="row nowrap"><button class="btn s" data-act="ppay" data-id="${r.id}">Pagar</button><button class="btn s g" data-act="pedit2" data-id="${r.id}">${ic('edit')}</button><button class="btn s g" data-act="pcancel" data-id="${r.id}">${ic('x')}</button></span>` : '' }], rows, { empty: 'Nenhuma conta encontrada.' })}`;
      };
      $('#pnew', view).onclick = () => formModal({ title: 'Nova conta a pagar', fields: [...F, { name: 'repeat', label: 'Repetir (meses)', type: 'number', min: 1, hint: '1 = conta única; até 36 parcelas mensais' }], values: { category: 'despesa', due_date: today(), repeat: 1 }, onSubmit: async (v, m) => { v.supplier_id = v.supplier_id || null; await POST('/api/finance/payables', v); m.close(); toast('Conta cadastrada', 'ok'); load(); } });
      ACT.pedit2 = el => { const r = rows.find(x => x.id === +el.dataset.id); formModal({ title: 'Editar conta', fields: F, values: r, onSubmit: async (v, m) => { v.supplier_id = v.supplier_id || null; await PUT('/api/finance/payables/' + r.id, v); m.close(); load(); } }); };
      ACT.ppay = async el => { if (!await confirmBox('Marcar esta conta como paga hoje?', { ok: 'Confirmar pagamento' })) return; try { await POST(`/api/finance/payables/${el.dataset.id}/pay`); toast('Pagamento registrado', 'ok'); load(); } catch (e) { fail(e); } };
      ACT.pcancel = async el => { if (!await confirmBox('Cancelar esta conta?', { danger: true })) return; try { await POST(`/api/finance/payables/${el.dataset.id}/cancel`); load(); } catch (e) { fail(e); } };
      $('#fl', view).addEventListener('submit', e => { e.preventDefault(); load().catch(fail); }); await load();
    }
  },
};

/* ------------------------------------------------ relatórios */
const REPORTS = [['sales', 'Vendas por período'], ['sales_by_seller', 'Vendas por vendedor'], ['sales_by_product', 'Vendas por produto e pacote'], ['stock', 'Estoque atual'], ['stock_movements', 'Movimentação do estoque'], ['costs_profit', 'Custos e lucro bruto estimado'], ['goals', 'Metas e desempenho'], ['commissions', 'Comissões'], ['receivables', 'Contas a receber'], ['payables', 'Contas a pagar']];
R.reports = {
  title: 'Relatórios', roles: A,
  async render(view, query) {
    const sellers = await sellerOpts();
    view.innerHTML = `<div class="card"><form class="filters" id="fl">${sel('name', 'Relatório', REPORTS.map(([v, l]) => ({ v, l })), query.name || 'sales')}${periodFilters({ from: today().slice(0, 4) + '-01-01' })}${sel('seller_id', 'Vendedor', sellers, '')}<button class="btn p">Gerar</button>
      <a class="btn" id="xl" href="#">${ic('download')} Excel</a><a class="btn" id="pdf" href="#">${ic('download')} PDF</a></form><div id="res">${spinner}</div></div>`;
    const fl = $('#fl', view);
    const fmt = (v, t) => v == null || v === '' ? '' : t === 'money' ? brl(v) : t === 'pct' ? pct(v) : t === 'qty' ? num(v) : t === 'date' ? fmtDate(v) : esc(v);
    const links = () => { const f = filterValues(fl), n = f.name; delete f.name; $('#xl', view).href = `/api/reports/${n}${qs({ ...f, format: 'xlsx' })}`; $('#pdf', view).href = `/api/reports/${n}${qs({ ...f, format: 'pdf' })}`; };
    const load = async () => {
      links(); const f = filterValues(fl), n = f.name; delete f.name;
      const r = await GET('/api/reports/' + n, f);
      $('#res', view).innerHTML = `<h3 class="mb">${esc(r.title)} <span class="muted sm">${fmtDate(r.period.from)} a ${fmtDate(r.period.to)}</span></h3>` +
        table(r.columns.map(c => ({ h: esc(c.label), cls: ['money', 'pct', 'qty', 'int', 'date'].includes(c.type) || /date|data/i.test(c.key) ? 'nowrap' : '', num: ['money', 'pct', 'qty', 'int'].includes(c.type), f: row => fmt(row[c.key], c.type) })), r.rows, { empty: 'Sem dados para os filtros escolhidos.',
          foot: Object.keys(r.totals || {}).length ? `<tr>${r.columns.map((c, i) => `<td class="${['money', 'pct', 'qty', 'int'].includes(c.type) ? 'num' : ''}"><b>${i === 0 ? 'Totais' : r.totals[c.key] != null ? fmt(r.totals[c.key], c.type) : ''}</b></td>`).join('')}</tr>` : '' });
    };
    fl.addEventListener('submit', e => { e.preventDefault(); load().catch(e2 => { $('#res', view).innerHTML = `<div class="errbox">${esc(e2.message)}</div>`; }); });
    fl.addEventListener('change', links);
    await load();
  },
};

/* ------------------------------------------------ usuários */
R.users = {
  title: 'Usuários', roles: A,
  async render(view) {
    const rows = await GET('/api/users');
    view.innerHTML = `<div class="card"><div class="card-h"><h3>Usuários do sistema</h3><span class="grow"></span><button class="btn p" id="unew">${ic('plus')} Novo usuário</button></div>${table([{ h: 'Nome', f: r => `<span class="row">${avatar(r)} <b>${esc(r.name)}</b></span>` }, { h: 'E-mail', f: r => esc(r.email) }, { h: 'Perfil', f: r => r.role === 'admin' ? '<span class="badge">Administrador</span>' : '<span class="badge mut">Vendedor</span>' }, { h: 'Situação', f: r => r.active ? '<span class="badge ok">Ativo</span>' : '<span class="badge bad">Inativo</span>' }, { h: '', f: r => `<button class="btn s g" data-act="uedit" data-id="${r.id}">${ic('edit')} Editar</button>` }], rows)}</div>`;
    const F = c => [{ name: 'name', label: 'Nome', required: 1, full: 1 }, { name: 'email', label: 'E-mail', type: 'email', required: 1 }, { name: 'phone', label: 'Telefone', type: 'tel' }, { name: 'role', label: 'Perfil', type: 'select', options: [{ v: 'vendedor', l: 'Vendedor' }, { v: 'admin', l: 'Administrador' }] }, { name: 'password', label: c ? 'Nova senha (opcional)' : 'Senha temporária (mín. 8)', type: 'password', required: !c, hint: 'O usuário deverá trocá-la no primeiro acesso.' }, ...(c ? [{ name: 'active', label: 'Usuário ativo', type: 'checkbox' }] : [])];
    $('#unew', view).onclick = () => formModal({ title: 'Novo usuário', fields: F(false), values: { role: 'vendedor' }, onSubmit: async (v, m) => { await POST('/api/users', v); m.close(); toast('Usuário criado', 'ok'); route(); } });
    ACT.uedit = el => { const u = rows.find(x => x.id === +el.dataset.id); formModal({ title: 'Editar usuário', fields: F(true), values: u, onSubmit: async (v, m) => { if (!v.password) delete v.password; await PUT('/api/users/' + u.id, v); m.close(); toast('Usuário atualizado', 'ok'); route(); } }); };
  },
};

/* ------------------------------------------------ configurações, backup e auditoria */
R.settings = {
  title: 'Configurações', roles: A,
  async render(view, query) {
    const tab = query.tab || 'store';
    view.innerHTML = tabsHTML([['store', 'Loja e regras'], ['backup', 'Backup'], ['audit', 'Registro de ações']], tab) + '<div id="tab"></div>';
    $$('[data-tab]', view).forEach(b => b.onclick = () => { location.hash = '#/settings?tab=' + b.dataset.tab; });
    const box = $('#tab', view);
    if (tab === 'store') {
      const st = await GET('/api/settings');
      box.innerHTML = `<div class="card"><form class="fgrid" id="sf" novalidate>${fieldHTML({ name: 'store_name', label: 'Nome da loja', required: 1 }, st.store_name)}${fieldHTML({ name: 'store_tagline', label: 'Slogan' }, st.store_tagline)}
        <div class="field full"><label>Logotipo</label><div class="row">${logoHTML()}<input type="file" id="logof" accept="image/png,image/jpeg,image/webp,image/svg+xml"><button type="button" class="btn s g" id="logorm">Remover</button></div><span class="hint">Imagem de até 300 KB.</span></div>
        ${fieldHTML({ name: 'seller_max_discount_pct', label: 'Desconto máximo do vendedor (% dos itens)', type: 'number', min: 0 }, st.seller_max_discount_pct)}
        ${fieldHTML({ name: 'commission_cancel_policy', label: 'Comissão de venda cancelada', type: 'select', options: [{ v: 'clawback', l: 'Estornar (descontar comissões já pagas)' }, { v: 'keep_paid', l: 'Manter comissões já pagas' }] }, st.commission_cancel_policy)}
        ${fieldHTML({ name: 'allow_oversell', label: 'Permitir vendas acima do estoque disponível', type: 'checkbox', full: 1 }, st.allow_oversell === '1')}
        <div class="errbox full" data-top hidden></div><div class="full"><button class="btn p" type="submit">Salvar configurações</button></div></form></div>`;
      let logo;
      $('#logof', view).onchange = e => { const f = e.target.files[0]; if (!f) return; const r = new FileReader(); r.onload = () => { logo = r.result; $('.logo', view).innerHTML = `<img src="${logo}" alt="">`; }; r.readAsDataURL(f); };
      $('#logorm', view).onclick = () => { logo = ''; $('.logo', view).innerHTML = ic('drop'); };
      $('#sf', view).addEventListener('submit', async e => {
        e.preventDefault(); const v = formValues(e.target), top = $('[data-top]', view); top.hidden = true;
        if (logo !== undefined) v.logo = logo;
        try { await PUT('/api/settings', v); const me = await GET('/api/me'); applyMe(me); startApp(); toast('Configurações salvas', 'ok'); } catch (er) { if (!showFieldError(e.target, er)) { top.textContent = er.message; top.hidden = false; } }
      });
    } else if (tab === 'backup') {
      const rows = await GET('/api/backups');
      box.innerHTML = `<div class="card"><div class="card-h"><h3>Cópias de segurança</h3><span class="grow"></span><button class="btn p" id="bk">${ic('download')} Criar backup agora</button></div><div class="note mb">O sistema cria um backup automático por dia e mantém os 14 mais recentes. Baixe cópias periodicamente e guarde fora do servidor.</div>
        ${table([{ h: 'Arquivo', f: r => esc(r.name) }, { h: 'Tamanho', num: 1, f: r => num(r.size / 1024, 0) + ' KB' }, { h: '', f: r => `<a class="btn s" href="/api/backups/${encodeURIComponent(r.name)}">${ic('download')} Baixar</a>` }], rows, { empty: 'Nenhum backup ainda.' })}</div>`;
      $('#bk', view).onclick = async () => { try { await POST('/api/backups'); toast('Backup criado', 'ok'); route(); } catch (e) { fail(e); } };
    } else {
      const rows = await GET('/api/audit');
      box.innerHTML = `<div class="card"><div class="card-h"><h3>Últimas 300 ações importantes</h3></div>${table([{ h: 'Data', f: r => fmtDT(r.created_at) }, { h: 'Usuário', f: r => esc(r.user_name || r.user_id || '—') }, { h: 'Ação', f: r => `<b>${esc(r.action)}</b>` }, { h: 'Alvo', f: r => esc((r.entity || '') + ' ' + (r.entity_id ?? '')) }, { h: 'Detalhes', f: r => `<span class="xs muted">${esc((r.detail || '').slice(0, 140))}</span>` }], rows, { empty: 'Sem registros.' })}</div>`;
    }
  },
};

NAV.push(
  { path: 'dashboard', label: 'Painel', icon: 'home', roles: A },
  { path: 'sale/new', label: 'Nova venda', icon: 'plus', roles: A, sep: 'Vendas' },
  { path: 'sales', label: 'Vendas', icon: 'cart', roles: A, sep: 'Vendas' },
  { path: 'customers', label: 'Clientes', icon: 'users', roles: A, sep: 'Vendas' },
  { path: 'products', label: 'Produtos e estoque', icon: 'box', roles: A, sep: 'Catálogo' },
  { path: 'packages', label: 'Pacotes', icon: 'layers', roles: A, sep: 'Catálogo' },
  { path: 'goals', label: 'Metas', icon: 'target', roles: A, sep: 'Equipe' },
  { path: 'commissions', label: 'Comissões', icon: 'percent', roles: A, sep: 'Equipe' },
  { path: 'finance', label: 'Financeiro', icon: 'wallet', roles: A, sep: 'Gestão' },
  { path: 'reports', label: 'Relatórios', icon: 'file', roles: A, sep: 'Gestão' },
  { path: 'users', label: 'Usuários', icon: 'user', roles: A, sep: 'Sistema' },
  { path: 'settings', label: 'Configurações', icon: 'settings', roles: A, sep: 'Sistema' },
);
