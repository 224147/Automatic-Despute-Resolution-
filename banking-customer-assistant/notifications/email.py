import os

def preview_email(subject: str, body: str):
    return {"to": os.getenv("DEMO_EMAIL", "demo@test.com"), "subject": subject, "body": body}

def send_email(message):
    return {"status": "FAILED" if os.getenv("DEMO_EMAIL_FAILURE", "false") == "true" else "QUEUED", "preview": message}
