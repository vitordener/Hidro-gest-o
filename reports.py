"""Dashboards, financeiro e relatórios (JSON / Excel / PDF). Somente administrador."""
import io
from datetime import datetime

from db import q, q1, today_s, now
import logic as L
from logic import ApiError, period

STATUS_SALE = {"confirmed": "Confirmada", "cancelled": "Cancelada", "refunded": "Estornada"}
PAY = {"dinheiro": "Dinheiro", "pix": "Pix", "debito": "Débito", "cartao_credito": "Cartão de crédito", "boleto": "Boleto",
       "carne": "Carnê", "transferencia": "Transferência", "entrada": "Entrada"}
MOVE = {"entrada": "Entrada", "saida": "Saída", "ajuste": "Ajuste", "venda": "Venda", "estorno": "Estorno/cancelamento"}


def brl(c):
    s = f"{abs(c) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if c < 0 else "") + "R$ " + s


def _sale_where(a, alias="s"):
    f, t, t0, t1 = period(a)
    w, p = [f"{alias}.status='confirmed'", f"{alias}.created_at>=?", f"{alias}.created_at<?"], [t0, t1]
    if a.get("seller_id"):
        w.append(f"{alias}.seller_id=?"); p.append(a["seller_id"])
    return w, p, (f, t, t0, t1)


def _item_filters(a):
    w, p = [], []
    if a.get("category_id"):
        w.append("p.category_id=?"); p.append(a["category_id"])
    if a.get("product_id"):
        w.append("si.product_id=?"); p.append(a["product_id"])
    return w, p


