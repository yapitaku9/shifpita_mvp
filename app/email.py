from threading import Thread
from flask import current_app, render_template
from flask_mail import Message
from app import mail

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Failed to send email: {e}")

def send_email(subject, recipients, template, **kwargs):
    """
    メールを非同期で送信する共通関数。

    Args:
        subject (str): メールの件名
        recipients (list): 受信者のメールアドレスリスト
        template (str): templates/email/ ディレクトリ以下のテンプレートファイル名 (拡張子なし)
        **kwargs: テンプレートに渡す変数
    """
    app = current_app._get_current_object()
    sender = app.config['MAIL_USERNAME'] or 'no-reply@example.com'
    
    msg = Message(subject, sender=sender, recipients=recipients)
    
    # メール本文をHTMLテンプレートから生成
    msg.html = render_template(f'email/{template}.html', **kwargs)
    
    # テキスト版もテンプレートから生成（オプション）
    # msg.body = render_template(f'email/{template}.txt', **kwargs)

    # 環境変数にMAIL_SERVERが設定されていない場合は、メールを送信しない（開発用）
    if not app.config.get('MAIL_SERVER'):
        app.logger.info("MAIL_SERVER is not set. Email sending is suppressed.")
        app.logger.info(f"Subject: {subject}")
        app.logger.info(f"Recipients: {recipients}")
        app.logger.info(f"HTML Body:\n{msg.html}")
        return

    Thread(target=send_async_email, args=(app, msg)).start()