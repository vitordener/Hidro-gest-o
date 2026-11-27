"""Regras de negócio: venda, pacotes, comissões, metas, estoque, parcelas, cancelamento."""
import calendar
import json
import math
import uuid
from datetime import datetime, timedelta

from db import q, q1, now, now_s, today_s, get_settings


class ApiError(Exception):
    def __init__(self, msg, status=400, field=None):
        super().__init__(msg)
        self.msg, self.status, self.field = msg, status, field


PAY_IMMEDIATE = {"dinheiro", "pix", "debito"}
PAY_METHODS = {"dinheiro", "pix", "debito", "cartao_credito", "boleto", "carne", "transferencia"}


def rnd(x):
    return int(math.floor(x + 0.5))


def to_int(v, name, minv=0, maxv=10**12):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ApiError(f"{name} inválido", field=name)
    if n < minv or n > maxv:
        raise ApiError(f"{name} fora do intervalo permitido", field=name)
    return n


def to_qty(v, name="quantidade"):
    try:
        n = round(float(v), 3)
    except (TypeError, ValueError):
        raise ApiError(f"{name} inválida", field=name)
    if n <= 0 or n > 1_000_000:
        raise ApiError(f"{name} deve ser maior que zero", field=name)
    return n


def allocate(total, weights):
    """Distribui `total` (centavos) proporcionalmente a `weights`; soma exata."""
    n = len(weights)
    if n == 0:
        return []
    s = sum(weights)
    if s <= 0:
        weights, s = [1] * n, n
    res = [rnd(total * w / s) for w in weights]
    diff = total - sum(res)
    if diff:
        res[max(range(n), key=lambda i: weights[i])] += diff
    return res


def add_months(datestr, k):
    d = datetime.strptime(datestr, "%Y-%m-%d")
    m = d.month - 1 + k
    y, m = d.year + m // 12, m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return f"{y:04d}-{m:02d}-{day:02d}"


def month_bounds(month):
    """'YYYY-MM' -> (início, fim exclusivo) em 'YYYY-MM-DD'."""
    import re
    if not isinstance(month, str) or not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
        raise ApiError("Mês inválido (use AAAA-MM)", field="month")
    start = month + "-01"
    end = add_months(start, 1)
    return start, end


def next_day(d):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def period(args):
    import re
    f = args.get("from") or today_s()[:8] + "01"
    t = args.get("to") or today_s()
    for x in (f, t):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", x):
            raise ApiError("Data inválida (AAAA-MM-DD)")
    if f > t:
        raise ApiError("Data inicial maior que a final")
    return f, t, f + " 00:00:00", next_day(t) + " 00:00:00"


def audit(db, user, action, entity=None, entity_id=None, detail=None, ip=None):
    db.execute(
        "INSERT INTO audit_log(user_id,user_name,action,entity,entity_id,detail,ip,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (user["id"] if user else None, user["name"] if user else None, action, entity,
         None if entity_id is None else str(entity_id),
         json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else detail, ip, now_s()),
    )


# ---------------------------------------------------------------- comissões
def resolve_rule(db, product):
    for scope, ref in (("product", product["id"]), ("category", product["category_id"] or -1), ("default", 0)):
        r = q1(db, "SELECT * FROM commission_rules WHERE scope=? AND ref_id=? AND active=1", (scope, ref))
        if r:
            return r
    return None


def calc_amount(rule, base, qty):
    if not rule:
        return 0
    if rule["type"] == "percent":
        return rnd(base * rule["value"] / 100.0)
    return rnd(rule["value"] * 100 * qty)  # fixa = valor em reais por unidade -> centavos


