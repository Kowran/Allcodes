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

# Carrega variáveis do .env (funciona mesmo se rodar de outra pasta)
load_dotenv(find_dotenv(), override=False)

# Importa o leitor de e-mails
from leitor import fetch_login_code_email_html  # noqa: E402

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_fallback_change_me")

# -----------------------------------------------------------------------------
# Banco (SQLite local / Postgres Heroku com psycopg3)
# -----------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")

# Ajuste de dialect para psycopg3 quando for Postgres
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
    # OBS: Em produção, defina FERNET_KEY fixa em config vars para não perder a chave.
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
# Autenticação admin (simples por sessão)
# -----------------------------------------------------------------------------
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  # texto puro (opcional)
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")  # hash (opcional)

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

# -----------------------------------------------------------------------------
# Rotas públicas
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

    # Evita buscas IMAP sem filtro em caso de "service" inválido.
    # (Sem isso, um service desconhecido poderia acabar exibindo o e-mail mais recente da caixa.)
    # Mantém alguns aliases por compatibilidade.
    # NOTE: Mantemos alguns aliases por compatibilidade.
    # "max" é o nome atual do serviço (antigo HBO Max) em vários mercados.
    allowed_services = {
        "disney",
        "netflix",
        "prime",
        "amazon",
        "amazon prime",
        "crunchyroll",
        "max",
        "hbomax",
        "hbo max",
    }
    if service not in allowed_services:
        return render_template(
            "index.html",
            lang=lang,
            t=t,
            mensagem="Serviço inválido.",
            email=email,
            service=service,
        )

    # Para compatibilidade com bases já existentes, tentamos achar a conta
    # considerando alguns aliases de plataforma.
    platform_candidates = [service]
    if service in {"prime", "amazon", "amazon prime"}:
        platform_candidates = ["prime", "amazon"]
    elif service in {"max", "hbomax", "hbo max"}:
        platform_candidates = ["max", "hbomax", "hbo max"]

    where_platform = " OR ".join([f"platform = :p{i}" for i in range(len(platform_candidates))])
    params = {"e": email}
    for i, p in enumerate(platform_candidates):
        params[f"p{i}"] = p

    with Session(engine) as s:
        found = s.execute(
            text(f"""SELECT id, platform, email, password_enc, notes, created_at
                    FROM streaming_accounts
                    WHERE ({where_platform}) AND email = :e
                    LIMIT 1"""),
            params,
        ).mappings().first()

    if not found:
        return render_template("index.html", lang=lang, t=t, mensagem=None, email=email, service=service)

    if dec(found["password_enc"]) != senha:
        return render_template("index.html", lang=lang, t=t,
                               mensagem=t["incorrect_password"], email=email, service=service)

    # ----- Filtros de assunto/remetente por serviço -----
    subject_filter = None
    subject_keywords = None
    from_filters = None
    forbidden_subject = None

    if service == "disney":
        subject_keywords = ["Your one-time passcode for Disney+", "Tu código de acceso único para Disney+"]

    elif service == "netflix":
        subject_filter = "Netflix: Your sign-in code"

    elif service in {"prime", "amazon", "amazon prime"}:
        subject_keywords = ["Verifi"]

    elif service == "crunchyroll":
        subject_keywords = ["Confirma tu nuevo inicio"]

    elif service in {"max", "hbomax", "hbo max"}:
        subject_keywords = ["Urgente: Tu código de un solo uso"]

    # Busca o e-mail com tratamento de erro para evitar 500
    try:
        email_html = fetch_login_code_email_html(
            service=service,
            target_email=email,
            lookback_days=7,
            max_scan=200,
            required_subject_substr=subject_filter,
            required_subject_keywords=subject_keywords,
            required_from_contains=from_filters,
            forbidden_subject_keywords=forbidden_subject,
        )
    except Exception as e:
        print("ERRO AO BUSCAR EMAIL:", repr(e))
        email_html = """
        <div style="color:#b00020">
          <strong>Não foi possível buscar o e-mail agora.</strong><br>
          Verifique as configurações do servidor de e-mail (IMAP) e tente novamente.
        </div>
        """
    # -----------------------------------------

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

# -----------------------------------------------------------------------------
# Rotas protegidas (admin)
# -----------------------------------------------------------------------------
@app.get("/accounts")
@admin_required
def accounts_page():
    lang = get_lang()

    # Filtros / paginação
    q = (request.args.get("q") or "").strip()
    try:
        per_page = int(request.args.get("per_page") or 20)
    except ValueError:
        per_page = 20
    per_page = max(5, min(per_page, 200))

    try:
        page = int(request.args.get("page") or 1)
    except ValueError:
        page = 1
    page = max(page, 1)

    where = ""
    params = {}
    if q:
        where = "WHERE lower(email) LIKE :q"
        params["q"] = f"%{q.lower()}%"

    with Session(engine) as s:
        total = s.execute(
            text(f"SELECT COUNT(1) AS c FROM streaming_accounts {where}"),
            params,
        ).mappings().first()["c"]

        total_pages = max(1, (int(total) + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        rows = s.execute(
            text(f"""
                SELECT id, platform, email, password_enc, notes, created_at
                FROM streaming_accounts
                {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {**params, "limit": per_page, "offset": offset},
        ).mappings().all()

    return render_template(
        "accounts.html",
        lang=lang,
        t=T[lang],
        accounts=rows,
        q=q,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )

@app.post("/accounts")
@admin_required
def accounts_create():
    platform = (request.form.get("platform") or "").strip().lower()
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    # Canonicaliza alguns aliases na inserção
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


@app.get("/accounts/<int:acc_id>/edit")
@admin_required
def accounts_edit_page(acc_id: int):
    """Página para editar uma conta (admin)."""
    lang = get_lang()
    next_url = request.args.get("next") or url_for("accounts_page")

    with Session(engine) as s:
        row = s.execute(
            text(
                """
                SELECT id, platform, email, notes, created_at
                FROM streaming_accounts
                WHERE id=:i
                """
            ),
            {"i": acc_id},
        ).mappings().first()

    if not row:
        flash("Conta não encontrada.", "error")
        return redirect(next_url)

    return render_template(
        "account_edit.html",
        lang=lang,
        t=T[lang],
        account=row,
        next_url=next_url,
    )


@app.post("/accounts/<int:acc_id>/edit")
@admin_required
def accounts_edit_save(acc_id: int):
    """Salva alterações de uma conta (admin)."""
    next_url = request.form.get("next") or url_for("accounts_page")

    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if not email:
        flash("Informe um e-mail válido.", "error")
        return redirect(url_for("accounts_edit_page", acc_id=acc_id, next=next_url))

    with Session(engine) as s:
        if password:
            s.execute(
                text(
                    """
                    UPDATE streaming_accounts
                    SET email=:e, notes=:n, password_enc=:pw
                    WHERE id=:i
                    """
                ),
                {"e": email, "n": notes, "pw": enc(password), "i": acc_id},
            )
        else:
            s.execute(
                text(
                    """
                    UPDATE streaming_accounts
                    SET email=:e, notes=:n
                    WHERE id=:i
                    """
                ),
                {"e": email, "n": notes, "i": acc_id},
            )
        s.commit()

    flash("Conta atualizada.", "success")
    return redirect(next_url)

# -----------------------------------------------------------------------------
# Run local
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
