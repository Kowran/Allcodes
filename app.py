import os
from datetime import datetime
from typing import Optional, Dict

from flask import (
    Flask, render_template, request, redirect, url_for, flash, make_response
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

# Busca o e-mail do código e retorna o HTML
from leitor import fetch_login_code_email_html

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_fallback_change_me")

# -----------------------------------------------------------------------------
# Banco (SQLite local / Postgres Heroku com psycopg3)
# -----------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")

# Heroku antigo: "postgres://". Convertemos para o dialect do psycopg3.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, future=True)

def ensure_schema():
    """Cria a tabela se não existir."""
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

# -----------------------------------------------------------------------------
# Criptografia de senha (Fernet)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# i18n – textos usados no template
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Rotas
# -----------------------------------------------------------------------------
@app.get("/")
def index():
    lang = get_lang()
    t = T[lang]
    return render_template("index.html", lang=lang, t=t, mensagem=None, email="", service="disney")

@app.post("/")
def index_post():
    lang = get_lang()
    t = T[lang]

    service = (request.form.get("service") or "").strip().lower()
    email = (request.form.get("email") or "").strip()
    senha = (request.form.get("senha") or "").strip()

    with Session(engine) as s:
        found = s.execute(
            text("""SELECT id, platform, email, password_enc, notes, created_at
                    FROM streaming_accounts
                    WHERE platform = :p AND email = :e
                    LIMIT 1"""),
            {"p": service, "e": email},
        ).mappings().first()

    if not found:
        return render_template("index.html", lang=lang, t=t, mensagem=None, email=email, service=service)

    if dec(found["password_enc"]) != senha:
        return render_template("index.html", lang=lang, t=t,
                               mensagem=t["incorrect_password"], email=email, service=service)

    # --- Filtros de assunto por serviço ---
    subject_filter = None
    if service == "disney":
        subject_filter = "Your one-time passcode for Disney+"
    elif service == "netflix":
        subject_filter = "Netflix: Your sign-in code"

    email_html = fetch_login_code_email_html(
        service=service,
        target_email=email,
        lookback_days=7,
        max_scan=200,
        required_subject_substr=subject_filter,  # << Disney e Netflix filtrados por título
    )

    if not email_html:
        safe_notes = (found.get("notes") or "")
        email_html = f"""
        <div>
            <p><strong>E-mail:</strong> {found['email']}</p>
            <p><strong>Serviço:</strong> {found['platform'].capitalize()}</p>
            <p><strong>Status:</strong> ✅ Login válido</p>
            {"<p><em>" + safe_notes + "</em></p>" if safe_notes else ""}
            <p style='color:#666'><em>Não localizei um e-mail recente com código para exibir.</em></p>
        </div>
        """

    return render_template("index.html", lang=lang, t=t,
                           mensagem=email_html, email=email, service=service)

# --- CRUD simples de contas ---
@app.get("/accounts")
def accounts_page():
    lang = get_lang()
    with Session(engine) as s:
        rows = s.execute(text("""
            SELECT id, platform, email, password_enc, notes, created_at
            FROM streaming_accounts
            ORDER BY created_at DESC
        """)).mappings().all()
    return render_template("accounts.html", lang=lang, t=T[lang], accounts=rows)

@app.post("/accounts")
def accounts_create():
    platform = (request.form.get("platform") or "").strip().lower()
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if platform not in {"disney", "netflix", "prime"} or not email or not password:
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
def accounts_delete(acc_id: int):
    with Session(engine) as s:
        s.execute(text("DELETE FROM streaming_accounts WHERE id=:i"), {"i": acc_id})
        s.commit()
    flash("Conta removida.", "info")
    return redirect(url_for("accounts_page"))

# -----------------------------------------------------------------------------
# Run local
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