# ---------------------------------------------------------------- venda
def build_sale(db, seller, payload, actor):
    """Calcula tudo a partir do banco (preços vindos do servidor, nunca do cliente). Não grava."""
    st = get_settings(db)
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ApiError("Adicione ao menos um item à venda", field="items")
    if len(items) > 100:
        raise ApiError("Itens demais na venda")

    cust = q1(db, "SELECT * FROM customers WHERE id=?", (payload.get("customer_id"),))
    if not cust:
        raise ApiError("Selecione o cliente", field="customer_id")
    if actor["role"] != "admin":
        ok = cust["created_by"] == actor["id"] or q1(
            db, "SELECT 1 x FROM sales WHERE customer_id=? AND seller_id=?", (cust["id"], actor["id"]))
        if not ok:
            raise ApiError("Cliente não disponível para este usuário", 403)

    cache = {}

    def getp(pid, must_active=True):
        if pid not in cache:
            cache[pid] = q1(db, "SELECT * FROM products WHERE id=?", (pid,))
        p = cache[pid]
        if not p:
            raise ApiError("Produto não encontrado", 404)
        if must_active and not p["active"]:
            raise ApiError(f"Produto inativo: {p['name']}")
        return p

    rev_lines = []   # linhas que geram receita (produto avulso ou cabeçalho de pacote)
    need = {}        # product_id -> quantidade física a baixar

    def pct_of(v, amount):
        """Desconto em % -> centavos (arredonda para baixo, para a soma nunca passar do limite do vendedor)."""
        try:
            pct = float(v)
        except (TypeError, ValueError):
            raise ApiError("Percentual de desconto inválido", field="discount")
        if not 0 <= pct <= 100:
            raise ApiError("Percentual de desconto deve ficar entre 0 e 100", field="discount")
        return math.floor(amount * pct / 100.0 + 1e-9)

    def line_disc(it, line_total):
        if it.get("discount_pct"):
            return pct_of(it["discount_pct"], line_total)
        d = to_int(it.get("discount") or 0, "desconto do item")
        if d > line_total:
            raise ApiError("Desconto do item maior que o valor do item", field="discount")
        return d

    def need_add(p, qty):
        if p["kind"] == "product":
            need[p["id"]] = round(need.get(p["id"], 0) + qty, 3)

    for it in items:
        t = it.get("type")
        if t == "product":
            p = getp(it.get("product_id"))
            qty = to_qty(it.get("qty"))
            lt = rnd(qty * p["sale_price"])
            rev_lines.append({
                "kind": "product", "product": p, "name": p["name"], "qty": qty,
                "unit_price": p["sale_price"], "unit_cost": p["cost_price"],
                "line_total": lt, "discount": line_disc(it, lt), "cost_total": rnd(qty * p["cost_price"]),
                "comps": [],
            })
            need_add(p, qty)
        elif t == "package":
            pkg = q1(db, "SELECT * FROM packages WHERE id=? AND active=1", (it.get("package_id"),))
            if not pkg:
                raise ApiError("Pacote não encontrado ou inativo", 404)
            pq = to_qty(it.get("qty", 1), "quantidade do pacote")
            if pq != int(pq):
                raise ApiError("Quantidade de pacotes deve ser inteira")
            pq = int(pq)
            pitems = q(db, "SELECT * FROM package_items WHERE package_id=? ORDER BY id", (pkg["id"],))
            removed = set(int(x) for x in (it.get("removed") or []))
            by_id = {pi["id"]: pi for pi in pitems}
            for rid in removed:
                if rid not in by_id or not by_id[rid]["removable"]:
                    raise ApiError("Item do pacote não pode ser removido")
            price = pkg["sale_price"]
            comps, cost_unit = [], 0
            for pi in pitems:
                if pi["id"] in removed:
                    price -= rnd(pi["price_alloc"] * pi["qty"])
                    continue
                p = getp(pi["product_id"], must_active=False)
                uc = pi["cost_override"] if pi["cost_override"] is not None else p["cost_price"]
                tq = round(pi["qty"] * pq, 3)
                comps.append({"product": p, "name": p["name"], "qty": tq, "unit_cost": uc,
                              "cost_total": rnd(tq * uc), "alloc": pi["price_alloc"] * pi["qty"],
                              "eligible": pi["commission_eligible"]})
                cost_unit += rnd(pi["qty"] * uc)
                need_add(p, tq)
            if price < 0:
                raise ApiError("Preço do pacote inválido após remoções")
            rev_lines.append({
                "kind": "package", "package": pkg, "name": pkg["name"], "qty": pq,
                "unit_price": price, "unit_cost": cost_unit, "line_total": price * pq,
                "discount": line_disc(it, price * pq),
                "cost_total": sum(c["cost_total"] for c in comps), "comps": comps,
            })
            extras = it.get("extras") or []
            if extras and not pkg["allow_extras"]:
                raise ApiError("Este pacote não aceita itens adicionais")
            for ex in extras:
                p = getp(ex.get("product_id"))
                qty = to_qty(ex.get("qty"))
                lt = rnd(qty * p["sale_price"])
                rev_lines.append({
                    "kind": "product", "product": p, "name": p["name"] + " (adicional)", "qty": qty,
                    "unit_price": p["sale_price"], "unit_cost": p["cost_price"],
                    "line_total": lt, "discount": line_disc(ex, lt), "cost_total": rnd(qty * p["cost_price"]),
                    "comps": [],
                })
                need_add(p, qty)
        else:
            raise ApiError("Tipo de item inválido")

    gross = sum(l["line_total"] for l in rev_lines)
    # desconto: por item (já em cada linha) + geral sobre o total; `discount` é a soma dos dois
    items_discount = sum(l["discount"] for l in rev_lines)
    if payload.get("discount_pct"):
        general_discount = pct_of(payload["discount_pct"], gross - items_discount)
    else:
        general_discount = to_int(payload.get("discount") or 0, "desconto")
    if general_discount > gross - items_discount:
        raise ApiError("Desconto maior que o valor dos itens", field="discount")
    discount = items_discount + general_discount
    if actor["role"] != "admin":
        lim = float(st.get("seller_max_discount_pct", 0) or 0)
        if discount > math.floor(gross * lim / 100.0):
            raise ApiError(f"Desconto acima do limite autorizado ({lim:g}% dos itens, somando descontos por item e geral). "
                           "Solicite ao administrador.", 403, "discount")
    net_items = gross - discount
    # o desconto geral é rateado pelo valor de cada linha já com o desconto do próprio item
    nets = allocate(net_items, [l["line_total"] - l["discount"] for l in rev_lines])
    for l, n in zip(rev_lines, nets):
        l["net"] = n

    freight = to_int(payload.get("freight", 0), "frete")
    install = to_int(payload.get("install", 0), "instalação")
    other = to_int(payload.get("other", 0), "outros")
    total = net_items + freight + install + other

    # receita alocada por componente de pacote
    for l in rev_lines:
        if l["kind"] == "package":
            ws = [c["alloc"] for c in l["comps"]]
            if sum(ws) <= 0:
                ws = [c["cost_total"] for c in l["comps"]]
            for c, n in zip(l["comps"], allocate(l["net"], ws)):
                c["net"] = n

    # comissão
    comm_lines, comm_total, comm_base = [], 0, 0
    for l in rev_lines:
        if l["kind"] == "product":
            rule = resolve_rule(db, l["product"])
            base = l["net"]
            amount = calc_amount(rule, base, l["qty"])
            src = None if not rule else rule["scope"]
        else:
            rule = (q1(db, "SELECT * FROM commission_rules WHERE scope='package' AND ref_id=? AND active=1", (l["package"]["id"],))
                    or q1(db, "SELECT * FROM commission_rules WHERE scope='default' AND ref_id=0 AND active=1"))
            if rule and rule["base"] == "eligible":
                base = sum(c["net"] for c in l["comps"] if c["eligible"])
            else:
                base = l["net"]
            amount = calc_amount(rule, base, l["qty"])
            src = rule["scope"] if rule else None
        comm_base += base if rule else 0
        comm_total += amount
        comm_lines.append({
            "item": l["name"], "rule_id": rule["id"] if rule else None, "rule_scope": src,
            "type": rule["type"] if rule else None, "value": rule["value"] if rule else None,
            "base_mode": rule["base"] if rule else None, "base": base, "amount": amount,
            "note": None if rule else "sem regra de comissão",
        })

    # pagamento
    method = payload.get("payment_method")
    if method not in PAY_METHODS:
        raise ApiError("Selecione a forma de pagamento", field="payment_method")
    inst = 1 if method in PAY_IMMEDIATE else to_int(payload.get("installments", 1), "parcelas", 1, 24)
    down = 0
    if method not in PAY_IMMEDIATE:
        down = to_int(payload.get("down_payment", 0), "entrada")
        if down >= total and total > 0:
            raise ApiError("Entrada deve ser menor que o total", field="down_payment")
    if total <= 0 and gross > 0:
        raise ApiError("Total da venda deve ser maior que zero")

    cost_total = sum(l["cost_total"] for l in rev_lines)
    return {
        "customer": cust, "lines": rev_lines, "need": need, "gross": gross, "discount": discount,
        "items_discount": items_discount, "general_discount": general_discount,
        "freight": freight, "install": install, "other": other, "total": total,
        "cost_total": cost_total, "gross_profit": total - cost_total,
        "costs_confirmed": 0 if (freight + install + other) > 0 else 1,
        "commission": {"amount": comm_total, "base": comm_base, "lines": comm_lines},
        "payment_method": method, "installments": inst, "down_payment": down,
        "notes": (payload.get("notes") or "").strip()[:1000],
        "stock_issues": stock_issues(db, need),
    }


