import os
import hmac
import hashlib
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from src.webhook import WebhookHandler
from src.auth import GitHubAppAuth

load_dotenv()

app = FastAPI(title="IntelliDocs", version="1.0.0")
webhook_handler = WebhookHandler()


@app.get("/")
async def root():
    return {"message": "IntelliDocs GitHub App is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    webhook_secret = os.getenv("WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected_signature = (
        "sha256="
        + hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    import json

    event_data = json.loads(payload.decode())
    event_type = request.headers.get("X-GitHub-Event")

    if event_type == "push":
        background_tasks.add_task(webhook_handler.handle_push, event_data)
        return {"message": "Push event received"}

    return {"message": "Event ignored"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
