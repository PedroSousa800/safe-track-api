# app/services/email_service.py

import os
import requests
import logging

logger = logging.getLogger(__name__)

def send_pin_recovery_email(recipient: str, pin: str):
    """
    Sends a PIN recovery email using the SendGrid API (v3/mail/send) via requests.
    """
    # 1. Obter a chave API (Certifique-se que o nome da variável no .env é SENDGRID_API_KEY)
    api_key = os.environ.get('SENDGRID_API_KEY')
    
    # 2. ENDEREÇO DO REMETENTE ÚNICO VERIFICADO NO SENDGRID
    # Substitua pelo seu e-mail do Gmail que verificou no SendGrid
    sender_email = "safe.track.lince@gmail.com"
    
    # 3. URL DA API DO SENDGRID
    api_url = "https://api.sendgrid.com/v3/mail/send"

    headers = {
        "Content-Type": "application/json",
        # O SendGrid usa o formato "Bearer" no Authorization, como o MailerSend
        "Authorization": f"Bearer {api_key}" 
    }
    
    # 4. PAYLOAD NO FORMATO ESPERADO PELO SENDGRID (um pouco diferente do MailerSend)
    payload = {
        # O SendGrid usa 'personalizations' para definir destinatários e 'content' para o corpo
        "personalizations": [
            {
                "to": [
                    {
                        "email": recipient
                    }
                ],
                "subject": "PIN Recovery - SafeTrack"
            }
        ],
        "from": {
            "email": sender_email,
            "name": "SafeTrack Support"
        },
        "content": [
            # Conteúdo em texto plano (necessário)
            {
                "type": "text/plain",
                "value": f'Olá, o seu código de recuperação de PIN é: {pin}.'
            },
            # Conteúdo em HTML (opcional, mas recomendado)
            {
                "type": "text/html",
                "value": f'Olá,<br><br>O seu código de recuperação de PIN é: <strong>{pin}</strong><br><br>Por favor, use este código para redefinir o seu PIN.'
            }
        ]
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        
        # O SendGrid retorna 202 Accepted em caso de sucesso, não 200 OK
        # response.raise_for_status() irá lançar uma exceção para códigos 4xx ou 5xx
        response.raise_for_status()

        # O SendGrid não retorna um corpo para 202, apenas o status de aceitação.
        logger.info(f"Email successfully queued by SendGrid. Status code: {response.status_code}")
        return True
    
    except requests.exceptions.HTTPError as e:
        # Se for um erro 4xx ou 5xx
        try:
            error_details = e.response.json()
        except requests.exceptions.JSONDecodeError:
            error_details = e.response.text # Em caso de corpo vazio ou não-JSON
            
        logger.error(f"SendGrid API Error (Status {e.response.status_code}): {error_details}")
        return False
    
    except Exception as e:
        logger.error(f"An unexpected error occurred during API call: {e}")
        return False