def stock_issues(db, need):
    out = []
    for pid, qty in need.items():
        p = q1(db, "SELECT name, stock_qty, unit FROM products WHERE id=?", (pid,))
        if p["stock_qty"] + 1e-9 < qty:
            out.append({"product_id": pid, "name": p["name"], "available": p["stock_qty"], "needed": qty, "unit": p["unit"]})
    return out


def commit_sale(db, plan, seller, actor, idem_key=None, created_at=None, allow_oversell_override=None):
    """Grava venda + itens + estoque + comissão + parcelas. Chamar dentro de tx()."""
    st = get_settings(db)
    if idem_key:
        dup = q1(db, "SELECT id FROM sales WHERE idem_key=?", (idem_key,))
        if dup:
            return dup["id"], True
    issues = stock_issues(db, plan["need"])  # releitura já dentro da transação (lock de escrita)
    allow = st.get("allow_oversell") == "1" if allow_oversell_override is None else allow_oversell_override
    if issues and not allow:
        msg = "; ".join(f"{i['name']}: disponível {i['available']:g}, necessário {i['needed']:g}" for i in issues)
        raise ApiError("Estoque insuficiente — " + msg, 409)

    ts = created_at or now_s()
    day = ts[:10]
    cur = db.execute(
        """INSERT INTO sales(number,idem_key,customer_id,seller_id,status,subtotal,discount,freight,install,other,total,
           cost_total,costs_confirmed,gross_profit,payment_method,installments,down_payment,notes,created_at)
           VALUES(?,?,?,?, 'confirmed',?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("tmp-" + uuid.uuid4().hex, idem_key, plan["customer"]["id"], seller["id"], plan["gross"], plan["discount"],
         plan["freight"], plan["install"], plan["other"], plan["total"], plan["cost_total"], plan["costs_confirmed"],
         plan["gross_profit"], plan["payment_method"], plan["installments"], plan["down_payment"], plan["notes"], ts),
    )
    sid = cur.lastrowid
    number = f"V{ts[:4]}-{sid:06d}"
    db.execute("UPDATE sales SET number=? WHERE id=?", (number, sid))

    for l in plan["lines"]:
        if l["kind"] == "product":
            db.execute(
                "INSERT INTO sale_items(sale_id,kind,product_id,name,qty,unit_price,line_total,discount,net_revenue,unit_cost,cost_total) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (sid, "product", l["product"]["id"], l["name"], l["qty"], l["unit_price"], l["line_total"], l["discount"], l["net"],
                 l["unit_cost"], l["cost_total"]))
        else:
            pid = db.execute(
                "INSERT INTO sale_items(sale_id,kind,package_id,name,qty,unit_price,line_total,discount,net_revenue,unit_cost,cost_total) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (sid, "package", l["package"]["id"], l["name"], l["qty"], l["unit_price"], l["line_total"], l["discount"], l["net"],
                 l["unit_cost"], l["cost_total"])).lastrowid
            for c in l["comps"]:
                db.execute(
                    "INSERT INTO sale_items(sale_id,parent_id,kind,product_id,name,qty,unit_price,line_total,net_revenue,unit_cost,cost_total) "
                    "VALUES(?,?,?,?,?,?,0,0,?,?,?)",
                    (sid, pid, "component", c["product"]["id"], c["name"], c["qty"], c["net"], c["unit_cost"], c["cost_total"]))

    # baixa de estoque: UMA vez por produto físico (já agregado em plan["need"])
    for pid, qty in plan["need"].items():
        bal = db.execute("SELECT stock_qty FROM products WHERE id=?", (pid,)).fetchone()[0] - qty
        db.execute("UPDATE products SET stock_qty=? WHERE id=?", (round(bal, 3), pid))
        db.execute(
            "INSERT INTO stock_movements(product_id,type,qty,balance_after,reason,sale_id,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (pid, "venda", -qty, round(bal, 3), f"Venda {number}", sid, actor["id"], ts))

    c = plan["commission"]
    db.execute(
        "INSERT INTO sale_commissions(sale_id,seller_id,kind,base,amount,status,snapshot,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (sid, seller["id"], "normal", c["base"], c["amount"], "prevista", json.dumps(c["lines"], ensure_ascii=False), ts))

    # parcelas / recebimentos (venda a prazo NÃO entra como caixa recebido)
    total, m, n, dp = plan["total"], plan["payment_method"], plan["installments"], plan["down_payment"]
    if m in PAY_IMMEDIATE:
        db.execute("INSERT INTO receivables(sale_id,installment_no,installments_total,due_date,amount,method,status,received_at) "
                   "VALUES(?,?,?,?,?,?,'recebido',?)", (sid, 1, 1, day, total, m, ts))
    else:
        if dp > 0:
            db.execute("INSERT INTO receivables(sale_id,installment_no,installments_total,due_date,amount,method,status,received_at) "
                       "VALUES(?,?,?,?,?,?,'recebido',?)", (sid, 0, n, day, dp, "entrada", ts))
        # vencimentos mensais: 1ª parcela daqui a 1 mês (cartão liquida mês a mês)
        for i, amt in enumerate(allocate(total - dp, [1] * n), start=1):
            db.execute("INSERT INTO receivables(sale_id,installment_no,installments_total,due_date,amount,method,status) "
                       "VALUES(?,?,?,?,?,?,'pendente')", (sid, i, n, add_months(day, i), amt, m))

    audit(db, actor, "venda.criar", "sale", sid, {"number": number, "total": plan["total"], "seller_id": seller["id"]})
    return sid, False


def cancel_sale(db, sale_id, actor, status="cancelled", reason=""):
    st = get_settings(db)
    sale = q1(db, "SELECT * FROM sales WHERE id=?", (sale_id,))
    if not sale:
        raise ApiError("Venda não encontrada", 404)
    if sale["status"] != "confirmed":
        raise ApiError("Venda já cancelada/estornada")
    if status not in ("cancelled", "refunded"):
        raise ApiError("Status inválido")
    ts = now_s()
    db.execute("UPDATE sales SET status=?, cancelled_at=?, cancel_reason=?, cancelled_by=? WHERE id=?",
               (status, ts, reason[:500], actor["id"], sale_id))
    # devolve estoque de itens físicos (avulsos + componentes), uma vez por produto
    ret = {}
    for r in q(db, "SELECT si.product_id, SUM(si.qty) qty FROM sale_items si JOIN products p ON p.id=si.product_id "
                   "WHERE si.sale_id=? AND si.kind IN ('product','component') AND p.kind='product' GROUP BY si.product_id", (sale_id,)):
        ret[r["product_id"]] = r["qty"]
    for pid, qty in ret.items():
        bal = round(db.execute("SELECT stock_qty FROM products WHERE id=?", (pid,)).fetchone()[0] + qty, 3)
        db.execute("UPDATE products SET stock_qty=? WHERE id=?", (bal, pid))
        db.execute("INSERT INTO stock_movements(product_id,type,qty,balance_after,reason,sale_id,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                   (pid, "estorno", qty, bal, f"{'Estorno' if status=='refunded' else 'Cancelamento'} da venda {sale['number']}", sale_id, actor["id"], ts))
    # recebimentos
    paid = db.execute("SELECT COALESCE(SUM(amount),0) FROM receivables WHERE sale_id=? AND status='recebido'", (sale_id,)).fetchone()[0]
    db.execute("UPDATE receivables SET status='cancelado' WHERE sale_id=? AND status='pendente'", (sale_id,))
    db.execute("UPDATE receivables SET status='estornado' WHERE sale_id=? AND status='recebido'", (sale_id,))
    if paid > 0:
        db.execute("INSERT INTO payables(description,category,sale_id,amount,due_date,status,created_at) VALUES(?,?,?,?,?,'pendente',?)",
                   (f"Devolução ao cliente — venda {sale['number']}", "estorno", sale_id, paid, today_s(), ts))
    # comissões conforme política
    policy = st.get("commission_cancel_policy", "clawback")
    cm = q1(db, "SELECT * FROM sale_commissions WHERE sale_id=? AND kind='normal'", (sale_id,))
    if cm:
        if cm["status"] in ("prevista", "aprovada"):
            db.execute("UPDATE sale_commissions SET status='cancelada' WHERE id=?", (cm["id"],))
        elif cm["status"] == "paga" and policy == "clawback" and cm["amount"] > 0:
            db.execute(
                "INSERT OR IGNORE INTO sale_commissions(sale_id,seller_id,kind,base,amount,status,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (sale_id, cm["seller_id"], "estorno", 0, -cm["amount"], "prevista",
                 f"Estorno de comissão já paga — venda {sale['number']}", ts))
    audit(db, actor, "venda.cancelar", "sale", sale_id, {"status": status, "reason": reason, "devolvido": paid})


# ---------------------------------------------------------------- metas
def seller_month(db, seller_id, month):
    start, end = month_bounds(month)
    r = q1(db, "SELECT COALESCE(SUM(total),0) sold, COUNT(*) n FROM sales WHERE seller_id=? AND status='confirmed' "
               "AND created_at>=? AND created_at<?", (seller_id, start, end))
    g = q1(db, "SELECT amount FROM goals WHERE seller_id=? AND month=?", (seller_id, month))
    goal = g["amount"] if g else None
    pct = round(r["sold"] * 100.0 / goal, 1) if goal else None
    return {"month": month, "goal": goal, "sold": r["sold"], "count": r["n"],
            "remaining": max(goal - r["sold"], 0) if goal is not None else None, "pct": pct}


def milestone(pct):
    if pct is None:
        return None
    for lim in (100, 90, 75, 50):
        if pct >= lim:
            return lim
    return 0


def seller_dashboard(db, seller_id):
    month = now().strftime("%Y-%m")
    d = seller_month(db, seller_id, month)
    start, end = month_bounds(month)
    comm = {"prevista": 0, "aprovada": 0, "paga": 0}
    for r in q(db, "SELECT sc.status, SUM(sc.amount) a FROM sale_commissions sc JOIN sales s ON s.id=sc.sale_id "
                   "WHERE sc.seller_id=? AND s.created_at>=? AND s.created_at<? AND sc.status<>'cancelada' GROUP BY sc.status",
               (seller_id, start, end)):
        comm[r["status"]] = r["a"]
    d["commission"] = comm
    d["milestone"] = milestone(d["pct"])
    d["recent"] = q(db, "SELECT s.id, s.number, s.created_at, s.total, s.status, c.name customer FROM sales s "
                        "JOIN customers c ON c.id=s.customer_id WHERE s.seller_id=? ORDER BY s.id DESC LIMIT 8", (seller_id,))
    return d