# ---------------------------------------------------------------- dashboard
def admin_dashboard(db, a):
    w, p, (f, t, t0, t1) = _sale_where(a)
    item_mode = bool(a.get("category_id") or a.get("product_id"))
    iw, ip_ = _item_filters(a)
    item_join = ("FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id "
                 "WHERE si.kind IN ('product','component') AND " + " AND ".join(w + iw))
    if item_mode:
        r = q1(db, "SELECT COALESCE(SUM(si.net_revenue),0) revenue, COUNT(DISTINCT s.id) n, COALESCE(SUM(si.cost_total),0) cost " + item_join, p + ip_)
        r["profit"] = r["revenue"] - r["cost"]
        series = q(db, "SELECT substr(s.created_at,1,10) day, SUM(si.net_revenue) value " + item_join + " GROUP BY day ORDER BY day", p + ip_)
    else:
        r = q1(db, "SELECT COALESCE(SUM(total),0) revenue, COUNT(*) n, COALESCE(SUM(cost_total+freight_cost+install_cost+other_cost),0) cost, "
                   "COALESCE(SUM(gross_profit),0) profit FROM sales s WHERE " + " AND ".join(w), p)
        series = q(db, "SELECT substr(created_at,1,10) day, SUM(total) value FROM sales s WHERE " + " AND ".join(w) + " GROUP BY day ORDER BY day", p)
    r["ticket"] = r["revenue"] // r["n"] if r["n"] else 0

    sw = ["status='confirmed'"] + (["seller_id=?"] if a.get("seller_id") else [])
    sp = [a["seller_id"]] if a.get("seller_id") else []
    today, month = today_s(), today_s()[:7]
    ms, me = L.month_bounds(month)
    rev_today = q1(db, f"SELECT COALESCE(SUM(total),0) v, COUNT(*) n FROM sales WHERE {' AND '.join(sw)} AND created_at>=? AND created_at<?",
                   sp + [today + " 00:00:00", L.next_day(today) + " 00:00:00"])
    rev_month = q1(db, f"SELECT COALESCE(SUM(total),0) v, COUNT(*) n FROM sales WHERE {' AND '.join(sw)} AND created_at>=? AND created_at<?", sp + [ms, me])

    gm = t[:7]
    sellers = []
    for u in q(db, "SELECT id,name,avatar FROM users WHERE role='vendedor' AND active=1" + (" AND id=?" if a.get("seller_id") else "") + " ORDER BY name",
               [a["seller_id"]] if a.get("seller_id") else []):
        per = q1(db, "SELECT COALESCE(SUM(total),0) sold, COUNT(*) n, COALESCE(SUM(gross_profit),0) profit FROM sales WHERE seller_id=? AND status='confirmed' "
                     "AND created_at>=? AND created_at<?", (u["id"], t0, t1))
        sm = L.seller_month(db, u["id"], gm)
        sellers.append({"id": u["id"], "name": u["name"], "avatar": u["avatar"], "sold": per["sold"], "count": per["n"], "profit": per["profit"],
                        "goal_month": gm, "goal": sm["goal"], "month_sold": sm["sold"], "pct": sm["pct"]})
    with_goal = [s for s in sellers if s["goal"]]
    goals = {"month": gm, "achieved": sum(1 for s in with_goal if s["pct"] >= 100), "pending": sum(1 for s in with_goal if s["pct"] < 100),
             "without_goal": len(sellers) - len(with_goal)}

    cw, cp = ["s.created_at>=?", "s.created_at<?"], [t0, t1]
    if a.get("seller_id"):
        cw.append("sc.seller_id=?"); cp.append(a["seller_id"])
    comm = {"prevista": 0, "aprovada": 0, "paga": 0}
    for row in q(db, "SELECT sc.status, SUM(sc.amount) v FROM sale_commissions sc JOIN sales s ON s.id=sc.sale_id WHERE " + " AND ".join(cw) +
                     " AND sc.status<>'cancelada' GROUP BY sc.status", cp):
        comm[row["status"]] = row["v"]

    rj = "FROM receivables r JOIN sales s ON s.id=r.sale_id WHERE 1=1" + (" AND s.seller_id=?" if a.get("seller_id") else "")
    rp = [a["seller_id"]] if a.get("seller_id") else []
    received = q1(db, f"SELECT COALESCE(SUM(r.amount),0) v {rj} AND r.status IN ('recebido','estornado') AND r.received_at>=? AND r.received_at<?", rp + [t0, t1])["v"]
    paid_out = q1(db, "SELECT COALESCE(SUM(amount),0) v FROM payables WHERE status='pago' AND paid_at>=? AND paid_at<?", (t0, t1))["v"]
    comm_paid = q1(db, "SELECT COALESCE(SUM(amount),0) v FROM sale_commissions WHERE status='paga' AND paid_at>=? AND paid_at<?", (t0, t1))["v"]
    to_receive = q1(db, f"SELECT COALESCE(SUM(r.amount),0) v, COALESCE(SUM(CASE WHEN r.due_date<? THEN r.amount END),0) late {rj} AND r.status='pendente'", [today_s()] + rp)
    to_pay = q1(db, "SELECT COALESCE(SUM(amount),0) v, COALESCE(SUM(CASE WHEN due_date<? THEN amount END),0) late FROM payables WHERE status='pendente'", (today_s(),))
    comm_due = q1(db, "SELECT COALESCE(SUM(amount),0) v FROM sale_commissions WHERE status='aprovada'")["v"]

    top = q(db, "SELECT si.product_id, si.name, SUM(si.qty) qty, SUM(si.net_revenue) revenue " + item_join + " GROUP BY si.product_id ORDER BY revenue DESC LIMIT 8", p + ip_)
    low = q(db, "SELECT p.id,p.sku,p.name,p.stock_qty,p.min_stock,p.unit FROM products p WHERE p.kind='product' AND p.active=1 AND p.stock_qty<=p.min_stock ORDER BY (p.stock_qty-p.min_stock) LIMIT 10")
    moves = q(db, "SELECT m.created_at,m.type,m.qty,m.balance_after,m.reason,p.name product,p.unit,u.name user FROM stock_movements m JOIN products p ON p.id=m.product_id "
                  "LEFT JOIN users u ON u.id=m.user_id ORDER BY m.id DESC LIMIT 10")
    return {
        "period": {"from": f, "to": t}, "scope": "itens" if item_mode else "vendas",
        "kpi": {"revenue": r["revenue"], "count": r["n"], "ticket": r["ticket"], "cost": r["cost"], "gross_profit": r["profit"],
                "margin": round(r["profit"] * 100.0 / r["revenue"], 1) if r["revenue"] else 0,
                "today": rev_today, "month": rev_month},
        "cash": {"received": received, "paid": paid_out + comm_paid, "result": received - paid_out - comm_paid,
                 "to_receive": to_receive["v"], "to_receive_late": to_receive["late"], "to_pay": to_pay["v"], "to_pay_late": to_pay["late"],
                 "commissions_due": comm_due},
        "commissions": comm, "sellers": sellers, "goals": goals, "series": series, "top_products": top, "low_stock": low, "movements": moves,
        "alerts": {"costs_unconfirmed": q1(db, "SELECT COUNT(*) n FROM sales WHERE status='confirmed' AND costs_confirmed=0")["n"],
                   "low_stock": len(low)},
    }


