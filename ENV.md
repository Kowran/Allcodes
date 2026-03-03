# Configuração de ambiente (Railway / Local)

Para que o **painel de Contas (Admin)** leia e grave no Postgres do Railway, defina a variável `DATABASE_URL`.

## Local
1. Copie `.env.example` para `.env`
2. Ajuste `SECRET_KEY`, `FERNET_KEY` e `ADMIN_PASSWORD`
3. Rode:
   - `pip install -r requirements.txt`
   - `python app.py`

## Railway
No Railway, vá em **Variables** e configure:
- `DATABASE_URL` (a URL do Postgres)
- `SECRET_KEY`
- `FERNET_KEY` (fixa, para não perder a capacidade de descriptografar senhas)
- `ADMIN_USER` / `ADMIN_PASSWORD` (ou `ADMIN_PASSWORD_HASH`)

> Importante: se você trocar `FERNET_KEY`, as senhas antigas não poderão ser descriptografadas.
