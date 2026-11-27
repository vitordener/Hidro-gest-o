"""Banco de dados (SQLite) — esquema, conexão, transações e dados iniciais."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("PISCINAS_DB", os.path.join(BASE, "data", "piscinas.db"))

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.environ.get("STORE_TZ", "America/Sao_Paulo"))
except Exception:  # pragma: no cover
    TZ = timezone(timedelta(hours=-3))


def now():
    return datetime.now(TZ).replace(tzinfo=None)


def now_s():
    return now().strftime("%Y-%m-%d %H:%M:%S")


def today_s():
    return now().strftime("%Y-%m-%d")


def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path, isolation_level=None, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


@contextmanager
def tx(db):
    """Transação atômica (BEGIN IMMEDIATE = lock de escrita; evita corridas de estoque)."""
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def q(db, sql, params=()):
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def q1(db, sql, params=()):
    r = db.execute(sql, params).fetchone()
    return dict(r) if r else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','vendedor')),
  active INTEGER NOT NULL DEFAULT 1,
  avatar TEXT, phone TEXT,
  must_change_pw INTEGER NOT NULL DEFAULT 0,
  failed_logins INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, doc TEXT, phone TEXT, email TEXT, notes TEXT,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  category_id INTEGER REFERENCES categories(id),
  brand TEXT, model TEXT, description TEXT,
  cost_price INTEGER NOT NULL DEFAULT 0 CHECK(cost_price >= 0),
  sale_price INTEGER NOT NULL DEFAULT 0 CHECK(sale_price >= 0),
  stock_qty REAL NOT NULL DEFAULT 0,
  min_stock REAL NOT NULL DEFAULT 0,
  supplier_id INTEGER REFERENCES suppliers(id),
  unit TEXT NOT NULL DEFAULT 'un',
  kind TEXT NOT NULL DEFAULT 'product' CHECK(kind IN ('product','service')),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_products_cat ON products(category_id);

CREATE TABLE IF NOT EXISTS stock_movements(
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  type TEXT NOT NULL CHECK(type IN ('entrada','saida','ajuste','venda','estorno')),
  qty REAL NOT NULL,
  balance_after REAL NOT NULL,
  unit_cost INTEGER,
  reason TEXT,
  sale_id INTEGER,
  user_id INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mov_prod ON stock_movements(product_id, created_at);

CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  doc TEXT, phone TEXT, whatsapp TEXT, email TEXT,
  address TEXT, city TEXT, notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_customers_doc ON customers(doc) WHERE doc IS NOT NULL AND doc <> '';

CREATE TABLE IF NOT EXISTS packages(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  sale_price INTEGER NOT NULL CHECK(sale_price >= 0),
  allow_extras INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS package_items(
  id INTEGER PRIMARY KEY,
  package_id INTEGER NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty REAL NOT NULL CHECK(qty > 0),
  cost_override INTEGER,
  price_alloc INTEGER NOT NULL DEFAULT 0,
  commission_eligible INTEGER NOT NULL DEFAULT 1,
  removable INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS commission_rules(
  id INTEGER PRIMARY KEY,
  scope TEXT NOT NULL CHECK(scope IN ('default','category','product','package')),
  ref_id INTEGER NOT NULL DEFAULT 0,
  type TEXT NOT NULL CHECK(type IN ('percent','fixed')),
  value REAL NOT NULL CHECK(value >= 0),
  base TEXT NOT NULL DEFAULT 'line' CHECK(base IN ('line','total','eligible')),
  active INTEGER NOT NULL DEFAULT 1,
  note TEXT,
  updated_at TEXT,
  UNIQUE(scope, ref_id)
);

CREATE TABLE IF NOT EXISTS sales(
  id INTEGER PRIMARY KEY,
  number TEXT UNIQUE,
  idem_key TEXT UNIQUE,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  seller_id INTEGER NOT NULL REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed','cancelled','refunded')),
  subtotal INTEGER NOT NULL, discount INTEGER NOT NULL DEFAULT 0,
  freight INTEGER NOT NULL DEFAULT 0, install INTEGER NOT NULL DEFAULT 0, other INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL,
  cost_total INTEGER NOT NULL DEFAULT 0,
  freight_cost INTEGER NOT NULL DEFAULT 0, install_cost INTEGER NOT NULL DEFAULT 0, other_cost INTEGER NOT NULL DEFAULT 0,
  costs_confirmed INTEGER NOT NULL DEFAULT 1,
  gross_profit INTEGER NOT NULL DEFAULT 0,
  payment_method TEXT NOT NULL,
  installments INTEGER NOT NULL DEFAULT 1,
  down_payment INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL,
  cancelled_at TEXT, cancel_reason TEXT, cancelled_by INTEGER
);
CREATE INDEX IF NOT EXISTS ix_sales_seller ON sales(seller_id, created_at);
CREATE INDEX IF NOT EXISTS ix_sales_date ON sales(created_at);

CREATE TABLE IF NOT EXISTS sale_items(
  id INTEGER PRIMARY KEY,
  sale_id INTEGER NOT NULL REFERENCES sales(id),
  parent_id INTEGER,
  kind TEXT NOT NULL CHECK(kind IN ('product','package','component')),
  product_id INTEGER REFERENCES products(id),
  package_id INTEGER REFERENCES packages(id),
  name TEXT NOT NULL,
  qty REAL NOT NULL,
  unit_price INTEGER NOT NULL DEFAULT 0,
  line_total INTEGER NOT NULL DEFAULT 0,
  net_revenue INTEGER NOT NULL DEFAULT 0,
  unit_cost INTEGER NOT NULL DEFAULT 0,
  cost_total INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS ix_items_prod ON sale_items(product_id);

CREATE TABLE IF NOT EXISTS sale_commissions(
  id INTEGER PRIMARY KEY,
  sale_id INTEGER NOT NULL REFERENCES sales(id),
  seller_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL DEFAULT 'normal' CHECK(kind IN ('normal','estorno')),
  base INTEGER NOT NULL DEFAULT 0,
  amount INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'prevista' CHECK(status IN ('prevista','aprovada','paga','cancelada')),
  snapshot TEXT,
  note TEXT,
  created_at TEXT NOT NULL, approved_at TEXT, paid_at TEXT,
  UNIQUE(sale_id, kind)
);
CREATE INDEX IF NOT EXISTS ix_comm_seller ON sale_commissions(seller_id, status);

CREATE TABLE IF NOT EXISTS receivables(
  id INTEGER PRIMARY KEY,
  sale_id INTEGER NOT NULL REFERENCES sales(id),
  installment_no INTEGER NOT NULL,
  installments_total INTEGER NOT NULL,
  due_date TEXT NOT NULL,
  amount INTEGER NOT NULL,
  method TEXT,
  status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','recebido','cancelado','estornado')),
  received_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_rec_due ON receivables(status, due_date);

CREATE TABLE IF NOT EXISTS payables(
  id INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'despesa' CHECK(category IN ('despesa','fornecedor','frete','instalacao','estorno','outros')),
  supplier_id INTEGER REFERENCES suppliers(id),
  sale_id INTEGER REFERENCES sales(id),
  amount INTEGER NOT NULL CHECK(amount > 0),
  due_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago','cancelado')),
  paid_at TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pay_due ON payables(status, due_date);

CREATE TABLE IF NOT EXISTS goals(
  id INTEGER PRIMARY KEY,
  seller_id INTEGER NOT NULL REFERENCES users(id),
  month TEXT NOT NULL,
  amount INTEGER NOT NULL CHECK(amount >= 0),
  UNIQUE(seller_id, month)
);

CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY,
  user_id INTEGER, user_name TEXT,
  action TEXT NOT NULL, entity TEXT, entity_id TEXT, detail TEXT, ip TEXT,
  created_at TEXT NOT NULL
);

-- Imutabilidade no próprio banco: histórico não pode ser apagado nem reescrito.
CREATE TRIGGER IF NOT EXISTS trg_sales_nodelete BEFORE DELETE ON sales
BEGIN SELECT RAISE(ABORT,'vendas não podem ser excluídas; use cancelamento/estorno'); END;
CREATE TRIGGER IF NOT EXISTS trg_items_nodelete BEFORE DELETE ON sale_items
BEGIN SELECT RAISE(ABORT,'itens de venda não podem ser excluídos'); END;
CREATE TRIGGER IF NOT EXISTS trg_mov_nodelete BEFORE DELETE ON stock_movements
BEGIN SELECT RAISE(ABORT,'movimentações de estoque não podem ser excluídas'); END;
CREATE TRIGGER IF NOT EXISTS trg_mov_noupdate BEFORE UPDATE ON stock_movements
BEGIN SELECT RAISE(ABORT,'movimentações de estoque não podem ser alteradas'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_nodelete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT,'auditoria é imutável'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_noupdate BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT,'auditoria é imutável'); END;
CREATE TRIGGER IF NOT EXISTS trg_comm_nodelete BEFORE DELETE ON sale_commissions
BEGIN SELECT RAISE(ABORT,'comissões não podem ser excluídas; use cancelamento'); END;
-- Venda: itens e valores de uma venda confirmada nunca mudam depois de gravados.
CREATE TRIGGER IF NOT EXISTS trg_items_noupdate BEFORE UPDATE ON sale_items
BEGIN SELECT RAISE(ABORT,'itens de venda são imutáveis'); END;
"""