# ---------------------------------------------------------------- financeiro
def receivables(db, a):
    f, t, *_ = period({"from": a.get("from") or "2000-01-01", "to": a.get("to") or "2999-12-31"})
    w, p = ["r.due_date>=?", "r.due_date<=?"], [f, t]
    st = a.get("status")
    if st == "atrasado":
        w.append("r.status='pendente' AND r.due_date<?"); p.append(today_s())
    elif st in ("pendente", "recebido", "cancelado", "estornado"):
        w.append("r.status=?"); p.append(st)
    if a.get("seller_id"):
        w.append("s.seller_id=?"); p.append(a["seller_id"])
    rows = q(db, "SELECT r.*, s.number, c.name customer, u.name seller FROM receivables r JOIN sales s ON s.id=r.sale_id JOIN customers c ON c.id=s.customer_id "
                 "JOIN users u ON u.id=s.seller_id WHERE " + " AND ".join(w) + " ORDER BY r.due_date, r.id LIMIT 800", p)
    td = today_s()
    tot = {"pendente": 0, "recebido": 0, "atrasado": 0}
    for r in rows:
        r["overdue"] = r["status"] == "pendente" and r["due_date"] < td
        if r["overdue"]:
            tot["atrasado"] += r["amount"]
        elif r["status"] in tot:
            tot[r["status"]] += r["amount"]
    return {"rows": rows, "totals": tot}


def payables(db, a):
    f, t, *_ = period({"from": a.get("from") or "2000-01-01", "to": a.get("to") or "2999-12-31"})
    w, p = ["p.due_date>=?", "p.due_date<=?"], [f, t]
    st = a.get("status")
    if st == "atrasado":
        w.append("p.status='pendente' AND p.due_date<?"); p.append(today_s())
    elif st in ("pendente", "pago", "cancelado"):
        w.append("p.status=?"); p.append(st)
    rows = q(db, "SELECT p.*, s.name supplier, sl.number sale_number FROM payables p LEFT JOIN suppliers s ON s.id=p.supplier_id "
                 "LEFT JOIN sales sl ON sl.id=p.sale_id WHERE " + " AND ".join(w) + " ORDER BY p.due_date, p.id LIMIT 800", p)
    td = today_s()
    tot = {"pendente": 0, "pago": 0, "atrasado": 0}
    for r in rows:
        r["overdue"] = r["status"] == "pendente" and r["due_date"] < td
        if r["overdue"]:
            tot["atrasado"] += r["amount"]
        elif r["status"] in tot:
            tot[r["status"]] += r["amount"]
    return {"rows": rows, "totals": tot}


def cashflow(db, a):
    f, t, t0, t1 = period(a)
    days = (datetime.strptime(t, "%Y-%m-%d") - datetime.strptime(f, "%Y-%m-%d")).days
    n = 7 if (a.get("group") == "month" or (a.get("group") != "day" and days > 62)) else 10
    k = lambda col: f"substr({col},1,{n})"  # noqa: E731
    buckets = {}

    def put(key, field, v):
        buckets.setdefault(key, {"key": key, "sold": 0, "received": 0, "paid": 0, "expected_in": 0, "expected_out": 0})[field] += v

    for r in q(db, f"SELECT {k('created_at')} k, SUM(total) v FROM sales WHERE status='confirmed' AND created_at>=? AND created_at<? GROUP BY k", (t0, t1)):
        put(r["k"], "sold", r["v"])
    for r in q(db, f"SELECT {k('received_at')} k, SUM(amount) v FROM receivables WHERE status IN ('recebido','estornado') AND received_at>=? AND received_at<? GROUP BY k", (t0, t1)):
        put(r["k"], "received", r["v"])
    for r in q(db, f"SELECT {k('paid_at')} k, SUM(amount) v FROM payables WHERE status='pago' AND paid_at>=? AND paid_at<? GROUP BY k", (t0, t1)):
        put(r["k"], "paid", r["v"])
    for r in q(db, f"SELECT {k('paid_at')} k, SUM(amount) v FROM sale_commissions WHERE status='paga' AND paid_at>=? AND paid_at<? GROUP BY k", (t0, t1)):
        put(r["k"], "paid", r["v"])
    for r in q(db, f"SELECT {k('due_date')} k, SUM(amount) v FROM receivables WHERE status='pendente' AND due_date>=? AND due_date<=? GROUP BY k", (f, t)):
        put(r["k"], "expected_in", r["v"])
    for r in q(db, f"SELECT {k('due_date')} k, SUM(amount) v FROM payables WHERE status='pendente' AND due_date>=? AND due_date<=? GROUP BY k", (f, t)):
        put(r["k"], "expected_out", r["v"])
    rows, acc = [], 0
    for key in sorted(buckets):
        b = buckets[key]
        b["net"] = b["received"] - b["paid"]
        acc += b["net"]
        b["balance"] = acc
        rows.append(b)
    tot = {x: sum(r[x] for r in rows) for x in ("sold", "received", "paid", "expected_in", "expected_out", "net")}
    return {"period": {"from": f, "to": t}, "group": "month" if n == 7 else "day", "rows": rows, "totals": tot}


