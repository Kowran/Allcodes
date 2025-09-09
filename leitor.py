import os
import imaplib
import email
import re
from email.header import decode_header
from email.utils import getaddresses
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

# -----------------------------------------------------------------------------
# Configurações
# -----------------------------------------------------------------------------
EMAIL = os.environ.get("EMAIL")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_FOLDER = os.environ.get("IMAP_FOLDER", "INBOX")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))

# -----------------------------------------------------------------------------
# Utilitários
# -----------------------------------------------------------------------------
def _require_credentials():
    if not EMAIL or not APP_PASSWORD:
        raise RuntimeError("Credenciais ausentes: defina EMAIL e APP_PASSWORD.")

def _decode_maybe(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return value.decode(errors="replace")
    parts = decode_header(value)
    decoded = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                decoded.append(text.decode(enc or "utf-8", errors="replace"))
            except Exception:
                decoded.append(text.decode("utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)

def _dd_mon_yyyy(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y")

def _get_msg_addresses(msg: email.message.Message) -> set:
    fields = []
    for hdr in ("To", "Cc", "Bcc", "Delivered-To", "X-Original-To", "X-Forwarded-To"):
        vals = msg.get_all(hdr, [])
        if not isinstance(vals, list):
            vals = [vals]
        fields.extend(vals)
    addrs = {addr.lower() for _, addr in getaddresses(fields) if addr}
    return addrs

def _get_parts(msg: email.message.Message) -> Tuple[Optional[str], Optional[str]]:
    if msg.is_multipart():
        html_body = None
        text_body = None
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            if ctype == "text/html" and html_body is None:
                try:
                    html_body = payload.decode(charset, errors="replace")
                except Exception:
                    pass
            elif ctype == "text/plain" and text_body is None:
                try:
                    text_body = payload.decode(charset, errors="replace")
                except Exception:
                    pass
        return html_body, text_body
    else:
        ctype = msg.get_content_type()
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        if ctype == "text/html":
            return payload.decode(charset, errors="replace"), None
        elif ctype == "text/plain":
            return None, payload.decode(charset, errors="replace")
        return None, None

def _highlight_code_in_html(html: str, codes: List[str]) -> str:
    out = html
    for c in codes:
        pat = re.escape(c)
        out = re.sub(pat, f"<mark>{c}</mark>", out, flags=re.IGNORECASE)
    return out

def _extract_codes(text: str) -> List[str]:
    if not text:
        return []
    context = r"(codigo|c[oó]digo|verification|verify|one[-\s]?time|OTP|security|login|signin|verifica[cç][aã]o|access)"
    code_re = re.compile(rf"{context}[^0-9]{{0,20}}(\d{{4,8}})", re.IGNORECASE)
    codes = [m.group(1) for m in code_re.finditer(text)]
    if not codes:
        fallback = re.findall(r"\b(\d{6})\b", text)
        codes = fallback[:3]
    seen = set(); ordered = []
    for c in codes:
        if c not in seen:
            seen.add(c); ordered.append(c)
    return ordered

_SERVICE_HINTS = {
    "disney": {"subjects": ["Disney", "Disney+"], "from_contains": ["disney", "disneyplus"]},
    "netflix": {"subjects": ["Netflix"], "from_contains": ["netflix"]},
    "prime": {"subjects": ["Prime", "Amazon", "Prime Video"], "from_contains": ["amazon", "primevideo", "prime.video"]},
}

def _match_service(msg: email.message.Message, service: str) -> bool:
    svc = _SERVICE_HINTS.get(service, {})
    subj = _decode_maybe(msg.get("Subject", ""))
    frm = _decode_maybe(msg.get("From", "")).lower()
    ok_subj = any(word.lower() in subj.lower() for word in svc.get("subjects", []))
    ok_from = any(word in frm for word in svc.get("from_contains", []))
    return ok_subj or ok_from

# -----------------------------------------------------------------------------
# Busca e-mail do código apenas se contiver o target_email
# com filtro opcional de assunto obrigatório (required_subject_substr)
# -----------------------------------------------------------------------------
def fetch_login_code_email_html(
    service: str,
    target_email: str,
    lookback_days: int = 7,
    max_scan: int = 200,
    required_subject_substr: str | None = None,  # << permite filtrar o Subject
) -> Optional[str]:
    _require_credentials()
    if not target_email:
        return None

    target_email_low = target_email.lower()

    imap = imaplib.IMAP4_SSL(host=IMAP_HOST, port=IMAP_PORT)
    try:
        imap.login(EMAIL, APP_PASSWORD)
        imap.select(IMAP_FOLDER, readonly=True)

        since = _dd_mon_yyyy(datetime.utcnow() - timedelta(days=lookback_days))
        status, data = imap.search(None, "SINCE", since)
        if status != "OK":
            return None

        ids = data[0].split()
        if not ids:
            return None

        ids = ids[-max_scan:][::-1]

        for mid in ids:
            st, msg_data = imap.fetch(mid, "(RFC822)")
            if st != "OK":
                continue
            raw = None
            for part in msg_data:
                if isinstance(part, tuple):
                    raw = part[1]
                    break
            if not raw:
                continue

            msg = email.message_from_bytes(raw)

            # (1) precisa bater com o serviço
            if not _match_service(msg, service):
                continue

            # (2) se houver um assunto obrigatório, precisa conter
            if required_subject_substr:
                subj = _decode_maybe(msg.get("Subject", "")).strip()
                if required_subject_substr.lower() not in subj.lower():
                    continue

            # (3) precisa conter o target_email em destinatários OU no corpo
            addrs = _get_msg_addresses(msg)
            html, text = _get_parts(msg)
            body_text = ((html or "") + "\n" + (text or "")).lower()

            has_in_recipients = (target_email_low in addrs) if addrs else False
            has_in_body = (target_email_low in body_text) if body_text else False
            if not (has_in_recipients or has_in_body):
                continue

            # (4) extrai/realça códigos e retorna HTML
            codes = _extract_codes((html or "") + "\n" + (text or ""))

            if html:
                return _highlight_code_in_html(html, codes) if codes else html

            if text:
                safe = _decode_maybe(text)
                safe = re.sub(r"\r?\n", "<br>", safe)
                if codes:
                    for c in codes:
                        safe = re.sub(re.escape(c), f"<mark>{c}</mark>", safe, flags=re.IGNORECASE)
                return f"<div style='white-space:normal; font-family:inherit'>{safe}</div>"

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
