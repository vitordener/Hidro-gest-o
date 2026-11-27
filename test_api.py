"""Testes automatizados (dados fictícios, banco temporário).  Uso:  python -m unittest test_api -v"""
import os
import tempfile
import threading
import unittest

_tmp = tempfile.mkdtemp()
os.environ["PISCINAS_DB"] = os.path.join(_tmp, "t.db")
os.environ["AUTO_BACKUP"] = "0"
os.environ["BACKUP_DIR"] = os.path.join(_tmp, "bk")

import app as A  # noqa: E402
import db as D  # noqa: E402
import seed_demo  # noqa: E402

A.init_app()
_c = D.connect()
seed_demo.seed(_c)
_c.close()


class Client:
    def __init__(self):
        self.c = A.app.test_client()
        self.csrf = self.c.get("/api/me").json["csrf"]

    def req(self, m, url, data=None):
        kw = {"headers": {"X-CSRF-Token": self.csrf}}
        if data is not None:
            kw["json"] = data
        r = getattr(self.c, m)(url, **kw)
        return r

    def get(self, u): return self.req("get", u)
    def post(self, u, d=None): return self.req("post", u, d if d is not None else {})
    def put(self, u, d=None): return self.req("put", u, d if d is not None else {})

    def login(self, email, pw="vendedor123"):
        r = self.post("/api/login", {"email": email, "password": pw})
        if r.status_code == 200:
            self.csrf = r.json["csrf"]
        return r


def admin():
    c = Client(); assert c.login("admin@loja.com", "admin12345").status_code == 200; return c


def seller(n="carlos"):
    c = Client(); assert c.login(f"{n}@loja.com").status_code == 200; return c


def db():
    return D.connect()


def pid(sku):
    with db() as d:
        return d.execute("SELECT id FROM products WHERE sku=?", (sku,)).fetchone()[0]


def stock(sku):
    with db() as d:
        return d.execute("SELECT stock_qty FROM products WHERE sku=?", (sku,)).fetchone()[0]