# ---------------------------------------------------------------- relatórios
def C(key, label, typ="text"):
    return {"key": key, "label": label, "type": typ}


def _wrap(name, title, a, cols, rows, sum_keys=()):
    f, t, *_ = period(a)
    totals = {k: sum((r.get(k) or 0) for r in rows) for k in sum_keys}
    return {"name": name, "title": title, "period": {"from": f, "to": t}, "columns": cols, "rows": rows, "totals": totals}


def rep_sales(db, a):
    w, p, _ = _sale_where(a)
    st = a.get("status")
    if st == "all":
        w[0] = "1=1"
    rows = q(db, "SELECT s.number, s.created_at date, c.name customer, u.name seller, s.status, s.payment_method pay, s.discount, s.total, "
                 "s.cost_total+s.freight_cost+s.install_cost+s.other_cost cost, s.gross_profit profit, COALESCE(sc.amount,0) commission "
                 "FROM sales s JOIN customers c ON c.id=s.customer_id JOIN users u ON u.id=s.seller_id LEFT JOIN sale_commissions sc ON sc.sale_id=s.id AND sc.kind='normal' "
                 "WHERE " + " AND ".join(w) + " ORDER BY s.id", p)
    for r in rows:
        r["status"], r["pay"], r["date"] = STATUS_SALE[r["status"]], PAY.get(r["pay"], r["pay"]), r["date"][:16]
    return _wrap("sales", "Vendas por período", a, [C("number", "Nº"), C("date", "Data"), C("customer", "Cliente"), C("seller", "Vendedor"), C("status", "Situação"),
                 C("pay", "Pagamento"), C("discount", "Desconto", "money"), C("total", "Total", "money"), C("cost", "Custo", "money"),
                 C("profit", "Lucro bruto", "money"), C("commission", "Comissão", "money")], rows, ("discount", "total", "cost", "profit", "commission"))


def rep_sales_by_seller(db, a):
    w, p, _ = _sale_where(a)
    rows = q(db, "SELECT u.name seller, COUNT(*) n, SUM(s.total) revenue, SUM(s.cost_total+s.freight_cost+s.install_cost+s.other_cost) cost, SUM(s.gross_profit) profit, "
                 "COALESCE(SUM(sc.amount),0) commission FROM sales s JOIN users u ON u.id=s.seller_id LEFT JOIN sale_commissions sc ON sc.sale_id=s.id AND sc.kind='normal' "
                 "WHERE " + " AND ".join(w) + " GROUP BY s.seller_id ORDER BY revenue DESC", p)
    for r in rows:
        r["ticket"] = r["revenue"] // r["n"]
        r["margin"] = round(r["profit"] * 100.0 / r["revenue"], 1) if r["revenue"] else 0
    return _wrap("sales_by_seller", "Vendas por vendedor", a, [C("seller", "Vendedor"), C("n", "Vendas", "int"), C("revenue", "Faturamento", "money"),
                 C("ticket", "Ticket médio", "money"), C("cost", "Custos", "money"), C("profit", "Lucro bruto", "money"), C("margin", "Margem", "pct"),
                 C("commission", "Comissões", "money")], rows, ("n", "revenue", "cost", "profit", "commission"))


