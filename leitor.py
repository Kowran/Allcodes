import imaplib
import email
import unicodedata
from email.header import decode_header, make_header
from email.message import Message
from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable
from dotenv import load_dotenv
import os

load_dotenv()

IMAP_HOST = os.environ.get("EMAIL_HOST", "")
IMAP_PORT = int(os.environ.get("EMAIL_PORT", "993"))
IMAP_USER = os.environ.get("EMAIL_USERNAME", "")
IMAP_PASS = os.environ.get("EMAIL_PASSWORD", "")
IMAP_FOLDER = os.environ.get("EMAIL_FOLDER", "INBOX")


def _normalize_text(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()


def _decode_subject(msg: Message) -> str:
    raw = msg.get("Subject", "") or ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _message_date(msg: Message) -> datetime:
    """Converte 'Date' do cabeçalho para datetime (UTC) com fallback."""
    raw = msg.get("Date")
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(tz=timezone.utc)


def _html_or_text(msg: Message) -> str:
    """Extrai primeiro HTML disponível; senão, devolve texto simples em <pre>."""
    # multipart: percorre as partes
    if msg.is_multipart():
        for part in msg.walk():
            ct = (part.get_content_type() or "").lower()
            cd = (part.get("Content-Disposition") or "").lower()
            if ct == "text/html" and "attachment" not in cd:
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        for part in msg.walk():
            ct = (part.get_content_type() or "").lower()
            cd = (part.get("Content-Disposition") or "").lower()
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    return f"<pre>{email.utils.escape(text)}</pre>"
                except Exception:
                    continue
    else:
        ct = (msg.get_content_type() or "").lower()
        try:
            body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            body = msg.get_payload()
        if ct == "text/html":
            return body if isinstance(body, str) else str(body)
        return f"<pre>{email.utils.escape(body if isinstance(body, str) else str(body))}</pre>"

    # fallback
    return "<em>(sem conteúdo visualizável)</em>"


def _imap_search_since(imap: imaplib.IMAP4_SSL, since: datetime) -> list[bytes]:
    # IMAP requer data no formato DD-Mon-YYYY (UTC não importa para o filtro “SINCE”)
    date_str = since.strftime("%d-%b-%Y")
    typ, data = imap.search(None, "SINCE", date_str)
    if typ != "OK":
        return []
    return data[0].split()


def _connect_select(folder: str) -> imaplib.IMAP4_SSL:
    if not (IMAP_HOST and IMAP_USER and IMAP_PASS):
        raise RuntimeError("Configuração IMAP ausente (EMAIL_HOST/EMAIL_USERNAME/EMAIL_PASSWORD).")
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(IMAP_USER, IMAP_PASS)
    imap.select(folder)
    return imap


def fetch_login_code_email_html(
    service: str,
    target_email: str,
    lookback_days: int = 7,
    max_scan: int = 200,
    required_subject_substr: Optional[str] = None,
    required_subject_keywords: Optional[list[str]] = None,  # NOVO: lista de palavras
) -> Optional[str]:
    """
    Percorre as mensagens recentes no IMAP e retorna o HTML do primeiro e-mail que
    bater nos critérios (serviço/e-mail alvo) e filtros de assunto.

    - service: "disney" | "netflix" | "prime"/"amazon"/"amazon prime" | ...
    - target_email: e-mail do usuário que está tentando logar
    - lookback_days: janela de busca
    - max_scan: máximo de mensagens a examinar (mais recentes primeiro)
    - required_subject_substr: substring única (compatibilidade legada)
    - required_subject_keywords: lista de palavras aceitas no assunto (match parcial)
    """
    service = (service or "").strip().lower()
    target_email_norm = _normalize_text(target_email)

    # Normaliza palavras-chave (se houver)
    kw_norm: Optional[list[str]] = None
    if required_subject_keywords:
        kw_norm = [_normalize_text(k) for k in required_subject_keywords if k]

    since = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)

    imap = _connect_select(IMAP_FOLDER)
    try:
        ids = _imap_search_since(imap, since)
        if not ids:
            return None

        # varre do mais recente para o mais antigo
        ids = ids[-max_scan:][::-1]

        for msg_id in ids:
            typ, data = imap.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not data or not isinstance(data[0], tuple):
                continue

            msg: Message = email.message_from_bytes(data[0][1])
            subject = _decode_subject(msg)
            subject_norm = _normalize_text(subject)

            # Filtro por assunto (palavras-chave > substr única)
            if kw_norm:
                if not any(k in subject_norm for k in kw_norm):
                    continue
            elif required_subject_substr:
                if _normalize_text(required_subject_substr) not in subject_norm:
                    continue

            # (Opcional) Filtro simples por destinatário "To" contendo target_email
            # — útil para caixas compartilhadas. Mantém frouxo para não descartar válidos.
            to_hdr = (msg.get("To", "") or "") + " " + (msg.get("Delivered-To", "") or "")
            if target_email and _normalize_text(to_hdr).find(target_email_norm) == -1:
                # não descarta automaticamente; às vezes o serviço envia para alias/lista
                pass

            # Dentro de janela de tempo?
            if _message_date(msg) < since:
                continue

            # Se passou, retorna HTML (ou texto como <pre>)
            html = _html_or_text(msg)

            # Envelopo simples com assunto e data (visualmente útil no front)
            dt_str = _message_date(msg).strftime("%d/%m/%Y %H:%M UTC")
            return f"""
            <div>
                <p><strong>Assunto:</strong> {subject}</p>
                <p><strong>Data:</strong> {dt_str}</p>
                <div style="margin-top:10px;border-top:1px solid #ddd;padding-top:10px">
                    {html}
                </div>
            </div>
            """

        return None
    finally:
        try:
            imap.close()
        except Exception:
            pass
        try:
            imap.logout()
        except Exception:
            pass
