"""Popula o banco com DADOS FICTÍCIOS para demonstração/testes.  Uso:  python seed_demo.py
Não use em produção (cria usuários com senhas conhecidas)."""
import random
import sys
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

import db as D
import logic as L
from db import q1, tx, now, today_s

R = 100  # reais -> centavos


def cpf(seed):
    r = random.Random(seed)
    d = [r.randint(0, 9) for _ in range(9)]
    for n in (9, 10):
        t = sum(d[i] * (n + 1 - i) for i in range(n))
        d.append((t * 10 % 11) % 10)
    return "".join(map(str, d))


def seed(db):
    if db.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
        print("Banco já possui produtos — seed ignorado."); return
    rnd = random.Random(7)
    cat = {r["name"]: r["id"] for r in db.execute("SELECT id,name FROM categories")}
    admin = q1(db, "SELECT * FROM users WHERE role='admin' ORDER BY id LIMIT 1")
    ts0 = (now() - timedelta(days=75)).strftime("%Y-%m-%d 08:00:00")

    with tx(db):
        db.execute("UPDATE users SET must_change_pw=0 WHERE id=?", (admin["id"],))
        sup = {}
        for n in ("Fibrasul Cascos", "HidroForte Equipamentos", "QuimiPool Distribuidora", "Pedras & Cia"):
            sup[n] = db.execute("INSERT INTO suppliers(name,phone) VALUES(?,?)", (n, "(11) 4000-0000")).lastrowid
        sellers = []
        for name, mail in (("Carlos Mendes", "carlos@loja.com"), ("Mariana Souza", "mariana@loja.com"), ("Rafael Lima", "rafael@loja.com")):
            uid = db.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,'vendedor',?)",
                             (name, mail, generate_password_hash("vendedor123"), ts0)).lastrowid
            sellers.append({"id": uid, "name": name, "role": "vendedor"})

        P = {}
        def prod(sku, name, c, cost, price, stock, mn, s, unit="un", kind="product", brand=None):
            pid = db.execute("INSERT INTO products(sku,name,category_id,brand,cost_price,sale_price,min_stock,supplier_id,unit,kind,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                             (sku, name, cat[c], brand, cost * R, price * R, mn, sup.get(s), unit, kind, ts0)).lastrowid
            if stock and kind == "product":
                db.execute("UPDATE products SET stock_qty=? WHERE id=?", (stock, pid))
                db.execute("INSERT INTO stock_movements(product_id,type,qty,balance_after,unit_cost,reason,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (pid, "entrada", stock, stock, cost * R, "Estoque inicial", admin["id"], ts0))
            P[sku] = pid

        F, H, Q, S = "Fibrasul Cascos", "HidroForte Equipamentos", "QuimiPool Distribuidora", "Pedras & Cia"
        prod("CAS-6X3", "Casco de fibra 6x3 m", "Cascos de piscinas", 14000, 21000, 14, 2, F, brand="Splash")
        prod("CAS-4X2", "Casco de fibra 4x2 m", "Cascos de piscinas", 8000, 12500, 10, 2, F, brand="Splash")
        prod("CAS-7X35", "Casco de fibra 7x3,5 m", "Cascos de piscinas", 18500, 27500, 8, 2, F, brand="Splash")
        prod("BOM-05", "Motobomba 1/2 cv", "Bombas e motores", 650, 990, 20, 4, H, brand="Sodramar")
        prod("BOM-10", "Motobomba 1 cv", "Bombas e motores", 980, 1490, 18, 4, H, brand="Sodramar")
        prod("BOM-15", "Motobomba 1,5 cv", "Bombas e motores", 1250, 1890, 3, 4, H, brand="Sodramar")
        prod("FIL-40", "Filtro de areia 40 cm", "Filtros", 780, 1290, 14, 3, H, brand="Nautilus")
        prod("FIL-60", "Filtro de areia 60 cm", "Filtros", 1100, 1790, 12, 3, H, brand="Nautilus")
        prod("AQU-TC", "Trocador de calor elétrico", "Aquecedores", 3200, 4900, 9, 2, H, brand="Termopool")
        prod("AQU-SOL", "Kit aquecimento solar", "Aquecedores", 2400, 3790, 6, 2, H, brand="Termopool")
        prod("LIM-CLO", "Cloro granulado 10 kg", "Produtos de limpeza", 280, 449, 40, 10, Q, brand="HidroAzul")
        prod("LIM-ALG", "Algicida 5 L", "Produtos de limpeza", 90, 159, 35, 10, Q, brand="HidroAzul")
        prod("LIM-BAR", "Barrilha 12 kg", "Produtos de limpeza", 70, 129, 30, 8, Q, brand="HidroAzul")
        prod("LIM-CLA", "Clarificante 1 L", "Produtos de limpeza", 28, 52, 6, 10, Q, brand="HidroAzul")
        prod("PED-SAO", "Pedra São Tomé", "Pedras e revestimentos", 85, 160, 400, 60, S, unit="m²")
        prod("PED-GOI", "Pedra Goiás", "Pedras e revestimentos", 70, 135, 350, 60, S, unit="m²")
        prod("ACE-CAPA", "Capa térmica 6x3 m", "Acessórios", 900, 1590, 8, 2, H)
        prod("ACE-ESC", "Escada inox 3 degraus", "Acessórios", 750, 1290, 7, 2, H)
        prod("ACE-LED", "Kit iluminação LED", "Acessórios", 320, 590, 25, 5, H)
        prod("ACE-ASP", "Aspirador manual", "Acessórios", 180, 349, 12, 4, H)
        prod("ACE-PEN", "Peneira com cabo", "Acessórios", 25, 59, 18, 5, H)
        prod("INS-KIT", "Kit hidráulico de instalação", "Materiais de instalação", 1350, 2200, 15, 3, H)
        prod("INS-AREIA", "Areia filtrante 25 kg", "Materiais de instalação", 35, 69, 60, 15, S)
        prod("INS-TUBO", "Tubo PVC 50 mm (barra)", "Materiais de instalação", 38, 69, 50, 10, H)
        prod("OUT-BOIA", "Boia de piscina", "Outros produtos", 40, 89, 20, 5, H)
        prod("SRV-MO", "Mão de obra de instalação (pacote)", "Serviços (instalação e frete)", 4500, 7500, 0, 0, None, kind="service")
        prod("SRV-FRT", "Frete e transporte de casco", "Serviços (instalação e frete)", 1200, 2000, 0, 0, None, kind="service")
        prod("SRV-AQ", "Instalação de aquecimento", "Serviços (instalação e frete)", 600, 1100, 0, 0, None, kind="service")

        def package(name, desc, price, comps, rule):
            pid = db.execute("INSERT INTO packages(name,description,sale_price,created_at) VALUES(?,?,?,?)", (name, desc, price * R, ts0)).lastrowid
            for sku, qty, alloc, elig, rem in comps:
                db.execute("INSERT INTO package_items(package_id,product_id,qty,price_alloc,commission_eligible,removable) VALUES(?,?,?,?,?,?)",
                           (pid, P[sku], qty, alloc * R, elig, rem))
            db.execute("INSERT INTO commission_rules(scope,ref_id,type,value,base,updated_at) VALUES('package',?,?,?,?,?)", (pid, *rule, D.now_s()))
            return pid
        pk1 = package("Piscina Completa 6x3 com Aquecimento", "Casco, motobomba, filtro, trocador de calor, kit hidráulico, pedras, LED, instalação e frete.", 45900,
                      [("CAS-6X3", 1, 21000, 1, 0), ("BOM-10", 1, 1490, 1, 0), ("FIL-60", 1, 1790, 1, 0), ("AQU-TC", 1, 4900, 1, 0), ("INS-KIT", 1, 2200, 1, 0),
                       ("PED-SAO", 30, 160, 1, 0), ("ACE-LED", 1, 590, 1, 1), ("SRV-MO", 1, 7500, 0, 0), ("SRV-FRT", 1, 2000, 0, 0)], ("percent", 3, "total"))
        pk2 = package("Piscina 4x2 Essencial", "Casco 4x2 com bomba, filtro, kit hidráulico, instalação e frete.", 24900,
                      [("CAS-4X2", 1, 12500, 1, 0), ("BOM-05", 1, 990, 1, 0), ("FIL-40", 1, 1290, 1, 0), ("INS-KIT", 1, 2200, 1, 0), ("SRV-MO", 1, 7500, 0, 0), ("SRV-FRT", 1, 2000, 0, 0)],
                      ("percent", 4, "total"))
        pk3 = package("Piscina 7x3,5 Premium com Aquecimento Solar", "Casco 7x3,5, motobomba 1,5 cv, filtro, aquecimento solar, pedras Goiás, LED, capa térmica, instalação e frete.", 62500,
                      [("CAS-7X35", 1, 27500, 1, 0), ("BOM-15", 1, 1890, 1, 0), ("FIL-60", 1, 1790, 1, 0), ("AQU-SOL", 1, 3790, 1, 0), ("INS-KIT", 1, 2200, 1, 0), ("PED-GOI", 40, 135, 1, 0),
                       ("ACE-LED", 2, 590, 1, 1), ("ACE-CAPA", 1, 1590, 1, 1), ("SRV-MO", 1, 7500, 0, 0), ("SRV-FRT", 1, 2000, 0, 0), ("SRV-AQ", 1, 1100, 0, 0)],
                      ("percent", 5, "eligible"))

        cust = []
        for i, (n, city) in enumerate([("Roberto Almeida", "Campinas"), ("Fernanda Costa", "Sorocaba"), ("Condomínio Villa Verde", "Jundiaí"), ("Paulo Henrique Dias", "Atibaia"),
                                       ("Luciana Ribeiro", "Indaiatuba"), ("Marcos Vinícius Prado", "Valinhos"), ("Hotel Fazenda Recanto", "Itu"), ("Ana Beatriz Torres", "Americana")]):
            cust.append(db.execute("INSERT INTO customers(name,doc,phone,whatsapp,address,city,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                                   (n, cpf(100 + i) if i != 2 and i != 6 else None, "1999000%04d" % (1000 + i), "1999000%04d" % (1000 + i), f"Rua das Palmeiras, {100 + i * 7}", city,
                                    sellers[i % 3]["id"], ts0)).lastrowid)

        # metas
        mo = now()
        months = [(mo - timedelta(days=60)).strftime("%Y-%m"), (mo - timedelta(days=30)).strftime("%Y-%m"), mo.strftime("%Y-%m")]
        for m in sorted(set(months)):
            for sl, g in zip(sellers, (80000, 60000, 50000)):
                db.execute("INSERT OR REPLACE INTO goals(seller_id,month,amount) VALUES(?,?,?)", (sl["id"], m, g * R))

        def sale(sl, days_ago, ci, items, pay="pix", inst=1, down=0, disc=0, freight=0, install=0):
            d = now() - timedelta(days=days_ago)
            ts = d.strftime("%Y-%m-%d ") + f"{rnd.randint(9, 17):02d}:{rnd.randint(0, 59):02d}:00"
            payload = {"customer_id": cust[ci], "items": items, "payment_method": pay, "installments": inst, "down_payment": down * R,
                       "discount": 0, "freight": freight * R, "install": install * R}
            plan = L.build_sale(db, sl, payload, admin)
            payload["discount"] = int(plan["gross"] * disc / 100)
            plan = L.build_sale(db, sl, payload, admin)
            return L.commit_sale(db, plan, sl, admin, idem_key="demo-" + ts + str(sl["id"]) + str(rnd.random()), created_at=ts)[0]

        pr = lambda sku, qty: {"type": "product", "product_id": P[sku], "qty": qty}  # noqa: E731
        pkg = lambda pid, qty=1, **kw: {"type": "package", "package_id": pid, "qty": qty, **kw}  # noqa: E731
        carlos, mariana, rafael = sellers
        day = now().day
        cur = lambda d: min(max(d, 0), day - 1)  # dias atrás dentro do mês corrente  # noqa: E731
        # --- meses anteriores
        ids = []
        ids.append(sale(carlos, 58, 0, [pkg(pk1)], "boleto", 6, 10000))
        ids.append(sale(mariana, 55, 1, [pkg(pk2)], "cartao_credito", 10))
        ids.append(sale(rafael, 52, 3, [pkg(pk3)], "carne", 12, 15000, disc=2))
        ids.append(sale(carlos, 49, 4, [pr("LIM-CLO", 4), pr("LIM-ALG", 3), pr("ACE-ASP", 1)], "dinheiro"))
        ids.append(sale(mariana, 44, 7, [pr("BOM-10", 1), pr("FIL-60", 1), pr("INS-AREIA", 2)], "pix"))
        ids.append(sale(carlos, 40, 2, [pkg(pk2), pr("PED-SAO", 20)], "boleto", 8, 20000, install=1500))
        ids.append(sale(rafael, 35, 5, [pr("ACE-CAPA", 1), pr("ACE-ESC", 1), pr("ACE-LED", 2)], "debito"))
        ids.append(sale(mariana, 33, 6, [pkg(pk1, removed=[])], "cartao_credito", 12, disc=3))
        ids.append(sale(carlos, 28, 1, [pr("LIM-CLO", 6), pr("LIM-BAR", 4), pr("LIM-CLA", 3)], "pix"))
        ids.append(sale(rafael, 24, 0, [pkg(pk2)], "boleto", 6, 8000))
        # --- mês corrente (Carlos ~65% da meta de 80 mil)
        ids.append(sale(carlos, cur(18), 3, [pkg(pk1)], "boleto", 8, 12000))
        ids.append(sale(carlos, cur(7), 7, [pr("BOM-10", 2), pr("FIL-60", 2), pr("INS-KIT", 1), pr("ACE-LED", 3)], "pix"))
        ids.append(sale(carlos, cur(3), 5, [pr("LIM-CLO", 3), pr("LIM-ALG", 2)], "debito"))
        ids.append(sale(mariana, cur(15), 2, [pkg(pk2)], "carne", 12, 5000, disc=1))
        ids.append(sale(mariana, cur(6), 1, [pr("ACE-CAPA", 1), pr("LIM-CLO", 3)], "pix"))
        ids.append(sale(rafael, cur(10), 6, [pkg(pk2, extras=[{"product_id": P["ACE-ESC"], "qty": 1}])], "cartao_credito", 6, install=0))
        ids.append(sale(rafael, cur(2), 0, [pr("LIM-CLO", 2), pr("ACE-ASP", 2), pr("ACE-PEN", 3)], "dinheiro"))
        ids.append(sale(rafael, cur(1), 4, [pr("OUT-BOIA", 3), pr("LIM-ALG", 2)], "pix"))
        # cancelamentos
        L.cancel_sale(db, ids[4], admin, "cancelled", "Cliente desistiu da compra")
        L.cancel_sale(db, ids[6], admin, "refunded", "Produto devolvido pelo cliente")

        # recebimentos já ocorridos (vencidos há mais de 5 dias) — deixa alguns em atraso de propósito
        td = today_s()
        for r in db.execute("SELECT id,due_date FROM receivables WHERE status='pendente' AND due_date<=?", ((now() - timedelta(days=5)).strftime("%Y-%m-%d"),)).fetchall():
            if rnd.random() < 0.8:
                db.execute("UPDATE receivables SET status='recebido', received_at=? WHERE id=?", (r["due_date"] + " 10:00:00", r["id"]))
        # comissões de vendas antigas: aprovadas/pagas
        old = (now() - timedelta(days=30)).strftime("%Y-%m-%d")
        for r in db.execute("SELECT sc.id, s.created_at FROM sale_commissions sc JOIN sales s ON s.id=sc.sale_id WHERE sc.status='prevista' AND s.status='confirmed' AND s.created_at<?", (old,)).fetchall():
            db.execute("UPDATE sale_commissions SET status='paga', approved_at=?, paid_at=? WHERE id=?", (r["created_at"], (now() - timedelta(days=rnd.randint(3, 20))).strftime("%Y-%m-%d 15:00:00"), r["id"]))
        for r in db.execute("SELECT sc.id FROM sale_commissions sc JOIN sales s ON s.id=sc.sale_id WHERE sc.status='prevista' AND s.status='confirmed' AND s.created_at<? LIMIT 2",
                            ((now() - timedelta(days=14)).strftime("%Y-%m-%d"),)).fetchall():
            db.execute("UPDATE sale_commissions SET status='aprovada', approved_at=? WHERE id=?", (D.now_s(), r["id"]))

        # contas a pagar
        def pay(desc, cat_, amt, due_off, paid, s=None):
            due = (now() + timedelta(days=due_off)).strftime("%Y-%m-%d")
            db.execute("INSERT INTO payables(description,category,supplier_id,amount,due_date,status,paid_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       (desc, cat_, sup.get(s), amt * R, due, "pago" if paid else "pendente", due + " 09:00:00" if paid else None, D.now_s()))
        for k, nm in ((-60, "Aluguel do galpão"), (-30, "Aluguel do galpão")):
            pay(nm, "despesa", 6500, k, True)
        pay("Aluguel do galpão", "despesa", 6500, 4, False)
        pay("Energia elétrica", "despesa", 1480, -20, True)
        pay("Energia elétrica", "despesa", 1620, 7, False)
        pay("Internet e telefonia", "despesa", 390, -3, False)
        pay("Combustível da frota", "despesa", 2150, -12, True)
        pay("Fibrasul — reposição de cascos", "fornecedor", 28000, 12, False, F)
        pay("QuimiPool — produtos químicos", "fornecedor", 5400, -6, False, Q)
        pay("Frete de entrega — Hotel Fazenda Recanto", "frete", 900, 2, False)
    print("Seed concluído.")


if __name__ == "__main__":
    c = D.connect()
    D.init_db(c)
    seed(c)
    for r in c.execute("SELECT u.name, g.amount, (SELECT SUM(total) FROM sales s WHERE s.seller_id=u.id AND s.status='confirmed' AND substr(s.created_at,1,7)=g.month) sold "
                       "FROM goals g JOIN users u ON u.id=g.seller_id WHERE g.month=?", (now().strftime("%Y-%m"),)):
        print(r["name"], "meta", r["amount"] / 100, "vendido", (r["sold"] or 0) / 100)
    print("Admin: admin@loja.com / admin12345  |  Vendedores: carlos@loja.com, mariana@loja.com, rafael@loja.com / vendedor123")
