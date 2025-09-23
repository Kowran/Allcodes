# netlify/functions/app_handler.py
import os
# Garante que o Python veja os módulos da raiz (app.py, leitor.py, templates/static ao serem copiados)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in os.sys.path:
    os.sys.path.insert(0, ROOT)

from serverless_wsgi import handle_request
from app import app  # importa seu Flask app existente

def handler(event, context):
    # Delega a execução do Flask para a Lambda via serverless-wsgi
    return handle_request(app, event, context)