def rep_sales_by_product(db, a):
    w, p, _ = _sale_where(a)
    iw, ip_ = _item_filters(a)
    rows = q(db, "SELECT si.name item, CASE si.kind WHEN 'package' THEN 'Pacote' ELSE 'Produto' END type, SUM(si.qty) qty, SUM(si.net_revenue) revenue, SUM(si.cost_total) cost "
                 "FROM sale_items si JOIN sales s ON s.id=si.sale_id LEFT JOIN products p ON p.id=si.product_id WHERE si.kind IN ('product','package') AND "
                 + " AND ".join(w + iw) + " GROUP BY si.kind, COALESCE(si.product_id, -si.package_id) ORDER BY revenue DESC", p + ip_)
    for r in rows:
        r["profit"] = r["revenue"] - r["cost"]
    return _wrap("sales_by_product", "Vendas por produto e pacote", a, [C("item", "Item"), C("type", "Tipo"), C("qty", "Qtd.", "qty"), C("revenue", "Receita", "money"),
                 C("cost", "Custo", "money"), C("profit", "Lucro bruto", "money")], rows, ("qty", "revenue", "cost", "profit"))


def rep_stock(db, a):
    w, p = ["p.kind='product'"], []
    if a.get("category_id"):
        w.append("p.category_id=?"); p.append(a["category_id"])
    if a.get("product_id"):
        w.append("p.id=?"); p.append(a["product_id"])
    rows = q(db, "SELECT p.sku, p.name, c.name category, p.unit, p.stock_qty qty, p.min_stock minq, p.cost_price cost, p.sale_price price, "
                 "CAST(ROUND(p.stock_qty*p.cost_price) AS INTEGER) value, CASE WHEN p.active=0 THEN 'Inativo' WHEN p.stock_qty<=p.min_stock THEN 'Estoque baixo' ELSE 'OK' END status "
                 "FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE " + " AND ".join(w) + " ORDER BY p.name", p)
    return _wrap("stock", "Estoque atual", a, [C("sku", "SKU"), C("name", "Produto"), C("category", "Categoria"), C("unit", "Un."), C("qty", "Estoque", "qty"),
                 C("minq", "Mínimo", "qty"), C("cost", "Custo un.", "money"), C("price", "Venda un.", "money"), C("value", "Valor em estoque (custo)", "money"),
                 C("status", "Situação")], rows, ("value",))


def rep_stock_movements(db, a):
    f, t, t0, t1 = period(a)
    w, p = ["m.created_at>=?", "m.created_at<?"], [t0, t1]
    if a.get("product_id"):
        w.append("m.product_id=?"); p.append(a["product_id"])
    if a.get("category_id"):
        w.append("pr.category_id=?"); p.append(a["category_id"])
    rows = q(db, "SELECT m.created_at date, pr.sku, pr.name product, m.type, m.qty, m.balance_after bal, m.reason, u.name user FROM stock_movements m "
                 "JOIN products pr ON pr.id=m.product_id LEFT JOIN users u ON u.id=m.user_id WHERE " + " AND ".join(w) + " ORDER BY m.id", p)
    for r in rows:
        r["type"], r["date"] = MOVE[r["type"]], r["date"][:16]
    return _wrap("stock_movements", "Histórico de movimentação do estoque", a, [C("date", "Data"), C("sku", "SKU"), C("product", "Produto"), C("type", "Tipo"),
                 C("qty", "Qtd.", "qty"), C("bal", "Saldo", "qty"), C("reason", "Motivo"), C("user", "Usuário")], rows)


