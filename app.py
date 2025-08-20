from flask import Flask, render_template, request, redirect, url_for, session
from leitor import buscar_email_disney, buscar_email_netflix, buscar_email_prime

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_123'

# Pré-definindo e-mails e senhas associadas
email_senhas = {
    "henriquestore743@gmail.com": "senha123",
    "erass_manxga@telusservice.com": "123"
}

# Traduções para os idiomas
TRANSLATIONS = {
    'pt': {
        'store_name': 'Henrique Store',
        'instagram': 'Instagram',
        'whatsapp': 'WhatsApp',
        'ggmax': 'Nossa Loja',
        'title': 'Buscar e-mail',
        'placeholder': 'Digite o e-mail da conta',
        'button': 'Buscar',
        'password_placeholder': 'Digite a senha',
        'result': 'Última mensagem encontrada:',
        'not_found': 'Nenhuma mensagem encontrada para',
        'incorrect_password': 'Senha incorreta! Tente novamente.',
        'language_label': '🌐 Idioma:',
        'service_label': 'Escolha o serviço:',
        'footer_text': '© 2025 Henrique Store – Todos os direitos reservados.',
        'whatsapp_icon': '💬 Suporte',
        'help_text': 'Se precisar de ajuda, entre em contato conosco!',
        'click_here': 'Clique aqui',
        'searching': 'Procurando...',
    },
    'en': {
        'store_name': 'Henrique Store',
        'instagram': 'Instagram',
        'whatsapp': 'WhatsApp',
        'ggmax': 'Our Store',
        'title': 'Find Email',
        'placeholder': 'Enter account email',
        'button': 'Search',
        'password_placeholder': 'Enter password',
        'result': 'Last message found:',
        'not_found': 'No message found for',
        'incorrect_password': 'Incorrect password! Please try again.',
        'language_label': '🌐 Language:',
        'service_label': 'Choose the service:',
        'footer_text': '© 2025 Henrique Store – All rights reserved.',
        'whatsapp_icon': '💬 Support',
        'help_text': 'If you need help, contact us!',
        'click_here': 'Click here',
        'searching': 'Searching...',
    },
    'es': {
        'store_name': 'Henrique Store',
        'instagram': 'Instagram',
        'whatsapp': 'WhatsApp',
        'ggmax': 'Nuestra Tienda',
        'title': 'Buscar correo electrónico',
        'placeholder': 'Introduzca el correo electrónico de la cuenta',
        'button': 'Buscar',
        'password_placeholder': 'Introduzca la contraseña',
        'result': 'Último mensaje encontrado:',
        'not_found': 'No se encontró ningún mensaje para',
        'incorrect_password': '¡Contraseña incorrecta! Inténtalo de nuevo.',
        'language_label': '🌐 Idioma:',
        'service_label': 'Elija el servicio:',
        'footer_text': '© 2025 Henrique Store – Todos los derechos reservados.',
        'whatsapp_icon': '💬 Soporte',
        'help_text': 'Si necesitas ayuda, contáctanos!',
        'click_here': 'Haz clic aquí',
        'searching': 'Buscando...',
    },
    'fr': {
        'store_name': 'Henrique Store',
        'instagram': 'Instagram',
        'whatsapp': 'WhatsApp',
        'ggmax': 'Notre Boutique',
        'title': 'Trouver un e-mail',
        'placeholder': 'Entrez l\'email du compte',
        'button': 'Rechercher',
        'password_placeholder': 'Entrez le mot de passe',
        'result': 'Dernier message trouvé:',
        'not_found': 'Aucun message trouvé pour',
        'incorrect_password': 'Mot de passe incorrect! Veuillez réessayer.',
        'language_label': '🌐 Langue:',
        'service_label': 'Choisir le service:',
        'footer_text': '© 2025 Henrique Store – Tous droits réservés.',
        'whatsapp_icon': '💬 Support',
        'help_text': 'Si vous avez besoin d\'aide, contactez-nous!',
        'click_here': 'Cliquez ici',
        'searching': 'Recherche...',
    },
    'de': {
        'store_name': 'Henrique Store',
        'instagram': 'Instagram',
        'whatsapp': 'WhatsApp',
        'ggmax': 'Unser Geschäft',
        'title': 'E-Mail finden',
        'placeholder': 'Geben Sie die E-Mail des Kontos ein',
        'button': 'Suchen',
        'password_placeholder': 'Passwort eingeben',
        'result': 'Letzte Nachricht gefunden:',
        'not_found': 'Keine Nachricht gefunden für',
        'incorrect_password': 'Falsches Passwort! Bitte versuche es erneut.',
        'language_label': '🌐 Sprache:',
        'service_label': 'Wählen Sie den Service:',
        'footer_text': '© 2025 Henrique Store – Alle Rechte vorbehalten.',
        'whatsapp_icon': '💬 Unterstützung',
        'help_text': 'Wenn Sie Hilfe benötigen, kontaktieren Sie uns!',
        'click_here': 'Klicken Sie hier',
        'searching': 'Suche...',
    }
}


@app.route('/', methods=['GET', 'POST'])
def index():
    email = ''
    senha = ''
    mensagem = None
    service = None
    lang = session.get('lang', 'pt')
    t = TRANSLATIONS.get(lang, TRANSLATIONS['pt'])

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        service = request.form.get('service')

        if email in email_senhas and email_senhas[email] == senha:
            if service == 'disney':
                mensagem, service = buscar_email_disney(email)
            elif service == 'netflix':
                mensagem, service = buscar_email_netflix(email)
            elif service == 'prime':
                mensagem, service = buscar_email_prime(email)
        else:
            mensagem = t['incorrect_password']  # Mensagem de erro com a tradução correta

    return render_template("index.html", t=t, email=email, mensagem=mensagem, lang=lang, service=service)

@app.route('/set_lang/<lang>')
def set_language(lang):
    if lang in TRANSLATIONS:
        session['lang'] = lang
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