DEFAULT_SETTINGS = {
    "store_name": "Aqua Piscinas",
    "store_tagline": "Gestão de vendas e estoque",
    "logo": "",
    "allow_oversell": "0",
    "seller_max_discount_pct": "5",
    "commission_cancel_policy": "clawback",  # clawback | keep_paid
}

CATEGORIES = [
    "Cascos de piscinas", "Bombas e motores", "Filtros", "Aquecedores",
    "Produtos de limpeza", "Pedras e revestimentos", "Acessórios",
    "Materiais de instalação", "Outros produtos", "Serviços (instalação e frete)",
]


def get_settings(db):
    s = dict(DEFAULT_SETTINGS)
    for r in db.execute("SELECT key,value FROM settings"):
        s[r["key"]] = r["value"]
    return s


def init_db(db=None, admin_email=None, admin_password=None):
    """Cria o esquema e os dados mínimos. Idempotente."""
    from werkzeug.security import generate_password_hash
    own = db is None
    db = db or connect()
    db.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    for name in CATEGORIES:
        db.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (name,))
    db.execute(
        "INSERT OR IGNORE INTO commission_rules(scope,ref_id,type,value,base,note,updated_at) "
        "VALUES('default',0,'percent',5,'line','Regra inicial: 5% sobre o valor elegível vendido',?)",
        (now_s(),),
    )
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        email = admin_email or os.environ.get("ADMIN_EMAIL", "admin@loja.com")
        pw = admin_password or os.environ.get("ADMIN_PASSWORD", "admin12345")
        db.execute(
            "INSERT INTO users(name,email,password_hash,role,must_change_pw,created_at) VALUES(?,?,?,?,1,?)",
            ("Administrador", email, generate_password_hash(pw), "admin", now_s()),
        )
    if own:
        db.close()