def rep_costs_profit(db, a):
    w, p, _ = _sale_where(a)
    rows = q(db, "SELECT s.number, s.created_at date, u.name seller, s.total, s.cost_total pcost, s.freight_cost fc, s.install_cost ic, s.other_cost oc, s.gross_profit profit, "
                 "CASE WHEN s.costs_confirmed=1 THEN 'Sim' ELSE 'Pendente' END confirmed FROM sales s JOIN users u ON u.id=s.seller_id WHERE " + " AND ".join(w) + " ORDER BY s.id", p)
    for r in rows:
        r["date"] = r["date"][:10]
        r["margin"] = round(r["profit"] * 100.0 / r["total"], 1) if r["total"] else 0
    return _wrap("costs_profit", "Custos e lucro bruto estimado", a, [C("number", "Nº"), C("date", "Data"), C("seller", "Vendedor"), C("total", "Faturamento", "money"),
                 C("pcost", "Custo produtos/serviços", "money"), C("fc", "Custo frete", "money"), C("ic", "Custo instalação", "money"), C("oc", "Outros custos", "money"),
                 C("profit", "Lucro bruto", "money"), C("margin", "Margem", "pct"), C("confirmed", "Custos confirmados")], rows, ("total", "pcost", "fc", "ic", "oc", "profit"))


def rep_goals(db, a):
    f, t, *_ = period(a)
    months, m = [], f[:7]
    while m <= t[:7]:
        months.append(m)
        m = L.add_months(m + "-01", 1)[:7]
    rows = []
    for mo in months[-24:]:
        for u in q(db, "SELECT id,name FROM users WHERE role='vendedor'" + (" AND id=?" if a.get("seller_id") else "") + " ORDER BY name", [a["seller_id"]] if a.get("seller_id") else []):
            sm = L.seller_month(db, u["id"], mo)
            if sm["goal"] is None and not sm["count"]:
                continue
            rows.append({"month": mo, "seller": u["name"], "goal": sm["goal"] or 0, "sold": sm["sold"], "count": sm["count"], "pct": sm["pct"] or 0,
                         "status": "Sem meta" if sm["goal"] is None else ("Atingida" if sm["pct"] >= 100 else "Pendente")})
    return _wrap("goals", "Metas e desempenho", a, [C("month", "Mês"), C("seller", "Vendedor"), C("goal", "Meta", "money"), C("sold", "Vendido", "money"),
                 C("count", "Vendas", "int"), C("pct", "% da meta", "pct"), C("status", "Situação")], rows, ("goal", "sold", "count"))


def rep_commissions(db, a):
    f, t, t0, t1 = period(a)
    w, p = ["s.created_at>=?", "s.created_at<?"], [t0, t1]
    if a.get("seller_id"):
        w.append("sc.seller_id=?"); p.append(a["seller_id"])
    if a.get("status"):
        w.append("sc.status=?"); p.append(a["status"])
    rows = q(db, "SELECT u.name seller, s.number, s.created_at date, c.name customer, sc.base, sc.amount, sc.status, sc.paid_at FROM sale_commissions sc "
                 "JOIN sales s ON s.id=sc.sale_id JOIN customers c ON c.id=s.customer_id JOIN users u ON u.id=sc.seller_id WHERE " + " AND ".join(w) + " ORDER BY u.name, s.id", p)
    for r in rows:
        r["date"], r["paid_at"] = r["date"][:10], (r["paid_at"] or "")[:10]
    tot = _wrap("commissions", "Comissões por vendedor e período", a, [C("seller", "Vendedor"), C("number", "Venda"), C("date", "Data"), C("customer", "Cliente"),
                C("base", "Base", "money"), C("amount", "Comissão", "money"), C("status", "Status"), C("paid_at", "Pago em")], rows)
    tot["totals"] = {"amount": sum(r["amount"] for r in rows if r["status"] != "cancelada")}
    return tot


def rep_receivables(db, a):
    d = receivables(db, a)
    rows = d["rows"]
    for r in rows:
        r["state"] = "Atrasado" if r["overdue"] else r["status"].capitalize()
        r["method"] = PAY.get(r["method"], r["method"] or "")
        r["parc"] = f"{r['installment_no']}/{r['installments_total']}" if r["installment_no"] else "Entrada"
    return _wrap("receivables", "Contas a receber", a, [C("number", "Venda"), C("customer", "Cliente"), C("seller", "Vendedor"), C("parc", "Parcela"), C("due_date", "Vencimento"),
                 C("method", "Forma"), C("amount", "Valor", "money"), C("state", "Situação"), C("received_at", "Recebido em")], rows, ("amount",))


