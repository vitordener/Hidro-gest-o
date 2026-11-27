"""API Flask — Sistema de Gestão para Loja de Piscinas.

Todas as permissões são aplicadas AQUI, no servidor: o navegador nunca acessa o banco, e cada rota
checa o perfil (admin/vendedor) e filtra os dados (vendedor só enxerga o que é dele e nunca custos).
"""
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import timedelta
from functools import wraps

from flask import Flask, jsonify, request, session, g, send_from_directory, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash

import db as D
from db import q, q1, tx, now_s, today_s, get_settings
import logic as L
from logic import ApiError, audit, to_int, to_qty

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="/static")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=1024 * 1024,
)


def _secret():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    p = os.path.join(os.path.dirname(D.DB_PATH), "secret.key")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(p, 0o600)
    return open(p).read().strip()


app.secret_key = _secret()
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


# ------------------------------------------------------------------ infra
def get_db():
    if "db" not in g:
        g.db = D.connect()
    return g.db


@app.teardown_appcontext
def _close(_):
    c = g.pop("db", None)
    if c:
        c.close()


@app.after_request
def _headers(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "same-origin"
    r.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    return r


@app.errorhandler(ApiError)
def _api_error(e):
    return jsonify(error=e.msg, field=e.field), e.status


@app.errorhandler(sqlite3.IntegrityError)
def _integrity(e):
    m = str(e)
    if "UNIQUE" in m:
        return jsonify(error="Registro duplicado (valor já cadastrado)."), 409
    return jsonify(error="Operação recusada pelo banco de dados: " + m.split(":")[0]), 400


@app.errorhandler(sqlite3.DatabaseError)
def _dberr(e):
    if "imutáv" in str(e) or "não podem" in str(e):
        return jsonify(error=str(e)), 400
    app.logger.exception(e)
    return jsonify(error="Erro interno no banco de dados."), 500


@app.errorhandler(404)
def _404(e):
    if request.path.startswith("/api/"):
        return jsonify(error="Não encontrado"), 404
    return send_from_directory(app.static_folder, "index.html")


@app.errorhandler(413)
def _413(e):
    return jsonify(error="Arquivo/dados grandes demais"), 413


@app.errorhandler(Exception)
def _500(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    app.logger.exception(e)
    return jsonify(error="Erro interno do servidor."), 500


@app.before_request
def _csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
        tok = session.get("csrf")
        if not tok or not secrets.compare_digest(tok, request.headers.get("X-CSRF-Token", "")):
            return jsonify(error="Sessão inválida. Recarregue a página."), 403


def cu():
    if "user" in g:
        return g.user
    uid = session.get("uid")
    g.user = None
    if uid:
        u = q1(get_db(), "SELECT id,name,email,role,active,avatar,phone,must_change_pw FROM users WHERE id=?", (uid,))
        if u and u["active"]:
            g.user = u
        else:
            session.pop("uid", None)
    return g.user


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not cu():
            return jsonify(error="Faça login para continuar"), 401
        return f(*a, **k)
    return w


def admin_required(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if cu()["role"] != "admin":
            return jsonify(error="Acesso restrito ao administrador"), 403
        return f(*a, **k)
    return w


def body():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


def s(v, n=200):
    return (str(v).strip()[:n]) if v is not None else ""


def need(d, key, label=None):
    v = s(d.get(key))
    if not v:
        raise ApiError(f"Informe {label or key}", field=key)
    return v


def flag(v):
    return 1 if v in (1, True, "1", "true", "on") else 0


def digits(v):
    return re.sub(r"\D", "", v or "")


def valid_cpf(c):
    if len(c) != 11 or c == c[0] * 11:
        return False
    for n in (9, 10):
        t = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        if (t * 10 % 11) % 10 != int(c[n]):
            return False
    return True


def valid_cnpj(c):
    if len(c) != 14 or c == c[0] * 14:
        return False
    for n in (12, 13):
        w = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-n:] if n == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        t = sum(int(c[i]) * w[i] for i in range(n))
        if (t % 11 < 2 and int(c[n]) != 0) or (t % 11 >= 2 and int(c[n]) != 11 - t % 11):
            return False
    return True


def img_data(v, maxkb):
    v = v or ""
    if v == "":
        return ""
    if not re.match(r"^data:image/(png|jpeg|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$", v):
        raise ApiError("Imagem inválida (use PNG, JPG, WEBP ou SVG)")
    if len(v) > maxkb * 1366:
        raise ApiError(f"Imagem grande demais (máx. {maxkb} KB)")
    return v


period = L.period
_next_day = L.next_day


# ------------------------------------------------------------------ páginas
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/branding")
def branding():
    st = get_settings(get_db())
    return jsonify(store_name=st["store_name"], tagline=st["store_tagline"], logo=st["logo"])


@app.get("/api/me")
def me():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(24)
    u = cu()
    st = get_settings(get_db())
    return jsonify(user=u, csrf=session["csrf"], branding={"store_name": st["store_name"], "tagline": st["store_tagline"], "logo": st["logo"]},
                   settings={"seller_max_discount_pct": float(st["seller_max_discount_pct"]), "allow_oversell": st["allow_oversell"] == "1"})


@app.post("/api/login")
def login():
    d = body()
    db = get_db()
    email, pw = s(d.get("email")).lower(), d.get("password") or ""
    u = q1(db, "SELECT * FROM users WHERE email=?", (email,))
    msg = "E-mail ou senha incorretos"
    if u and u["locked_until"] and u["locked_until"] > now_s():
        raise ApiError("Conta bloqueada temporariamente por tentativas inválidas. Tente em alguns minutos.", 429)
    ok = check_password_hash(u["password_hash"] if u else _DUMMY_HASH, pw)
    if not u or not ok:
        if u:
            n = u["failed_logins"] + 1
            lock = (D.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S") if n >= 5 else None
            db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (0 if lock else n, lock, u["id"]))
        audit(db, None, "login.falha", "user", email, ip=ip())
        time.sleep(0.4)
        raise ApiError(msg, 401)
    if not u["active"]:
        raise ApiError("Usuário inativo. Fale com o administrador.", 403)
    db.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?", (u["id"],))
    session.clear()
    session.permanent = True
    session["uid"] = u["id"]
    session["csrf"] = secrets.token_hex(24)
    audit(db, u, "login", "user", u["id"], ip=ip())
    g.pop("user", None)
    return me()


@app.post("/api/logout")
@login_required
def logout():
    audit(get_db(), cu(), "logout", "user", cu()["id"], ip=ip())
    session.clear()
    return jsonify(ok=True)


@app.post("/api/me/password")
@login_required
def change_password():
    d, db, u = body(), get_db(), cu()
    row = q1(db, "SELECT password_hash FROM users WHERE id=?", (u["id"],))
    if not check_password_hash(row["password_hash"], d.get("current") or ""):
        raise ApiError("Senha atual incorreta", 400, "current")
    new = d.get("new") or ""
    if len(new) < 8 or new == d.get("current"):
        raise ApiError("A nova senha deve ter ao menos 8 caracteres e ser diferente da atual", 400, "new")
    db.execute("UPDATE users SET password_hash=?, must_change_pw=0 WHERE id=?", (generate_password_hash(new), u["id"]))
    audit(db, u, "senha.alterar", "user", u["id"], ip=ip())
    return jsonify(ok=True)


@app.post("/api/me/avatar")
@login_required
def set_avatar():
    v = img_data(body().get("avatar"), 150)
    get_db().execute("UPDATE users SET avatar=? WHERE id=?", (v or None, cu()["id"]))
    return jsonify(ok=True)


# ------------------------------------------------------------------ configurações
@app.get("/api/settings")
@admin_required
def settings_get():
    return jsonify(get_settings(get_db()))


@app.put("/api/settings")
@admin_required
def settings_put():
    d, db = body(), get_db()
    upd = {}
    if "store_name" in d:
        upd["store_name"] = need(d, "store_name", "o nome da loja")[:80]
    if "store_tagline" in d:
        upd["store_tagline"] = s(d["store_tagline"], 120)
    if "logo" in d:
        upd["logo"] = img_data(d["logo"], 300)
    if "allow_oversell" in d:
        upd["allow_oversell"] = "1" if flag(d["allow_oversell"]) else "0"
    if "seller_max_discount_pct" in d:
        try:
            v = float(d["seller_max_discount_pct"])
        except (TypeError, ValueError):
            raise ApiError("Percentual inválido")
        if not 0 <= v <= 100:
            raise ApiError("Percentual deve estar entre 0 e 100")
        upd["seller_max_discount_pct"] = str(v)
    if "commission_cancel_policy" in d:
        if d["commission_cancel_policy"] not in ("clawback", "keep_paid"):
            raise ApiError("Política inválida")
        upd["commission_cancel_policy"] = d["commission_cancel_policy"]
    with tx(db):
        for k, v in upd.items():
            db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        audit(db, cu(), "config.alterar", "settings", None, {k: (v if k != "logo" else "[imagem]") for k, v in upd.items()}, ip())
    return jsonify(get_settings(db))


# ------------------------------------------------------------------ usuários
def user_row(r):
    r = dict(r)
    r.pop("password_hash", None)
    return r


@app.get("/api/users")
@admin_required
def users_list():
    return jsonify(q(get_db(), "SELECT id,name,email,role,active,phone,avatar,must_change_pw,created_at FROM users ORDER BY role, name"))


@app.post("/api/users")
@admin_required
def users_create():
    d, db = body(), get_db()
    name, email = need(d, "name", "o nome"), need(d, "email", "o e-mail").lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ApiError("E-mail inválido", field="email")
    role = d.get("role")
    if role not in ("admin", "vendedor"):
        raise ApiError("Perfil inválido", field="role")
    pw = d.get("password") or ""
    if len(pw) < 8:
        raise ApiError("A senha deve ter ao menos 8 caracteres", field="password")
    with tx(db):
        uid = db.execute("INSERT INTO users(name,email,password_hash,role,phone,must_change_pw,created_at) VALUES(?,?,?,?,?,1,?)",
                         (name, email, generate_password_hash(pw), role, s(d.get("phone"), 30), now_s())).lastrowid
        audit(db, cu(), "usuario.criar", "user", uid, {"email": email, "role": role}, ip())
    return jsonify(id=uid), 201


@app.put("/api/users/<int:uid>")
@admin_required
def users_update(uid):
    d, db = body(), get_db()
    u = q1(db, "SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        raise ApiError("Usuário não encontrado", 404)
    sets, vals = [], []
    if "name" in d:
        sets.append("name=?"); vals.append(need(d, "name", "o nome"))
    if "email" in d:
        e = need(d, "email").lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            raise ApiError("E-mail inválido", field="email")
        sets.append("email=?"); vals.append(e)
    if "phone" in d:
        sets.append("phone=?"); vals.append(s(d["phone"], 30))
    if "role" in d:
        if d["role"] not in ("admin", "vendedor"):
            raise ApiError("Perfil inválido")
        sets.append("role=?"); vals.append(d["role"])
    if "active" in d:
        sets.append("active=?"); vals.append(flag(d["active"]))
    if d.get("password"):
        if len(d["password"]) < 8:
            raise ApiError("A senha deve ter ao menos 8 caracteres", field="password")
        sets += ["password_hash=?", "must_change_pw=1", "failed_logins=0", "locked_until=NULL"]
        vals.append(generate_password_hash(d["password"]))
    if not sets:
        return jsonify(ok=True)
    with tx(db):
        db.execute(f"UPDATE users SET {','.join(sets)} WHERE id=?", vals + [uid])
        if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0] == 0:
            raise ApiError("Deve existir ao menos um administrador ativo")
        audit(db, cu(), "usuario.alterar", "user", uid, {k: ("[nova senha]" if k == "password" else v) for k, v in d.items()}, ip())
    return jsonify(ok=True)


@app.get("/api/sellers")
@admin_required
def sellers():
    return jsonify(q(get_db(), "SELECT id,name,avatar FROM users WHERE role='vendedor' AND active=1 ORDER BY name"))


# ------------------------------------------------------------------ categorias e fornecedores
@app.get("/api/categories")
@login_required
def categories():
    return jsonify(q(get_db(), "SELECT id,name,active FROM categories ORDER BY id"))


@app.post("/api/categories")
@admin_required
def categories_create():
    name = need(body(), "name", "o nome")
    cid = get_db().execute("INSERT INTO categories(name) VALUES(?)", (name,)).lastrowid
    return jsonify(id=cid), 201


@app.get("/api/suppliers")
@admin_required
def suppliers():
    return jsonify(q(get_db(), "SELECT * FROM suppliers ORDER BY name"))


@app.post("/api/suppliers")
@admin_required
def suppliers_create():
    d, db = body(), get_db()
    sid = db.execute("INSERT INTO suppliers(name,doc,phone,email,notes) VALUES(?,?,?,?,?)",
                     (need(d, "name", "o nome"), s(d.get("doc"), 20), s(d.get("phone"), 30), s(d.get("email"), 100), s(d.get("notes"), 500))).lastrowid
    return jsonify(id=sid), 201


@app.put("/api/suppliers/<int:sid>")
@admin_required
def suppliers_update(sid):
    d, db = body(), get_db()
    db.execute("UPDATE suppliers SET name=?,doc=?,phone=?,email=?,notes=?,active=? WHERE id=?",
               (need(d, "name", "o nome"), s(d.get("doc"), 20), s(d.get("phone"), 30), s(d.get("email"), 100), s(d.get("notes"), 500),
                flag(d.get("active", 1)), sid))
    return jsonify(ok=True)


# ------------------------------------------------------------------ produtos e estoque
def public_product(p):
    return {k: p[k] for k in ("id", "sku", "name", "category_id", "category", "brand", "model", "description",
                              "sale_price", "stock_qty", "unit", "kind", "active")} | {"low": p["stock_qty"] <= p["min_stock"] and p["kind"] == "product"}


@app.get("/api/products")
@login_required
def products_list():
    db, a, u = get_db(), request.args, cu()
    where, par = [], []
    if a.get("q"):
        like = f"%{a['q'].strip()}%"
        where.append("(p.name LIKE ? OR p.sku LIKE ? OR p.brand LIKE ? OR p.model LIKE ?)")
        par += [like] * 4
    if a.get("category_id"):
        where.append("p.category_id=?"); par.append(a["category_id"])
    if a.get("kind") in ("product", "service"):
        where.append("p.kind=?"); par.append(a["kind"])
    if a.get("low") == "1":
        where.append("p.kind='product' AND p.stock_qty<=p.min_stock")
    if u["role"] != "admin":
        where.append("p.active=1")
    elif a.get("active") in ("0", "1"):
        where.append("p.active=?"); par.append(a["active"])
    sql = ("SELECT p.*, c.name category, s.name supplier FROM products p LEFT JOIN categories c ON c.id=p.category_id "
           "LEFT JOIN suppliers s ON s.id=p.supplier_id" + (" WHERE " + " AND ".join(where) if where else "") +
           " ORDER BY p.name LIMIT 500")
    rows = q(db, sql, par)
    if u["role"] != "admin":
        rows = [public_product(p) for p in rows]   # vendedor NUNCA recebe custo/fornecedor/estoque mínimo
    return jsonify(rows)


def product_fields(d, partial=False):
    out = {}
    if not partial or "sku" in d:
        out["sku"] = need(d, "sku", "o código/SKU").upper()
    if not partial or "name" in d:
        out["name"] = need(d, "name", "o nome")
    if "category_id" in d:
        out["category_id"] = to_int(d["category_id"], "categoria", 1) if d["category_id"] else None
    for k in ("brand", "model", "unit"):
        if k in d:
            out[k] = s(d[k], 60) or ("un" if k == "unit" else None)
    if "description" in d:
        out["description"] = s(d["description"], 1000)
    for k, lbl in (("cost_price", "custo"), ("sale_price", "preço de venda")):
        if k in d:
            out[k] = to_int(d[k], lbl)
    if "min_stock" in d:
        out["min_stock"] = to_qty(d["min_stock"], "estoque mínimo") if float(d["min_stock"] or 0) > 0 else 0
    if "supplier_id" in d:
        out["supplier_id"] = to_int(d["supplier_id"], "fornecedor", 1) if d["supplier_id"] else None
    if "kind" in d:
        if d["kind"] not in ("product", "service"):
            raise ApiError("Tipo inválido")
        out["kind"] = d["kind"]
    if "active" in d:
        out["active"] = flag(d["active"])
    return out


@app.post("/api/products")
@admin_required
def products_create():
    d, db = body(), get_db()
    f = product_fields(d)
    init = float(d.get("stock_qty") or 0)
    if init < 0:
        raise ApiError("Estoque inicial inválido", field="stock_qty")
    f["created_at"] = now_s()
    with tx(db):
        pid = db.execute(f"INSERT INTO products({','.join(f)}) VALUES({','.join('?'*len(f))})", list(f.values())).lastrowid
        if init > 0 and f.get("kind", "product") == "product":
            db.execute("UPDATE products SET stock_qty=? WHERE id=?", (init, pid))
            db.execute("INSERT INTO stock_movements(product_id,type,qty,balance_after,unit_cost,reason,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       (pid, "entrada", init, init, f.get("cost_price"), "Estoque inicial", cu()["id"], now_s()))
        audit(db, cu(), "produto.criar", "product", pid, {"sku": f["sku"]}, ip())
    return jsonify(id=pid), 201


@app.put("/api/products/<int:pid>")
@admin_required
def products_update(pid):
    d, db = body(), get_db()
    old = q1(db, "SELECT * FROM products WHERE id=?", (pid,))
    if not old:
        raise ApiError("Produto não encontrado", 404)
    f = product_fields(d, partial=True)  # estoque NÃO é editável aqui: só via movimentação
    if not f:
        return jsonify(ok=True)
    with tx(db):
        db.execute(f"UPDATE products SET {','.join(k+'=?' for k in f)} WHERE id=?", list(f.values()) + [pid])
        ch = {k: [old[k], v] for k, v in f.items() if old[k] != v}
        audit(db, cu(), "produto.alterar", "product", pid, ch, ip())
    return jsonify(ok=True)


@app.post("/api/stock/move")
@admin_required
def stock_move():
    d, db, u = body(), get_db(), cu()
    t = d.get("type")
    if t not in ("entrada", "saida", "ajuste"):
        raise ApiError("Tipo de movimentação inválido", field="type")
    reason = s(d.get("reason"), 300)
    if t != "entrada" and not reason:
        raise ApiError("Informe o motivo", field="reason")
    with tx(db):
        p = q1(db, "SELECT * FROM products WHERE id=?", (d.get("product_id"),))
        if not p:
            raise ApiError("Produto não encontrado", 404)
        if p["kind"] != "product":
            raise ApiError("Serviços não possuem estoque")
        if t == "ajuste":
            try:
                counted = round(float(d.get("qty")), 3)
            except (TypeError, ValueError):
                raise ApiError("Quantidade inválida", field="qty")
            if counted < 0:
                raise ApiError("Quantidade contada não pode ser negativa", field="qty")
            delta, bal = round(counted - p["stock_qty"], 3), counted
        else:
            qty = to_qty(d.get("qty"))
            delta = qty if t == "entrada" else -qty
            bal = round(p["stock_qty"] + delta, 3)
            if bal < 0:
                raise ApiError(f"Saída maior que o estoque ({p['stock_qty']:g})", 409, "qty")
        uc = None
        if t == "entrada" and d.get("unit_cost") not in (None, ""):
            uc = to_int(d["unit_cost"], "custo unitário")
            db.execute("UPDATE products SET cost_price=? WHERE id=?", (uc, p["id"]))
        db.execute("UPDATE products SET stock_qty=? WHERE id=?", (bal, p["id"]))
        db.execute("INSERT INTO stock_movements(product_id,type,qty,balance_after,unit_cost,reason,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                   (p["id"], t, delta, bal, uc, reason or (f"Fornecedor: {s(d.get('supplier'))}" if d.get("supplier") else None), u["id"], now_s()))
        audit(db, u, "estoque." + t, "product", p["id"], {"delta": delta, "saldo": bal, "motivo": reason}, ip())
    return jsonify(balance=bal)


@app.get("/api/stock/movements")
@admin_required
def stock_movements():
    a = request.args
    where, par = [], []
    if a.get("product_id"):
        where.append("m.product_id=?"); par.append(a["product_id"])
    if a.get("type"):
        where.append("m.type=?"); par.append(a["type"])
    if a.get("category_id"):
        where.append("p.category_id=?"); par.append(a["category_id"])
    if a.get("from"):
        where.append("m.created_at>=?"); par.append(a["from"] + " 00:00:00")
    if a.get("to"):
        where.append("m.created_at<?"); par.append(_next_day(a["to"]) + " 00:00:00")
    sql = ("SELECT m.*, p.sku, p.name product, p.unit, u.name user FROM stock_movements m JOIN products p ON p.id=m.product_id "
           "LEFT JOIN users u ON u.id=m.user_id" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY m.id DESC LIMIT 500")
    return jsonify(q(get_db(), sql, par))


# ------------------------------------------------------------------ pacotes
def package_full(db, pkg, admin):
    items = q(db, "SELECT pi.*, p.name, p.sku, p.unit, p.kind, p.stock_qty, p.cost_price FROM package_items pi "
                  "JOIN products p ON p.id=pi.product_id WHERE pi.package_id=? ORDER BY pi.id", (pkg["id"],))
    avail = None
    for it in items:
        if it["kind"] == "product":
            n = int(it["stock_qty"] // it["qty"]) if it["qty"] > 0 else 0
            avail = n if avail is None else min(avail, n)
    out = {"id": pkg["id"], "name": pkg["name"], "description": pkg["description"], "sale_price": pkg["sale_price"],
           "allow_extras": pkg["allow_extras"], "active": pkg["active"], "available": avail}
    if admin:
        cost = sum(L.rnd(it["qty"] * (it["cost_override"] if it["cost_override"] is not None else it["cost_price"])) for it in items)
        rule = q1(db, "SELECT type,value,base FROM commission_rules WHERE scope='package' AND ref_id=? AND active=1", (pkg["id"],))
        out.update(cost_total=cost, gross_profit=pkg["sale_price"] - cost, commission_rule=rule,
                   items=[{k: it[k] for k in ("id", "product_id", "name", "sku", "unit", "qty", "cost_override", "price_alloc", "commission_eligible", "removable")}
                          | {"unit_cost": it["cost_override"] if it["cost_override"] is not None else it["cost_price"]} for it in items])
    else:  # vendedor: nomes e quantidades, sem custos nem rateio interno
        out["items"] = [{"id": it["id"], "name": it["name"], "unit": it["unit"], "qty": it["qty"], "removable": it["removable"],
                         "credit": L.rnd(it["price_alloc"] * it["qty"]) if it["removable"] else 0} for it in items]
    return out


@app.get("/api/packages")
@login_required
def packages_list():
    db, admin = get_db(), cu()["role"] == "admin"
    rows = q(db, "SELECT * FROM packages" + ("" if admin else " WHERE active=1") + " ORDER BY name")
    return jsonify([package_full(db, p, admin) for p in rows])


def save_package(db, pid, d):
    name = need(d, "name", "o nome do pacote")
    price = to_int(d.get("sale_price"), "preço final", 0)
    items = d.get("items") or []
    if not items:
        raise ApiError("Inclua ao menos um componente no pacote", field="items")
    if pid is None:
        pid = db.execute("INSERT INTO packages(name,description,sale_price,allow_extras,active,created_at) VALUES(?,?,?,?,?,?)",
                         (name, s(d.get("description"), 1000), price, flag(d.get("allow_extras", 1)), flag(d.get("active", 1)), now_s())).lastrowid
    else:
        db.execute("UPDATE packages SET name=?,description=?,sale_price=?,allow_extras=?,active=? WHERE id=?",
                   (name, s(d.get("description"), 1000), price, flag(d.get("allow_extras", 1)), flag(d.get("active", 1)), pid))
        db.execute("DELETE FROM package_items WHERE package_id=?", (pid,))
    seen = set()
    for it in items:
        p = q1(db, "SELECT id FROM products WHERE id=?", (it.get("product_id"),))
        if not p:
            raise ApiError("Componente inválido")
        if p["id"] in seen:
            raise ApiError("Componente repetido no pacote — some as quantidades")
        seen.add(p["id"])
        co = it.get("cost_override")
        db.execute("INSERT INTO package_items(package_id,product_id,qty,cost_override,price_alloc,commission_eligible,removable) VALUES(?,?,?,?,?,?,?)",
                   (pid, p["id"], to_qty(it.get("qty", 1)), None if co in (None, "") else to_int(co, "custo do componente"),
                    to_int(it.get("price_alloc") or 0, "valor do componente"), flag(it.get("commission_eligible", 1)), flag(it.get("removable", 0))))
    cr = d.get("commission")
    if cr and cr.get("type") in ("percent", "fixed"):
        try:
            val = float(cr.get("value"))
        except (TypeError, ValueError):
            raise ApiError("Valor de comissão inválido")
        if val < 0 or (cr["type"] == "percent" and val > 100):
            raise ApiError("Valor de comissão inválido")
        base = cr.get("base") if cr.get("base") in ("total", "eligible") else "total"
        db.execute("INSERT INTO commission_rules(scope,ref_id,type,value,base,active,updated_at) VALUES('package',?,?,?,?,1,?) "
                   "ON CONFLICT(scope,ref_id) DO UPDATE SET type=excluded.type,value=excluded.value,base=excluded.base,active=1,updated_at=excluded.updated_at",
                   (pid, cr["type"], val, base, now_s()))
    elif cr is None or cr == {}:
        db.execute("UPDATE commission_rules SET active=0 WHERE scope='package' AND ref_id=?", (pid,))
    return pid


@app.post("/api/packages")
@admin_required
def packages_create():
    db = get_db()
    with tx(db):
        pid = save_package(db, None, body())
        audit(db, cu(), "pacote.criar", "package", pid, None, ip())
    return jsonify(id=pid), 201


@app.put("/api/packages/<int:pid>")
@admin_required
def packages_update(pid):
    db = get_db()
    if not q1(db, "SELECT 1 x FROM packages WHERE id=?", (pid,)):
        raise ApiError("Pacote não encontrado", 404)
    with tx(db):
        save_package(db, pid, body())
        audit(db, cu(), "pacote.alterar", "package", pid, None, ip())
    return jsonify(ok=True)


# ------------------------------------------------------------------ clientes
def seller_customer_filter(u):
    if u["role"] == "admin":
        return "", []
    return " AND (c.created_by=? OR c.id IN (SELECT customer_id FROM sales WHERE seller_id=?))", [u["id"], u["id"]]


@app.get("/api/customers")
@login_required
def customers_list():
    u, a = cu(), request.args
    extra, par = seller_customer_filter(u)
    where = "1=1" + extra
    if a.get("q"):
        like = f"%{a['q'].strip()}%"
        where += " AND (c.name LIKE ? OR c.doc LIKE ? OR c.phone LIKE ? OR c.whatsapp LIKE ?)"
        par += [like, like, f"%{digits(a['q'])}%" if digits(a["q"]) else like, like]
    rows = q(get_db(), f"SELECT c.id,c.name,c.doc,c.phone,c.whatsapp,c.email,c.address,c.city,c.notes,c.created_at, "
                       f"(SELECT COUNT(*) FROM sales s WHERE s.customer_id=c.id AND s.status='confirmed'"
                       f"{'' if u['role']=='admin' else ' AND s.seller_id='+str(u['id'])}) purchases, "
                       f"(SELECT MAX(created_at) FROM sales s WHERE s.customer_id=c.id AND s.status='confirmed'"
                       f"{'' if u['role']=='admin' else ' AND s.seller_id='+str(u['id'])}) last_purchase "
                       f"FROM customers c WHERE {where} ORDER BY c.name LIMIT 300", par)
    return jsonify(rows)


def customer_fields(d):
    name = need(d, "name", "o nome do cliente")
    doc = digits(d.get("doc"))
    if doc and not (valid_cpf(doc) or valid_cnpj(doc)):
        raise ApiError("CPF/CNPJ inválido", field="doc")
    email = s(d.get("email"), 100)
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ApiError("E-mail inválido", field="email")
    return dict(name=name, doc=doc or None, phone=digits(d.get("phone"))[:15] or None, whatsapp=digits(d.get("whatsapp"))[:15] or None,
                email=email or None, address=s(d.get("address"), 300) or None, city=s(d.get("city"), 80) or None, notes=s(d.get("notes"), 1000) or None)


@app.post("/api/customers")
@login_required
def customers_create():
    db, u = get_db(), cu()
    f = customer_fields(body())
    if f["doc"] and q1(db, "SELECT 1 x FROM customers WHERE doc=?", (f["doc"],)):
        raise ApiError("CPF/CNPJ já cadastrado." + ("" if u["role"] == "admin" else " Peça ao administrador para vinculá-lo a você."), 409, "doc")
    f.update(created_by=u["id"], created_at=now_s())
    cid = db.execute(f"INSERT INTO customers({','.join(f)}) VALUES({','.join('?'*len(f))})", list(f.values())).lastrowid
    audit(db, u, "cliente.criar", "customer", cid, None, ip())
    return jsonify(id=cid, name=f["name"]), 201


@app.put("/api/customers/<int:cid>")
@login_required
def customers_update(cid):
    db, u = get_db(), cu()
    extra, par = seller_customer_filter(u)
    if not q1(db, "SELECT 1 x FROM customers c WHERE c.id=?" + extra, [cid] + par):
        raise ApiError("Cliente não encontrado", 404)
    f = customer_fields(body())
    if f["doc"] and q1(db, "SELECT 1 x FROM customers WHERE doc=? AND id<>?", (f["doc"], cid)):
        raise ApiError("CPF/CNPJ já cadastrado em outro cliente", 409, "doc")
    db.execute(f"UPDATE customers SET {','.join(k+'=?' for k in f)} WHERE id=?", list(f.values()) + [cid])
    audit(db, u, "cliente.alterar", "customer", cid, None, ip())
    return jsonify(ok=True)


@app.get("/api/customers/<int:cid>")
@login_required
def customers_get(cid):
    db, u = get_db(), cu()
    extra, par = seller_customer_filter(u)
    c = q1(db, "SELECT c.* FROM customers c WHERE c.id=?" + extra, [cid] + par)
    if not c:
        raise ApiError("Cliente não encontrado", 404)
    sf, sp = ("", []) if u["role"] == "admin" else (" AND s.seller_id=?", [u["id"]])
    c["sales"] = q(db, "SELECT s.id,s.number,s.created_at,s.total,s.status,s.payment_method,u.name seller FROM sales s JOIN users u ON u.id=s.seller_id "
                       "WHERE s.customer_id=?" + sf + " ORDER BY s.id DESC", [cid] + sp)
    return jsonify(c)


# ------------------------------------------------------------------ vendas
def pay_label(m):
    return m


@app.post("/api/sales/preview")
@login_required
def sale_preview():
    db, u = get_db(), cu()
    d = body()
    seller = u
    if u["role"] == "admin" and d.get("seller_id"):
        seller = q1(db, "SELECT id,name,role FROM users WHERE id=? AND role='vendedor' AND active=1", (d["seller_id"],)) or u
    p = L.build_sale(db, seller, d, u)
    out = {"gross": p["gross"], "discount": p["discount"], "freight": p["freight"], "install": p["install"], "other": p["other"],
           "total": p["total"], "stock_issues": p["stock_issues"], "commission": p["commission"]["amount"],
           "lines": [{"name": l["name"], "qty": l["qty"], "unit_price": l["unit_price"], "total": l["line_total"],
                      "components": [{"name": c["name"], "qty": c["qty"]} for c in l["comps"]]} for l in p["lines"]]}
    if u["role"] == "admin":
        out.update(cost_total=p["cost_total"], gross_profit=p["gross_profit"])
    return jsonify(out)


@app.post("/api/sales")
@login_required
def sale_create():
    db, u, d = get_db(), cu(), body()
    key = s(d.get("idempotency_key"), 80)
    if not key:
        raise ApiError("Chave de operação ausente")
    seller = u
    if u["role"] == "admin" and d.get("seller_id"):
        seller = q1(db, "SELECT id,name,role FROM users WHERE id=? AND role='vendedor' AND active=1", (d["seller_id"],))
        if not seller:
            raise ApiError("Vendedor inválido", field="seller_id")
    with tx(db):
        plan = L.build_sale(db, seller, d, u)
        sid, dup = L.commit_sale(db, plan, seller, u, idem_key=key)
    row = q1(db, "SELECT number,total FROM sales WHERE id=?", (sid,))
    return jsonify(id=sid, number=row["number"], total=row["total"], duplicate=dup), 200 if dup else 201


def sale_visible(db, sid, u):
    s_ = q1(db, "SELECT s.*, c.name customer_name, u.name seller_name FROM sales s JOIN customers c ON c.id=s.customer_id "
                "JOIN users u ON u.id=s.seller_id WHERE s.id=?", (sid,))
    if not s_ or (u["role"] != "admin" and s_["seller_id"] != u["id"]):
        raise ApiError("Venda não encontrada", 404)  # 404 (e não 403) para não revelar existência
    return s_


@app.get("/api/sales")
@login_required
def sales_list():
    db, u, a = get_db(), cu(), request.args
    f, t, t0, t1 = period({"from": a.get("from") or "2000-01-01", "to": a.get("to") or "2999-12-31"})
    where, par = ["s.created_at>=?", "s.created_at<?"], [t0, t1]
    if u["role"] != "admin":
        where.append("s.seller_id=?"); par.append(u["id"])
    elif a.get("seller_id"):
        where.append("s.seller_id=?"); par.append(a["seller_id"])
    if a.get("status") in ("confirmed", "cancelled", "refunded"):
        where.append("s.status=?"); par.append(a["status"])
    if a.get("customer_id"):
        where.append("s.customer_id=?"); par.append(a["customer_id"])
    if a.get("q"):
        where.append("(s.number LIKE ? OR c.name LIKE ?)"); par += [f"%{a['q']}%"] * 2
    cols = "s.id,s.number,s.created_at,s.status,s.total,s.payment_method,s.installments,c.name customer,u.name seller"
    if u["role"] == "admin":
        cols += ",s.cost_total+s.freight_cost+s.install_cost+s.other_cost cost,s.gross_profit,s.costs_confirmed,sc.amount commission,sc.status commission_status"
    else:
        cols += ",sc.amount commission,sc.status commission_status"
    rows = q(db, f"SELECT {cols} FROM sales s JOIN customers c ON c.id=s.customer_id JOIN users u ON u.id=s.seller_id "
                 f"LEFT JOIN sale_commissions sc ON sc.sale_id=s.id AND sc.kind='normal' WHERE {' AND '.join(where)} ORDER BY s.id DESC LIMIT 500", par)
    return jsonify(rows)


@app.get("/api/sales/<int:sid>")
@login_required
def sale_get(sid):
    db, u = get_db(), cu()
    s_ = sale_visible(db, sid, u)
    admin = u["role"] == "admin"
    items = q(db, "SELECT id,parent_id,kind,product_id,package_id,name,qty,unit_price,line_total,net_revenue,unit_cost,cost_total FROM sale_items WHERE sale_id=? ORDER BY id", (sid,))
    if not admin:
        items = [{k: v for k, v in it.items() if k not in ("unit_cost", "cost_total", "net_revenue")} for it in items]
    cm = q1(db, "SELECT id,kind,amount,status,base,snapshot,created_at,approved_at,paid_at FROM sale_commissions WHERE sale_id=? AND kind='normal'", (sid,))
    if cm and not admin:
        cm.pop("snapshot", None)
    s_["items"], s_["commission"] = items, cm
    if admin:
        s_["receivables"] = q(db, "SELECT * FROM receivables WHERE sale_id=? ORDER BY installment_no", (sid,))
    else:
        for k in ("cost_total", "freight_cost", "install_cost", "other_cost", "gross_profit", "costs_confirmed", "idem_key", "cancelled_by"):
            s_.pop(k, None)
    cust = q1(db, "SELECT name,doc,phone,whatsapp,address,city FROM customers WHERE id=?", (s_["customer_id"],))
    s_["customer"] = cust
    s_["store"] = {k: v for k, v in get_settings(db).items() if k in ("store_name", "store_tagline", "logo")}
    return jsonify(s_)


@app.post("/api/sales/<int:sid>/cancel")
@admin_required
def sale_cancel(sid):
    d, db = body(), get_db()
    reason = s(d.get("reason"), 500)
    if not reason:
        raise ApiError("Informe o motivo do cancelamento", field="reason")
    with tx(db):
        L.cancel_sale(db, sid, cu(), d.get("status", "cancelled"), reason)
    return jsonify(ok=True)


@app.put("/api/sales/<int:sid>/costs")
@admin_required
def sale_costs(sid):
    d, db = body(), get_db()
    with tx(db):
        sl = q1(db, "SELECT * FROM sales WHERE id=?", (sid,))
        if not sl:
            raise ApiError("Venda não encontrada", 404)
        fc, ic, oc = (to_int(d.get(k, 0), k) for k in ("freight_cost", "install_cost", "other_cost"))
        gp = sl["total"] - sl["cost_total"] - fc - ic - oc
        db.execute("UPDATE sales SET freight_cost=?,install_cost=?,other_cost=?,costs_confirmed=1,gross_profit=? WHERE id=?", (fc, ic, oc, gp, sid))
        audit(db, cu(), "venda.custos", "sale", sid, {"frete": fc, "instalacao": ic, "outros": oc}, ip())
    return jsonify(gross_profit=gp)


# ------------------------------------------------------------------ comissões
@app.get("/api/commission-rules")
@admin_required
def rules_list():
    return jsonify(q(get_db(), "SELECT r.*, CASE r.scope WHEN 'category' THEN (SELECT name FROM categories WHERE id=r.ref_id) "
                               "WHEN 'product' THEN (SELECT name FROM products WHERE id=r.ref_id) "
                               "WHEN 'package' THEN (SELECT name FROM packages WHERE id=r.ref_id) ELSE 'Padrão (todos os produtos sem regra específica)' END ref_name "
                               "FROM commission_rules r ORDER BY CASE scope WHEN 'default' THEN 0 WHEN 'category' THEN 1 WHEN 'product' THEN 2 ELSE 3 END, id"))


@app.put("/api/commission-rules")
@admin_required
def rules_put():
    d, db = body(), get_db()
    scope, ref = d.get("scope"), int(d.get("ref_id") or 0)
    if scope not in ("default", "category", "product", "package"):
        raise ApiError("Escopo inválido")
    if scope != "default" and not ref:
        raise ApiError("Selecione o item da regra", field="ref_id")
    if d.get("type") not in ("percent", "fixed"):
        raise ApiError("Tipo inválido", field="type")
    try:
        val = float(d.get("value"))
    except (TypeError, ValueError):
        raise ApiError("Valor inválido", field="value")
    if val < 0 or (d["type"] == "percent" and val > 100):
        raise ApiError("Valor inválido", field="value")
    base = d.get("base") if d.get("base") in ("line", "total", "eligible") else ("total" if scope == "package" else "line")
    with tx(db):
        db.execute("INSERT INTO commission_rules(scope,ref_id,type,value,base,active,note,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                   "ON CONFLICT(scope,ref_id) DO UPDATE SET type=excluded.type,value=excluded.value,base=excluded.base,"
                   "active=excluded.active,note=excluded.note,updated_at=excluded.updated_at",
                   (scope, 0 if scope == "default" else ref, d["type"], val, base, flag(d.get("active", 1)), s(d.get("note"), 200), now_s()))
        audit(db, cu(), "comissao.regra", "commission_rule", f"{scope}:{ref}", {"type": d["type"], "value": val, "base": base}, ip())
    return jsonify(ok=True)


@app.delete("/api/commission-rules/<int:rid>")
@admin_required
def rules_delete(rid):
    db = get_db()
    r = q1(db, "SELECT * FROM commission_rules WHERE id=?", (rid,))
    if not r:
        raise ApiError("Regra não encontrada", 404)
    if r["scope"] == "default":
        raise ApiError("A regra padrão não pode ser removida; altere o valor.")
    db.execute("DELETE FROM commission_rules WHERE id=?", (rid,))
    audit(db, cu(), "comissao.regra.remover", "commission_rule", rid, None, ip())
    return jsonify(ok=True)


@app.get("/api/commissions")
@login_required
def commissions_list():
    db, u, a = get_db(), cu(), request.args
    f, t, t0, t1 = period({"from": a.get("from") or "2000-01-01", "to": a.get("to") or "2999-12-31"})
    where, par = ["s.created_at>=?", "s.created_at<?"], [t0, t1]
    if u["role"] != "admin":
        where.append("sc.seller_id=?"); par.append(u["id"])
    elif a.get("seller_id"):
        where.append("sc.seller_id=?"); par.append(a["seller_id"])
    if a.get("status") in ("prevista", "aprovada", "paga", "cancelada"):
        where.append("sc.status=?"); par.append(a["status"])
    rows = q(db, "SELECT sc.id,sc.sale_id,sc.kind,sc.base,sc.amount,sc.status,sc.note,sc.created_at,sc.approved_at,sc.paid_at,"
                 "s.number,s.total,s.status sale_status,s.created_at sale_date,c.name customer,u.name seller "
                 "FROM sale_commissions sc JOIN sales s ON s.id=sc.sale_id JOIN customers c ON c.id=s.customer_id JOIN users u ON u.id=sc.seller_id "
                 f"WHERE {' AND '.join(where)} ORDER BY sc.id DESC LIMIT 500", par)
    tot = {"prevista": 0, "aprovada": 0, "paga": 0}
    for r in rows:
        if r["status"] in tot:
            tot[r["status"]] += r["amount"]
    return jsonify(rows=rows, totals=tot)


@app.post("/api/commissions/status")
@admin_required
def commissions_status():
    d, db = body(), get_db()
    ids, new = d.get("ids") or [], d.get("status")
    if new not in ("aprovada", "paga", "cancelada") or not ids:
        raise ApiError("Dados inválidos")
    allowed = {"aprovada": ("prevista",), "paga": ("aprovada",), "cancelada": ("prevista", "aprovada")}[new]
    done = 0
    with tx(db):
        for i in ids:
            c = q1(db, "SELECT * FROM sale_commissions WHERE id=?", (i,))
            if not c or c["status"] not in allowed:
                continue
            if new == "cancelada" and c["kind"] == "estorno":
                continue
            ts = now_s()
            db.execute("UPDATE sale_commissions SET status=?, approved_at=COALESCE(approved_at, ?), paid_at=? WHERE id=?",
                       (new, ts if new in ("aprovada", "paga") else None, ts if new == "paga" else c["paid_at"], i))
            done += 1
        audit(db, cu(), "comissao." + new, "sale_commission", ",".join(map(str, ids)), {"alteradas": done}, ip())
    return jsonify(changed=done)


# ------------------------------------------------------------------ metas
@app.get("/api/goals")
@admin_required
def goals_list():
    db, month = get_db(), request.args.get("month") or D.now().strftime("%Y-%m")
    L.month_bounds(month)
    rows = []
    for sl in q(db, "SELECT id,name,avatar FROM users WHERE role='vendedor' AND active=1 ORDER BY name"):
        rows.append(sl | L.seller_month(db, sl["id"], month))
    return jsonify(month=month, rows=rows)


@app.put("/api/goals")
@admin_required
def goals_put():
    d, db = body(), get_db()
    month = s(d.get("month"), 7)
    L.month_bounds(month)
    amount = to_int(d.get("amount"), "meta")
    sl = q1(db, "SELECT id FROM users WHERE id=? AND role='vendedor'", (d.get("seller_id"),))
    if not sl:
        raise ApiError("Vendedor inválido", field="seller_id")
    with tx(db):
        db.execute("INSERT INTO goals(seller_id,month,amount) VALUES(?,?,?) ON CONFLICT(seller_id,month) DO UPDATE SET amount=excluded.amount",
                   (sl["id"], month, amount))
        audit(db, cu(), "meta.definir", "goal", f"{sl['id']}:{month}", {"valor": amount}, ip())
    return jsonify(ok=True)


@app.get("/api/goals/history")
@login_required
def goals_history():
    db, u = get_db(), cu()
    sid = u["id"] if u["role"] != "admin" else int(request.args.get("seller_id") or 0)
    if not sid:
        raise ApiError("Informe o vendedor")
    months = {r["m"] for r in q(db, "SELECT DISTINCT substr(created_at,1,7) m FROM sales WHERE seller_id=?", (sid,))} | \
             {r["month"] for r in q(db, "SELECT month FROM goals WHERE seller_id=?", (sid,))}
    return jsonify([L.seller_month(db, sid, m) for m in sorted(months, reverse=True)][:24])


@app.get("/api/dashboard/seller")
@login_required
def dash_seller():
    u = cu()
    if u["role"] == "admin" and request.args.get("seller_id"):
        sid = int(request.args["seller_id"])
    else:
        sid = u["id"]
    db = get_db()
    d = L.seller_dashboard(db, sid)
    usr = q1(db, "SELECT id,name,avatar FROM users WHERE id=?", (sid,))
    return jsonify(d | {"seller": usr})


# ------------------------------------------------------------------ financeiro e relatórios
import reports as R  # noqa: E402


@app.get("/api/dashboard/admin")
@admin_required
def dash_admin():
    return jsonify(R.admin_dashboard(get_db(), request.args))


@app.get("/api/finance/receivables")
@admin_required
def receivables_list():
    return jsonify(R.receivables(get_db(), request.args))


@app.post("/api/finance/receivables/<int:rid>/receive")
@admin_required
def receivable_receive(rid):
    db = get_db()
    with tx(db):
        r = q1(db, "SELECT * FROM receivables WHERE id=?", (rid,))
        if not r or r["status"] != "pendente":
            raise ApiError("Parcela não está pendente", 409)
        db.execute("UPDATE receivables SET status='recebido', received_at=? WHERE id=?", (now_s(), rid))
        audit(db, cu(), "recebimento", "receivable", rid, {"valor": r["amount"]}, ip())
    return jsonify(ok=True)


@app.get("/api/finance/payables")
@admin_required
def payables_list():
    return jsonify(R.payables(get_db(), request.args))


def payable_fields(d):
    cat = d.get("category", "despesa")
    if cat not in ("despesa", "fornecedor", "frete", "instalacao", "outros"):
        raise ApiError("Categoria inválida", field="category")
    due = s(d.get("due_date"), 10)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", due):
        raise ApiError("Informe o vencimento", field="due_date")
    amount = to_int(d.get("amount"), "valor", 1)
    return dict(description=need(d, "description", "a descrição"), category=cat, amount=amount, due_date=due,
                supplier_id=d.get("supplier_id") or None, notes=s(d.get("notes"), 500) or None)


@app.post("/api/finance/payables")
@admin_required
def payables_create():
    db = get_db()
    f = payable_fields(body())
    n = int(body().get("repeat") or 1)
    if not 1 <= n <= 36:
        raise ApiError("Repetições devem ser entre 1 e 36")
    ids = []
    with tx(db):
        for i in range(n):
            g_ = dict(f, due_date=L.add_months(f["due_date"], i), created_at=now_s())
            if n > 1:
                g_["description"] = f"{f['description']} ({i+1}/{n})"
            ids.append(db.execute(f"INSERT INTO payables({','.join(g_)}) VALUES({','.join('?'*len(g_))})", list(g_.values())).lastrowid)
        audit(db, cu(), "conta_pagar.criar", "payable", ids[0], {"parcelas": n}, ip())
    return jsonify(ids=ids), 201


@app.put("/api/finance/payables/<int:pid>")
@admin_required
def payables_update(pid):
    db = get_db()
    r = q1(db, "SELECT * FROM payables WHERE id=?", (pid,))
    if not r or r["status"] != "pendente":
        raise ApiError("Só contas pendentes podem ser editadas", 409)
    f = payable_fields(body())
    db.execute(f"UPDATE payables SET {','.join(k+'=?' for k in f)} WHERE id=?", list(f.values()) + [pid])
    return jsonify(ok=True)


@app.post("/api/finance/payables/<int:pid>/<action>")
@admin_required
def payables_action(pid, action):
    db = get_db()
    if action not in ("pay", "cancel"):
        abort(404)
    with tx(db):
        r = q1(db, "SELECT * FROM payables WHERE id=?", (pid,))
        if not r or r["status"] != "pendente":
            raise ApiError("Conta não está pendente", 409)
        if action == "pay":
            db.execute("UPDATE payables SET status='pago', paid_at=? WHERE id=?", (now_s(), pid))
        else:
            db.execute("UPDATE payables SET status='cancelado' WHERE id=?", (pid,))
        audit(db, cu(), "conta_pagar." + action, "payable", pid, {"valor": r["amount"]}, ip())
    return jsonify(ok=True)


@app.get("/api/finance/cashflow")
@admin_required
def cashflow():
    return jsonify(R.cashflow(get_db(), request.args))


@app.get("/api/reports/<name>")
@admin_required
def report(name):
    rep = R.build_report(get_db(), name, request.args)
    fmt = request.args.get("format", "json")
    if fmt == "json":
        return jsonify(rep)
    if fmt == "xlsx":
        return send_file(R.export_xlsx(rep), as_attachment=True, download_name=f"{name}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if fmt == "pdf":
        return send_file(R.export_pdf(rep, get_settings(get_db())["store_name"]), as_attachment=True, download_name=f"{name}.pdf",
                         mimetype="application/pdf")
    raise ApiError("Formato inválido")


@app.get("/api/audit")
@admin_required
def audit_list():
    return jsonify(q(get_db(), "SELECT * FROM audit_log ORDER BY id DESC LIMIT 300"))


# ------------------------------------------------------------------ backup
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(os.path.dirname(D.DB_PATH), "backups"))


def do_backup(keep=14):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = "piscinas-" + D.now().strftime("%Y%m%d-%H%M%S") + ".db"
    path = os.path.join(BACKUP_DIR, name)
    src, dst = D.connect(), sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    os.chmod(path, 0o600)
    files = sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith(".db"))
    for old in files[:-keep]:
        os.remove(os.path.join(BACKUP_DIR, old))
    return name


@app.get("/api/backups")
@admin_required
def backups_list():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return jsonify([{"name": f, "size": os.path.getsize(os.path.join(BACKUP_DIR, f))}
                    for f in sorted(os.listdir(BACKUP_DIR), reverse=True) if f.endswith(".db")])


@app.post("/api/backups")
@admin_required
def backups_create():
    n = do_backup()
    audit(get_db(), cu(), "backup.criar", "backup", n, None, ip())
    return jsonify(name=n), 201


@app.get("/api/backups/<name>")
@admin_required
def backups_download(name):
    if not re.match(r"^piscinas-\d{8}-\d{6}\.db$", name):
        abort(404)
    p = os.path.join(BACKUP_DIR, name)
    if not os.path.exists(p):
        abort(404)
    return send_file(p, as_attachment=True, download_name=name)


def _backup_loop():
    while True:
        try:
            today = D.now().strftime("%Y%m%d")
            os.makedirs(BACKUP_DIR, exist_ok=True)
            if not any(f.startswith("piscinas-" + today) for f in os.listdir(BACKUP_DIR)):
                do_backup()
        except Exception as e:  # pragma: no cover
            app.logger.error("backup falhou: %s", e)
        time.sleep(3600)


def init_app():
    D.init_db()
    if os.environ.get("AUTO_BACKUP", "1") == "1":
        threading.Thread(target=_backup_loop, daemon=True).start()


if __name__ == "__main__":
    init_app()
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5000")), debug=False, threaded=True)
else:
    init_app()
