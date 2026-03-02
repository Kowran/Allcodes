import os
from datetime import datetime
from typing import Optional, Dict
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash, session
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv, find_dotenv
from werkzeug.security import check_password_hash

load_dotenv(find_dotenv(), override=False)

from leitor import fetch_login_code_email_html  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_fallback_change_me")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, future=True)

def ensure_schema():
    is_sqlite = DATABASE_URL.startswith("sqlite")
    id_col = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "BIGSERIAL PRIMARY KEY"
    with engine.begin() as conn:
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS streaming_accounts (
            id {id_col},
            platform TEXT NOT NULL,
            email TEXT NOT NULL,
            password_enc TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT uq_platform_email UNIQUE (platform, email)
        )
        """))
ensure_schema()

FERNET_KEY = os.environ.get("FERNET_KEY")
if not FERNET_KEY:
    FERNET_KEY = Fernet.generate_key().decode()

cipher = Fernet(FERNET_KEY)

def enc(p: str) -> str:
    return cipher.encrypt((p or "").encode()).decode()

def dec(p_enc: Optional[str]) -> str:
    if not p_enc:
        return ""
    try:
        return cipher.decrypt(p_enc.encode()).decode()
    except (InvalidToken, Exception):
        return "***erro-de-chave***"

T: Dict[str, Dict[str, str]] = {
    "pt": {
        "store_name": "Henrique Store",
        "title": "Buscar Códigos",
        "language_label": "Idioma",
        "whatsapp_icon": "WhatsApp",
        "service_label": "Selecione o serviço",
        "placeholder": "Seu e-mail da conta",
        "password_placeholder": "Sua senha",
        "button": "Buscar",
        "searching": "Buscando…",
        "incorrect_password": "Senha incorreta.",
        "result": "Resultado",
        "not_found": "Conta não encontrada para",
        "help_text": "Precisou de ajuda?",
        "click_here": "Clique aqui",
        "footer_text": "© Henrique Store – Todos os direitos reservados.",
        "instagram": "Instagram",
        "ggmax": "Loja",
        "whatsapp": "WhatsApp",
    }
}

def get_lang() -> str:
    lang = request.cookies.get("lang") or "pt"
    return lang if lang in T else "pt"

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")

def _verify_admin_password(pw: str) -> bool:
    if ADMIN_PASSWORD_HASH:
        try:
            return check_password_hash(ADMIN_PASSWORD_HASH, pw)
        except Exception:
            return False
    if ADMIN_PASSWORD is None:
        return False
    return pw == ADMIN_PASSWORD

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            nxt = request.path or url_for("accounts_page")
            return redirect(url_for("admin_login", next=nxt))
        return view(*args, **kwargs)
    return wrapped

@app.get("/admin/login")
def admin_login():
    nxt = request.args.get("next") or url_for("accounts_page")
    return render_template("admin_login.html", next=nxt)

@app.post("/admin/login")
def admin_login_post():
    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "")
    nxt = request.form.get("next") or url_for("accounts_page")

    if username == ADMIN_USER and _verify_admin_password(password):
        session["is_admin"] = True
        flash("Login efetuado com sucesso.", "success")
        return redirect(nxt)
    else:
        flash("Credenciais inválidas.", "error")
        return redirect(url_for("admin_login", next=nxt))

@app.post("/admin/logout")
def admin_logout():
    session.clear()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("admin_login"))

@app.get("/")
def index():
    lang = get_lang()
    t = T[lang]
    return render_template("index.html", lang=lang, t=t, mensagem=None, email="", service="disney")

# ==============================
# ACCOUNTS COM BUSCA + PAGINAÇÃO
# ==============================
@app.get("/accounts")
@admin_required
def accounts_page():
    lang = get_lang()

    search_email = (request.args.get("search") or "").strip()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10))

    if per_page not in {5, 10, 20, 50}:
        per_page = 10

    offset = (page - 1) * per_page

    where_clause = ""
    params = {}

    if search_email:
        where_clause = "WHERE email LIKE :search"
        params["search"] = f"%{search_email}%"

    with Session(engine) as s:
        total = s.execute(text(f"""
            SELECT COUNT(*) FROM streaming_accounts
            {where_clause}
        """), params).scalar()

        rows = s.execute(text(f"""
            SELECT id, platform, email, password_enc, notes, created_at
            FROM streaming_accounts
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), {**params, "limit": per_page, "offset": offset}).mappings().all()

    total_pages = (total // per_page) + (1 if total % per_page else 0)

    return render_template(
        "accounts.html",
        lang=lang,
        t=T[lang],
        accounts=rows,
        search=search_email,
        page=page,
        per_page=per_page,
        total_pages=total_pages
    )

@app.post("/accounts")
@admin_required
def accounts_create():
    platform = (request.form.get("platform") or "").strip().lower()
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if platform in {"hbomax", "hbo max"}:
        platform = "max"
    if platform == "amazon prime":
        platform = "prime"

    if platform not in {"disney", "netflix", "prime", "amazon", "crunchyroll", "max"} or not email or not password:
        flash("Preencha corretamente plataforma, e-mail e senha.", "error")
        return redirect(url_for("accounts_page"))

    with Session(engine) as s:
        s.execute(text("""
            INSERT INTO streaming_accounts (platform, email, password_enc, notes, created_at)
            VALUES (:p, :e, :pw, :n, :ts)
        """), {"p": platform, "e": email, "pw": enc(password), "n": notes, "ts": datetime.utcnow()})
        s.commit()
    flash("Conta adicionada.", "success")
    return redirect(url_for("accounts_page"))

@app.post("/accounts/<int:acc_id>/delete")
@admin_required
def accounts_delete(acc_id: int):
    with Session(engine) as s:
        s.execute(text("DELETE FROM streaming_accounts WHERE id=:i"), {"i": acc_id})
        s.commit()
    flash("Conta removida.", "info")
    return redirect(url_for("accounts_page"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