def rep_payables(db, a):
    d = payables(db, a)
    rows = d["rows"]
    for r in rows:
        r["state"] = "Atrasado" if r["overdue"] else r["status"].capitalize()
        r["paid_at"] = (r["paid_at"] or "")[:10]
    return _wrap("payables", "Contas a pagar", a, [C("description", "Descrição"), C("category", "Categoria"), C("supplier", "Fornecedor"), C("due_date", "Vencimento"),
                 C("amount", "Valor", "money"), C("state", "Situação"), C("paid_at", "Pago em")], rows, ("amount",))


REPORTS = {f.__name__[4:]: f for f in (rep_sales, rep_sales_by_seller, rep_sales_by_product, rep_stock, rep_stock_movements, rep_costs_profit,
                                       rep_goals, rep_commissions, rep_receivables, rep_payables)}


def build_report(db, name, a):
    fn = REPORTS.get(name)
    if not fn:
        raise ApiError("Relatório inexistente", 404)
    return fn(db, a)


# ---------------------------------------------------------------- exportação
def _fmt(v, typ):
    if v is None or v == "":
        return ""
    if typ == "money":
        return brl(v)
    if typ == "pct":
        return f"{v:.1f}%".replace(".", ",")
    if typ == "qty":
        return f"{v:,.3f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".") if isinstance(v, float) else str(v)
    return str(v)


def export_xlsx(rep):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = rep["title"][:30]
    ws["A1"] = rep["title"]
    ws["A1"].font = Font(bold=True, size=14, color="0B4F8A")
    ws["A2"] = f"Período: {rep['period']['from']} a {rep['period']['to']}  ·  Gerado em {now().strftime('%d/%m/%Y %H:%M')}"
    cols = rep["columns"]
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=4, column=i, value=c["label"])
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0B6BB8")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for ri, r in enumerate(rep["rows"], 5):
        for ci, c in enumerate(cols, 1):
            v = r.get(c["key"])
            if c["type"] == "money" and v is not None:
                v = v / 100
            cell = ws.cell(row=ri, column=ci, value=v)
            if c["type"] == "money":
                cell.number_format = '"R$" #,##0.00'
            elif c["type"] == "pct":
                cell.number_format = '0.0"%"'
            elif c["type"] == "qty":
                cell.number_format = "#,##0.###"
    if rep["totals"]:
        tr = len(rep["rows"]) + 5
        ws.cell(row=tr, column=1, value="TOTAL").font = Font(bold=True)
        for ci, c in enumerate(cols, 1):
            if c["key"] in rep["totals"]:
                v = rep["totals"][c["key"]]
                cell = ws.cell(row=tr, column=ci, value=v / 100 if c["type"] == "money" else v)
                cell.font = Font(bold=True)
                if c["type"] == "money":
                    cell.number_format = '"R$" #,##0.00'
    for ci, c in enumerate(cols, 1):
        width = max([len(str(c["label"]))] + [len(_fmt(r.get(c["key"]), c["type"])) for r in rep["rows"][:200]]) + 2
        ws.column_dimensions[ws.cell(row=4, column=ci).column_letter].width = min(max(width, 10), 45)
    ws.freeze_panes = "A5"
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def export_pdf(rep, store_name):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=28, title=rep["title"])
    ss = getSampleStyleSheet()
    cell = ss["BodyText"].clone("cell", fontSize=7.5, leading=9)
    cols = rep["columns"]
    head = cell.clone("head", textColor=colors.white)
    data = [[Paragraph(f"<b>{c['label']}</b>", head) for c in cols]]
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    for r in rep["rows"]:
        data.append([Paragraph(esc(_fmt(r.get(c["key"]), c["type"])), cell) for c in cols])
    if rep["totals"]:
        data.append([Paragraph("<b>TOTAL</b>" if i == 0 else (f"<b>{esc(_fmt(rep['totals'][c['key']], c['type']))}</b>" if c["key"] in rep["totals"] else ""), cell)
                     for i, c in enumerate(cols)])
    t = Table(data, repeatRows=1)
    sty = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B6BB8")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8D4EA")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F8FD")])]
    t.setStyle(TableStyle(sty))
    story = [Paragraph(f"<b>{esc(store_name)}</b> — {esc(rep['title'])}", ss["Title"]),
             Paragraph(f"Período: {rep['period']['from']} a {rep['period']['to']} · Gerado em {now().strftime('%d/%m/%Y %H:%M')}", ss["Normal"]),
             Spacer(1, 8), t]
    doc.build(story)
    bio.seek(0)
    return bio