class T(unittest.TestCase):
    key = 0

    def nk(self):
        T.key += 1
        return f"test-{T.key}"

    def sale(self, c, items, **kw):
        d = {"idempotency_key": self.nk(), "customer_id": kw.pop("customer_id", None), "items": items, "payment_method": kw.pop("payment_method", "pix")}
        d.update(kw)
        if d["customer_id"] is None:
            d["customer_id"] = c.get("/api/customers").json[0]["id"]
        return c.post("/api/sales", d)

    # ---------------------------------------------------------------- autenticação
    def test_01_auth_and_csrf(self):
        c = Client()
        self.assertEqual(c.get("/api/products").status_code, 401)
        self.assertEqual(c.login("carlos@loja.com", "errada").status_code, 401)
        # sem token CSRF a gravação é recusada
        r = c.c.post("/api/login", json={"email": "carlos@loja.com", "password": "vendedor123"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(c.login("carlos@loja.com").status_code, 200)

    def test_02_lockout(self):
        c = Client()
        for _ in range(5):
            c.login("rafael@loja.com", "x")
        r = c.login("rafael@loja.com", "vendedor123")
        self.assertEqual(r.status_code, 429)
        with db() as d:
            d.execute("UPDATE users SET locked_until=NULL, failed_logins=0 WHERE email='rafael@loja.com'")

    def test_03_password_hash_not_plain(self):
        with db() as d:
            for (h,) in d.execute("SELECT password_hash FROM users"):
                self.assertNotIn("vendedor123", h)
                self.assertNotIn("admin12345", h)
                self.assertTrue(h.startswith(("scrypt:", "pbkdf2:")))

    # ---------------------------------------------------------------- permissões
    def test_10_seller_blocked_from_admin_routes(self):
        c = seller()
        for m, u in [("get", "/api/users"), ("get", "/api/settings"), ("get", "/api/dashboard/admin"), ("get", "/api/finance/receivables"),
                     ("get", "/api/finance/payables"), ("get", "/api/finance/cashflow"), ("get", "/api/reports/sales"), ("get", "/api/audit"),
                     ("get", "/api/stock/movements"), ("get", "/api/goals"), ("get", "/api/commission-rules"), ("get", "/api/suppliers"),
                     ("get", "/api/backups"), ("get", "/api/sellers"), ("post", "/api/stock/move"), ("post", "/api/products"),
                     ("post", "/api/packages"), ("put", "/api/settings"), ("put", "/api/goals"), ("put", "/api/commission-rules"),
                     ("post", "/api/commissions/status"), ("post", "/api/users"), ("post", "/api/sales/1/cancel"), ("put", "/api/sales/1/costs"),
                     ("put", f"/api/products/{pid('BOM-10')}"), ("put", "/api/users/1")]:
            r = getattr(c, m)(u)
            self.assertEqual(r.status_code, 403, f"{m} {u} -> {r.status_code}")

    def test_11_seller_never_sees_costs(self):
        c = seller()
        for p in c.get("/api/products").json:
            for k in ("cost_price", "supplier", "supplier_id", "min_stock"):
                self.assertNotIn(k, p)
        for pk in c.get("/api/packages").json:
            self.assertNotIn("cost_total", pk)
            self.assertNotIn("gross_profit", pk)
            self.assertNotIn("commission_rule", pk)
            for it in pk["items"]:
                self.assertNotIn("unit_cost", it)
                self.assertNotIn("cost_override", it)
                self.assertNotIn("price_alloc", it)
        sid = c.get("/api/sales").json[0]["id"]
        txt = c.get(f"/api/sales/{sid}").get_data(as_text=True)
        for k in ("unit_cost", "cost_total", "gross_profit", "freight_cost", "net_revenue", "receivables"):
            self.assertNotIn(k, txt)
        for row in c.get("/api/sales").json:
            for k in ("cost", "gross_profit"):
                self.assertNotIn(k, row)
        d = c.get("/api/dashboard/seller").get_data(as_text=True)
        self.assertNotIn("profit", d)

    def test_12_seller_sees_only_own_sales_and_customers(self):
        c = seller("carlos")
        me = c.get("/api/me").json["user"]["id"]
        sales = c.get("/api/sales").json
        self.assertTrue(sales)
        with db() as d:
            others = [r[0] for r in d.execute("SELECT id FROM sales WHERE seller_id<>?", (me,))]
            n_own = d.execute("SELECT COUNT(*) FROM sales WHERE seller_id=?", (me,)).fetchone()[0]
        self.assertEqual(len(sales), n_own)
        self.assertEqual(c.get(f"/api/sales/{others[0]}").status_code, 404)
        self.assertEqual(c.get(f"/api/sales?seller_id={others and 99}").status_code, 200)  # filtro de outro vendedor é ignorado
        self.assertTrue(all(s["seller"] == "Carlos Mendes" for s in c.get("/api/sales?seller_id=2").json))
        # comissão de outros: lista só as próprias
        self.assertTrue(all(r["seller"] == "Carlos Mendes" for r in c.get("/api/commissions?seller_id=3").json["rows"]))
        # histórico de metas de outro vendedor é ignorado (usa o próprio)
        h = c.get("/api/goals/history?seller_id=3").json
        self.assertTrue(all(isinstance(x["goal"], (int, type(None))) for x in h))
        self.assertEqual(c.get("/api/dashboard/seller?seller_id=3").json["seller"]["id"], me)

    def test_13_customer_isolation(self):
        a, b = seller("carlos"), seller("mariana")
        ca = {x["id"] for x in a.get("/api/customers").json}
        cb = {x["id"] for x in b.get("/api/customers").json}
        self.assertTrue(ca and cb)
        only_b = cb - ca
        if only_b:
            self.assertEqual(a.get(f"/api/customers/{next(iter(only_b))}").status_code, 404)
            self.assertEqual(a.put(f"/api/customers/{next(iter(only_b))}", {"name": "x"}).status_code, 404)
            r = self.sale(a, [{"type": "product", "product_id": pid("LIM-CLO"), "qty": 1}], customer_id=next(iter(only_b)))
            self.assertEqual(r.status_code, 403)

    def test_14_seller_cannot_forge_seller_id(self):
        c = seller("carlos")
        r = self.sale(c, [{"type": "product", "product_id": pid("ACE-PEN"), "qty": 1}], seller_id=3)
        self.assertEqual(r.status_code, 201)
        with db() as d:
            sl = d.execute("SELECT u.email FROM sales s JOIN users u ON u.id=s.seller_id WHERE s.id=?", (r.json["id"],)).fetchone()[0]
        self.assertEqual(sl, "carlos@loja.com")

    # ---------------------------------------------------------------- venda
    def test_20_client_prices_ignored(self):
        c = seller()
        before = stock("ACE-ASP")
        r = self.sale(c, [{"type": "product", "product_id": pid("ACE-ASP"), "qty": 2, "unit_price": 1, "price": 1}], total=1, unit_price=1)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json["total"], 2 * 349 * 100)
        self.assertEqual(stock("ACE-ASP"), before - 2)

    def test_21_package_stock_once_and_commission(self):
        c = seller("mariana")
        skus = {"CAS-4X2": 1, "BOM-05": 1, "FIL-40": 1, "INS-KIT": 1}
        before = {k: stock(k) for k in skus}
        pk = next(p for p in c.get("/api/packages").json if p["name"].startswith("Piscina 4x2"))
        r = self.sale(c, [{"type": "package", "package_id": pk["id"], "qty": 1}])
        self.assertEqual(r.status_code, 201, r.json)
        for k, q in skus.items():
            self.assertEqual(stock(k), before[k] - q, f"{k} baixado mais de uma vez")
        self.assertEqual(r.json["total"], 24900 * 100)
        with db() as d:
            cm = d.execute("SELECT amount,status,base,snapshot FROM sale_commissions WHERE sale_id=?", (r.json["id"],)).fetchone()
            self.assertEqual(cm["amount"], round(24900 * 100 * 0.04))  # regra 4% sobre total do pacote
            self.assertEqual(cm["status"], "prevista")
            self.assertIn("percent", cm["snapshot"])  # regra aplicada fica registrada
            mv = d.execute("SELECT COUNT(*) FROM stock_movements WHERE sale_id=?", (r.json["id"],)).fetchone()[0]
            self.assertEqual(mv, 4)  # só produtos físicos (mão de obra e frete não têm estoque)
            rs = d.execute("SELECT COALESCE(SUM(net_revenue),0) FROM sale_items WHERE sale_id=? AND kind='component'", (r.json["id"],)).fetchone()[0]
            self.assertEqual(rs, 24900 * 100)  # receita alocada fecha com o preço do pacote

    def test_22_avulso_commission_5pct(self):
        c = seller()
        r = self.sale(c, [{"type": "product", "product_id": pid("LIM-CLO"), "qty": 2}])
        with db() as d:
            self.assertEqual(d.execute("SELECT amount FROM sale_commissions WHERE sale_id=?", (r.json["id"],)).fetchone()[0], round(2 * 44900 * 0.05))

    def test_23_discount_limit_for_seller(self):
        c = seller()
        it = [{"type": "product", "product_id": pid("LIM-CLO"), "qty": 10}]  # 4490,00
        self.assertEqual(self.sale(c, it, discount=int(449000 * 0.06)).status_code, 403)
        self.assertEqual(self.sale(c, it, discount=int(449000 * 0.05)).status_code, 201)
        a = admin()
        self.assertEqual(self.sale(a, it, discount=int(449000 * 0.20)).status_code, 201)
        self.assertEqual(self.sale(a, it, discount=10**9).status_code, 400)

    def test_24_idempotency_double_click(self):
        c = seller()
        key = self.nk()
        d = {"idempotency_key": key, "customer_id": c.get("/api/customers").json[0]["id"], "payment_method": "pix",
             "items": [{"type": "product", "product_id": pid("ACE-PEN"), "qty": 1}]}
        before = stock("ACE-PEN")
        r1, r2 = c.post("/api/sales", d), c.post("/api/sales", d)
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertEqual(r1.json["id"], r2.json["id"])
        self.assertTrue(r2.json["duplicate"])
        self.assertEqual(stock("ACE-PEN"), before - 1)

    def test_25_concurrent_submissions(self):
        a = admin()
        key = self.nk()
        d = {"idempotency_key": key, "customer_id": a.get("/api/customers").json[0]["id"], "payment_method": "pix",
             "items": [{"type": "product", "product_id": pid("OUT-BOIA"), "qty": 1}]}
        before = stock("OUT-BOIA")
        clients = [admin() for _ in range(6)]
        res = []
        ths = [threading.Thread(target=lambda c=c: res.append(c.post("/api/sales", d).status_code)) for c in clients]
        [t.start() for t in ths]; [t.join() for t in ths]
        with db() as dd:
            n = dd.execute("SELECT COUNT(*) FROM sales WHERE idem_key=?", (key,)).fetchone()[0]
        self.assertEqual(n, 1, res)
        self.assertEqual(stock("OUT-BOIA"), before - 1)

    def test_26_stock_limit_and_oversell(self):
        c, a = seller(), admin()
        p = pid("AQU-SOL")
        have = stock("AQU-SOL")
        r = self.sale(c, [{"type": "product", "product_id": p, "qty": have + 1}])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(stock("AQU-SOL"), have)  # nada gravado (rollback)
        a.put("/api/settings", {"allow_oversell": 1})
        try:
            r = self.sale(c, [{"type": "product", "product_id": p, "qty": have + 1}])
            self.assertEqual(r.status_code, 201)
        finally:
            a.put("/api/settings", {"allow_oversell": 0})
        self.assertLess(stock("AQU-SOL"), 0)
        a.post("/api/stock/move", {"product_id": p, "type": "ajuste", "qty": have, "reason": "reposição pós-teste"})

    def test_27_package_customization(self):
        c = seller()
        pk = next(p for p in c.get("/api/packages").json if p["name"].startswith("Piscina Completa"))
        rem = [i for i in pk["items"] if i["removable"]]
        self.assertTrue(rem)
        led, before = pid("ACE-LED"), stock("ACE-LED")
        r = self.sale(c, [{"type": "package", "package_id": pk["id"], "qty": 1, "removed": [rem[0]["id"]]}])
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json["total"], (45900 - 590) * 100)
        self.assertEqual(stock("ACE-LED"), before)  # item removido não baixa estoque
        non = [i for i in pk["items"] if not i["removable"]][0]
        self.assertEqual(self.sale(c, [{"type": "package", "package_id": pk["id"], "removed": [non["id"]]}]).status_code, 400)
        # adicional
        r = self.sale(c, [{"type": "package", "package_id": pk["id"], "extras": [{"product_id": pid("ACE-ESC"), "qty": 1}]}])
        self.assertEqual(r.json["total"], 45900 * 100 + 1290 * 100)

    def test_28_package_eligible_base_commission(self):
        c = seller()
        pk = next(p for p in c.get("/api/packages").json if p["name"].startswith("Piscina 7x3"))
        r = self.sale(c, [{"type": "package", "package_id": pk["id"]}])
        self.assertEqual(r.status_code, 201, r.json)
        with db() as d:
            amt = d.execute("SELECT amount FROM sale_commissions WHERE sale_id=?", (r.json["id"],)).fetchone()[0]
            el = d.execute("SELECT SUM(si.net_revenue) FROM sale_items si JOIN products p ON p.id=si.product_id WHERE si.sale_id=? AND si.kind='component' "
                           "AND p.kind='product'", (r.json["id"],)).fetchone()[0]
        self.assertTrue(0 < amt < round(62500 * 100 * 0.05))   # base só de itens elegíveis (exclui mão de obra/frete/aquecimento serviços)
        self.assertGreater(el, 0)

    def test_29_installments_not_cash(self):
        a = admin()
        before = a.get("/api/finance/cashflow?from=2000-01-01&to=2100-01-01").json["totals"]["received"]
        r = self.sale(a, [{"type": "product", "product_id": pid("BOM-10"), "qty": 1}], payment_method="cartao_credito", installments=5)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(a.get("/api/finance/cashflow?from=2000-01-01&to=2100-01-01").json["totals"]["received"], before)
        with db() as d:
            rec = d.execute("SELECT COUNT(*), SUM(amount), MIN(status), MAX(status) FROM receivables WHERE sale_id=?", (r.json["id"],)).fetchone()
        self.assertEqual((rec[0], rec[1], rec[2], rec[3]), (5, r.json["total"], "pendente", "pendente"))
        r2 = self.sale(a, [{"type": "product", "product_id": pid("BOM-10"), "qty": 1}], payment_method="pix")
        self.assertEqual(a.get("/api/finance/cashflow?from=2000-01-01&to=2100-01-01").json["totals"]["received"], before + r2.json["total"])
        r3 = self.sale(a, [{"type": "product", "product_id": pid("BOM-10"), "qty": 1}], payment_method="boleto", installments=3, down_payment=50000)
        with db() as d:
            rows = d.execute("SELECT installment_no,amount,status FROM receivables WHERE sale_id=? ORDER BY installment_no", (r3.json["id"],)).fetchall()
        self.assertEqual(sum(x[1] for x in rows), r3.json["total"])
        self.assertEqual((rows[0][0], rows[0][1], rows[0][2]), (0, 50000, "recebido"))

    def test_30_goal_updates_and_cancellation(self):
        c, a = seller("mariana"), admin()
        d0 = c.get("/api/dashboard/seller").json
        stk, p = stock("FIL-60"), pid("FIL-60")
        r = self.sale(c, [{"type": "product", "product_id": p, "qty": 1}])
        d1 = c.get("/api/dashboard/seller").json
        self.assertEqual(d1["sold"], d0["sold"] + r.json["total"])
        self.assertEqual(d1["count"], d0["count"] + 1)
        self.assertEqual(d1["remaining"], max(d1["goal"] - d1["sold"], 0))
        self.assertEqual(c.post(f"/api/sales/{r.json['id']}/cancel", {"reason": "x"}).status_code, 403)
        self.assertEqual(a.post(f"/api/sales/{r.json['id']}/cancel", {}).status_code, 400)  # motivo obrigatório
        self.assertEqual(a.post(f"/api/sales/{r.json['id']}/cancel", {"reason": "Erro de lançamento"}).status_code, 200)
        d2 = c.get("/api/dashboard/seller").json
        self.assertEqual((d2["sold"], d2["count"]), (d0["sold"], d0["count"]))
        self.assertEqual(stock("FIL-60"), stk)
        self.assertEqual(a.post(f"/api/sales/{r.json['id']}/cancel", {"reason": "de novo"}).status_code, 400)  # não duplica devolução
        self.assertEqual(stock("FIL-60"), stk)
        with db() as d:
            self.assertEqual(d.execute("SELECT status FROM sale_commissions WHERE sale_id=?", (r.json["id"],)).fetchone()[0], "cancelada")
            self.assertEqual(d.execute("SELECT COUNT(*) FROM receivables WHERE sale_id=? AND status='estornado'", (r.json["id"],)).fetchone()[0], 1)
            self.assertEqual(d.execute("SELECT COUNT(*) FROM payables WHERE sale_id=? AND category='estorno'", (r.json["id"],)).fetchone()[0], 1)

    def test_31_paid_commission_clawback(self):
        c, a = seller("rafael"), admin()
        r = self.sale(c, [{"type": "product", "product_id": pid("LIM-ALG"), "qty": 3}])
        with db() as d:
            cid = d.execute("SELECT id FROM sale_commissions WHERE sale_id=?", (r.json["id"],)).fetchone()[0]
        self.assertEqual(a.post("/api/commissions/status", {"ids": [cid], "status": "paga"}).json["changed"], 0)  # precisa aprovar antes
        self.assertEqual(a.post("/api/commissions/status", {"ids": [cid], "status": "aprovada"}).json["changed"], 1)
        self.assertEqual(a.post("/api/commissions/status", {"ids": [cid], "status": "paga"}).json["changed"], 1)
        self.assertEqual(a.post("/api/commissions/status", {"ids": [cid], "status": "paga"}).json["changed"], 0)  # não paga duas vezes
        a.post(f"/api/sales/{r.json['id']}/cancel", {"reason": "teste estorno"})
        with db() as d:
            rows = d.execute("SELECT kind,amount,status FROM sale_commissions WHERE sale_id=? ORDER BY kind", (r.json["id"],)).fetchall()
        self.assertEqual([(x[0], x[2]) for x in rows], [("estorno", "prevista"), ("normal", "paga")])
        self.assertEqual(rows[0][1], -rows[1][1])

    def test_32_milestones(self):
        import logic as L
        self.assertEqual([L.milestone(x) for x in (None, 10, 50, 74.9, 75, 89, 90, 99.9, 100, 130)], [None, 0, 50, 50, 75, 75, 90, 90, 100, 100])

    # ---------------------------------------------------------------- estoque / produtos
    def test_40_stock_moves(self):
        a = admin()
        p = pid("PED-GOI")
        s0 = stock("PED-GOI")
        self.assertEqual(a.post("/api/stock/move", {"product_id": p, "type": "entrada", "qty": 10, "unit_cost": 7200}).status_code, 200)
        self.assertEqual(stock("PED-GOI"), s0 + 10)
        self.assertEqual(a.post("/api/stock/move", {"product_id": p, "type": "saida", "qty": 1}).status_code, 400)  # motivo obrigatório
        self.assertEqual(a.post("/api/stock/move", {"product_id": p, "type": "saida", "qty": 99999, "reason": "x"}).status_code, 409)
        self.assertEqual(a.post("/api/stock/move", {"product_id": p, "type": "ajuste", "qty": 123, "reason": "inventário"}).status_code, 200)
        self.assertEqual(stock("PED-GOI"), 123)
        movs = a.get(f"/api/stock/movements?product_id={p}").json
        self.assertEqual([m["type"] for m in movs[:2]], ["ajuste", "entrada"])
        with db() as d:
            self.assertEqual(d.execute("SELECT cost_price FROM products WHERE id=?", (p,)).fetchone()[0], 7200)

    def test_41_product_crud_and_stock_not_editable(self):
        a = admin()
        r = a.post("/api/products", {"sku": "tst-001", "name": "Produto teste", "category_id": 7, "cost_price": 1000, "sale_price": 2000, "stock_qty": 5, "min_stock": 2})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(a.post("/api/products", {"sku": "TST-001", "name": "dup"}).status_code, 409)
        a.put(f"/api/products/{r.json['id']}", {"stock_qty": 999, "sale_price": 2500})
        self.assertEqual(stock("TST-001"), 5)
        self.assertEqual(a.get("/api/products?q=tst-0").json[0]["sale_price"], 2500)
        self.assertEqual(a.put(f"/api/products/{r.json['id']}", {"active": 0}).status_code, 200)
        c = seller()
        self.assertEqual([p for p in c.get("/api/products?q=tst-0").json], [])  # inativo some para o vendedor
        self.assertEqual(self.sale(c, [{"type": "product", "product_id": r.json["id"], "qty": 1}]).status_code, 400)

    def test_42_low_stock_alert(self):
        a = admin()
        low = a.get("/api/products?low=1").json
        self.assertTrue(any(p["sku"] == "LIM-CLA" for p in low))
        self.assertTrue(a.get("/api/dashboard/admin").json["low_stock"])

    # ---------------------------------------------------------------- clientes
    def test_50_customers(self):
        c = seller()
        self.assertEqual(c.post("/api/customers", {"name": "X", "doc": "111.111.111-11"}).status_code, 400)  # CPF inválido
        r = c.post("/api/customers", {"name": "Cliente Novo", "doc": "529.982.247-25", "phone": "(11) 98888-7777"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(c.post("/api/customers", {"name": "Outro", "doc": "52998224725"}).status_code, 409)
        o = seller("mariana")
        self.assertEqual(o.post("/api/customers", {"name": "Dup", "doc": "52998224725"}).status_code, 409)
        self.assertNotIn(r.json["id"], [x["id"] for x in o.get("/api/customers").json])
        self.assertEqual(c.get(f"/api/customers?q=Cliente Novo").json[0]["id"], r.json["id"])
        self.sale(c, [{"type": "product", "product_id": pid("ACE-PEN"), "qty": 1}], customer_id=r.json["id"])
        self.assertEqual(len(c.get(f"/api/customers/{r.json['id']}").json["sales"]), 1)
        self.assertEqual(admin().post("/api/customers", {"name": "CNPJ", "doc": "11.222.333/0001-81"}).status_code, 201)

    # ---------------------------------------------------------------- metas, comissões, dashboards, relatórios
    def test_60_goals_admin(self):
        a = admin()
        sid = [s for s in a.get("/api/sellers").json if s["name"].startswith("Carlos")][0]["id"]
        self.assertEqual(a.put("/api/goals", {"seller_id": sid, "month": "2031-01", "amount": 9000000}).status_code, 200)
        g = a.get("/api/goals?month=2031-01").json["rows"]
        self.assertEqual([x for x in g if x["id"] == sid][0]["goal"], 9000000)
        self.assertEqual(a.put("/api/goals", {"seller_id": sid, "month": "2031-13", "amount": 1}).status_code, 400)
        self.assertEqual(a.put("/api/goals", {"seller_id": sid, "month": "2031-01", "amount": -5}).status_code, 400)

    def test_61_dashboard_admin_and_filters(self):
        a = admin()
        d = a.get("/api/dashboard/admin").json
        k = d["kpi"]
        self.assertEqual(k["gross_profit"], k["revenue"] - k["cost"])
        self.assertIn("received", d["cash"])           # faturamento ≠ recebido
        self.assertNotEqual(d["cash"]["received"], k["revenue"])
        f = a.get(f"/api/dashboard/admin?category_id=5").json
        self.assertEqual(f["scope"], "itens")
        f2 = a.get(f"/api/dashboard/admin?seller_id={d['sellers'][0]['id']}").json
        self.assertLessEqual(f2["kpi"]["revenue"], k["revenue"])
        self.assertEqual(a.get("/api/dashboard/admin?from=2026-13-01").status_code, 400)

    def test_62_reports_and_exports(self):
        a = admin()
        names = ["sales", "sales_by_seller", "sales_by_product", "stock", "stock_movements", "costs_profit", "goals", "commissions", "receivables", "payables"]
        for n in names:
            r = a.get(f"/api/reports/{n}?from=2020-01-01&to=2100-01-01")
            self.assertEqual(r.status_code, 200, n)
            self.assertTrue(r.json["columns"])
            x = a.get(f"/api/reports/{n}?format=xlsx&from=2020-01-01&to=2100-01-01")
            self.assertEqual(x.status_code, 200, n)
            self.assertTrue(x.data[:2] == b"PK")
            p = a.get(f"/api/reports/{n}?format=pdf&from=2020-01-01&to=2100-01-01")
            self.assertEqual(p.status_code, 200, n)
            self.assertTrue(p.data[:4] == b"%PDF")
        self.assertEqual(a.get("/api/reports/naoexiste").status_code, 404)
        rs = a.get("/api/reports/sales?from=2020-01-01&to=2100-01-01").json
        self.assertEqual(rs["totals"]["profit"], rs["totals"]["total"] - rs["totals"]["cost"])

    def test_63_finance(self):
        a = admin()
        r = a.post("/api/finance/payables", {"description": "Teste conta", "amount": 12345, "due_date": "2031-02-10", "repeat": 3})
        self.assertEqual(len(r.json["ids"]), 3)
        self.assertEqual(a.post(f"/api/finance/payables/{r.json['ids'][0]}/pay").status_code, 200)
        self.assertEqual(a.post(f"/api/finance/payables/{r.json['ids'][0]}/pay").status_code, 409)
        rows = a.get("/api/finance/payables?from=2031-01-01&to=2031-12-31").json["rows"]
        self.assertEqual([x["due_date"][5:7] for x in rows], ["02", "03", "04"])
        rec = a.get("/api/finance/receivables?status=atrasado").json
        self.assertTrue(all(x["overdue"] for x in rec["rows"]))
        pend = a.get("/api/finance/receivables?status=pendente").json["rows"]
        p0 = next(x for x in pend if not x["overdue"])
        self.assertEqual(a.post(f"/api/finance/receivables/{p0['id']}/receive").status_code, 200)
        self.assertEqual(a.post(f"/api/finance/receivables/{p0['id']}/receive").status_code, 409)

    def test_64_sale_costs_confirm(self):
        a = admin()
        r = self.sale(a, [{"type": "product", "product_id": pid("ACE-PEN"), "qty": 1}], freight=10000, install=20000)
        with db() as d:
            self.assertEqual(d.execute("SELECT costs_confirmed FROM sales WHERE id=?", (r.json["id"],)).fetchone()[0], 0)
        gp = a.put(f"/api/sales/{r.json['id']}/costs", {"freight_cost": 6000, "install_cost": 15000}).json["gross_profit"]
        self.assertEqual(gp, r.json["total"] - 2500 - 6000 - 15000)

    # ---------------------------------------------------------------- integridade e usuários
    def test_70_db_immutability(self):
        import sqlite3
        with db() as d:
            for sql in ("DELETE FROM sales", "DELETE FROM sale_items", "DELETE FROM stock_movements", "UPDATE stock_movements SET qty=0",
                        "DELETE FROM audit_log", "UPDATE audit_log SET action='x'", "DELETE FROM sale_commissions", "UPDATE sale_items SET qty=999"):
                with self.assertRaises(sqlite3.DatabaseError, msg=sql):
                    d.execute(sql)

    def test_71_unique_commission_per_sale(self):
        import sqlite3
        with db() as d:
            sid = d.execute("SELECT sale_id FROM sale_commissions LIMIT 1").fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                d.execute("INSERT INTO sale_commissions(sale_id,seller_id,kind,amount,created_at) VALUES(?,?,?,?,?)", (sid, 2, "normal", 1, "x"))

    def test_72_users(self):
        a = admin()
        r = a.post("/api/users", {"name": "Novo Vend", "email": "novo@loja.com", "role": "vendedor", "password": "senhaboa123"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(a.post("/api/users", {"name": "Fraco", "email": "f@loja.com", "role": "vendedor", "password": "123"}).status_code, 400)
        self.assertEqual(a.post("/api/users", {"name": "Dup", "email": "NOVO@loja.com", "role": "vendedor", "password": "senhaboa123"}).status_code, 409)
        n = Client(); self.assertEqual(n.login("novo@loja.com", "senhaboa123").status_code, 200)
        self.assertTrue(n.get("/api/me").json["user"]["must_change_pw"])
        self.assertEqual(n.post("/api/me/password", {"current": "senhaboa123", "new": "curta"}).status_code, 400)
        self.assertEqual(n.post("/api/me/password", {"current": "senhaboa123", "new": "outrasenha456"}).status_code, 200)
        a.put(f"/api/users/{r.json['id']}", {"active": 0})
        self.assertEqual(n.get("/api/products").status_code, 401)          # sessão existente invalida ao desativar
        self.assertEqual(Client().login("novo@loja.com", "outrasenha456").status_code, 403)
        # sem vendedor ou meta: dashboard devolve null, sem erro
        a.put(f"/api/users/{r.json['id']}", {"active": 1})
        n2 = Client(); n2.login("novo@loja.com", "outrasenha456")
        d = n2.get("/api/dashboard/seller").json
        self.assertIsNone(d["goal"])
        self.assertEqual(d["sold"], 0)
        # nunca deixa o sistema sem admin
        adm = a.get("/api/users").json[0]
        self.assertEqual(a.put(f"/api/users/{adm['id']}", {"active": 0}).status_code, 400)

    def test_73_audit_and_backup(self):
        a = admin()
        self.assertTrue(a.get("/api/audit").json)
        n = a.post("/api/backups").json["name"]
        self.assertIn(n, [b["name"] for b in a.get("/api/backups").json])
        r = a.get(f"/api/backups/{n}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"SQLite format 3"))
        self.assertEqual(a.get("/api/backups/../../etc/passwd").status_code, 404)

    def test_74_headers_and_static(self):
        c = Client()
        r = c.c.get("/")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_75_xss_payload_stored_as_text(self):
        a = admin()
        r = a.post("/api/customers", {"name": "<img src=x onerror=alert(1)>"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(a.get(f"/api/customers/{r.json['id']}").json["name"], "<img src=x onerror=alert(1)>")  # escapamento é feito na renderização


if __name__ == "__main__":
    unittest.main(verbosity=2)
