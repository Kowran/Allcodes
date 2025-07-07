import imaplib
import email
import re
from email.header import decode_header

# ✅ Substitua pelos seus dados reais
EMAIL = "henriquestore744@gmail.com"
APP_PASSWORD = "muvm dnyn tbpu woxz"

def decode_mensagem(msg_bytes):
    try:
        return msg_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return msg_bytes.decode("latin1", errors="replace")

def buscar_codigo(email_referencia=None):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL, APP_PASSWORD)
        mail.select("inbox")
        status, data = mail.search(None, '(FROM "netflix")')
        email_ids = data[0].split()

        for eid in reversed(email_ids[-50:]):
            status, msg_data = mail.fetch(eid, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = decode_mensagem(part.get_payload(decode=True))
                        break
            else:
                body = decode_mensagem(msg.get_payload(decode=True))

            # 🔍 Filtra pelo e-mail do cliente no corpo da mensagem
            if email_referencia and email_referencia.lower() not in body.lower():
                continue

            # 🔐 Extrai o código de 4 dígitos
            codigo = re.search(r"\b\d{4}\b", body)
            if codigo:
                return codigo.group()

        return None
    except Exception as e:
        return None
