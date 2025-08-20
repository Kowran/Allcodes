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

def limpar_email_conteudo(body):
    # Regex para remover a parte do rodapé e informações indesejadas
    padrao = r"(MyDisney.*?© 2025 Disney and its related entities.*?SRC:.*?$)"
    body = re.sub(padrao, '', body, flags=re.DOTALL)
    return body

def buscar_email_disney(email_referencia=None):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL, APP_PASSWORD)
        mail.select("inbox")
        status, data = mail.search(None, '(FROM "disney+")')  # Buscar e-mails da Disney+
        email_ids = data[0].split()

        for eid in reversed(email_ids[-1:]):  # Buscar apenas o último e-mail
            status, msg_data = mail.fetch(eid, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body = decode_mensagem(part.get_payload(decode=True))
                        break
            else:
                if msg.get_content_type() == "text/html":
                    body = decode_mensagem(msg.get_payload(decode=True))

            body = limpar_email_conteudo(body)

            if email_referencia and email_referencia.lower() not in body.lower():
                continue

            return body, "Disney+"  # Marca como Disney+

        return "Nenhum e-mail encontrado.", "Disney+"
    except Exception as e:
        return f"Erro ao buscar e-mails: {e}", "Disney+"

def buscar_email_netflix(email_referencia=None):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL, APP_PASSWORD)
        mail.select("inbox")

        # Alterado para procurar pelo título (assunto) contendo exatamente "Netflix: Your sign-in code"
        status, data = mail.search(None, '(SUBJECT "Netflix: Your sign-in code")')  # Buscar e-mails com o título exato
        email_ids = data[0].split()

        if not email_ids:
            return "Nenhum e-mail encontrado.", "Netflix"  # Caso não haja e-mails

        for eid in reversed(email_ids[-1:]):  # Buscar apenas o último e-mail
            status, msg_data = mail.fetch(eid, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body = decode_mensagem(part.get_payload(decode=True))
                        break
            else:
                if msg.get_content_type() == "text/html":
                    body = decode_mensagem(msg.get_payload(decode=True))

            body = limpar_email_conteudo(body)

            if email_referencia and email_referencia.lower() not in body.lower():
                continue

            return body, "Netflix"  # Marca como Netflix

        return "Nenhum e-mail encontrado.", "Netflix"
    except Exception as e:
        return f"Erro ao buscar e-mails: {e}", "Netflix"


def buscar_email_prime(email_referencia=None):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL, APP_PASSWORD)
        mail.select("inbox")
        status, data = mail.search(None, '(FROM "amazon")')  # Buscar e-mails do Prime Video
        email_ids = data[0].split()

        for eid in reversed(email_ids[-1:]):  # Buscar apenas o último e-mail
            status, msg_data = mail.fetch(eid, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body = decode_mensagem(part.get_payload(decode=True))
                        break
            else:
                if msg.get_content_type() == "text/html":
                    body = decode_mensagem(msg.get_payload(decode=True))

            body = limpar_email_conteudo(body)

            if email_referencia and email_referencia.lower() not in body.lower():
                continue

            return body, "Prime Video"  # Marca como Prime Video

        return "Nenhum e-mail encontrado.", "Prime Video"
    except Exception as e:
        return f"Erro ao buscar e-mails: {e}", "Prime Video"
