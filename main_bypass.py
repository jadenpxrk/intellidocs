import os
import hmac
import hashlib
import json
from urllib.parse import parse_qs, unquote
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="IntelliDocs Test", version="1.0.0")


@app.get("/")
async def root():
    return {"message": "IntelliDocs GitHub App is running (TEST MODE)"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    print(f"📨 Webhook received!")
    print(f"📝 Signature: {signature}")

    if not signature:
        print("❌ Missing signature")
        raise HTTPException(status_code=400, detail="Missing signature")

    webhook_secret = os.getenv("WEBHOOK_SECRET")
    if not webhook_secret:
        print("❌ Webhook secret not configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected_signature = (
        "sha256="
        + hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(signature, expected_signature):
        print("❌ Invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    print("✅ Signature verified!")

    print(f"📦 Payload length: {len(payload)}")
    if len(payload) == 0:
        print("❌ Empty payload received")
        raise HTTPException(status_code=400, detail="Empty payload")

    try:
        # GitHub sends webhook data as form-encoded payload
        payload_str = payload.decode("utf-8")

        if payload_str.startswith("payload="):
            # Extract and URL-decode the JSON payload
            json_payload = unquote(payload_str[8:])  # Remove 'payload=' prefix
            event_data = json.loads(json_payload)
            print("📋 Parsed form-encoded webhook payload")
        else:
            # Try direct JSON parsing (for other webhook formats)
            event_data = json.loads(payload_str)
            print("📋 Parsed direct JSON payload")

    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        print(f"📄 Raw payload preview: {payload[:200]}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        print(f"❌ Payload parsing error: {e}")
        print(f"📄 Raw payload preview: {payload[:200]}")
        raise HTTPException(status_code=400, detail="Failed to parse payload")

    event_type = request.headers.get("X-GitHub-Event")

    print(f"📋 Event type: {event_type}")

    if event_type == "push":
        print("🚀 Processing push event...")
        background_tasks.add_task(handle_push_test, event_data)
        return {"message": "Push event received and processing in background"}

    return {"message": "Event ignored (not a push event)"}


async def handle_push_test(event_data):
    """Test version of push handler that just logs what would happen"""
    try:
        repo_full_name = event_data["repository"]["full_name"]
        before_sha = event_data["before"]
        after_sha = event_data["after"]
        ref = event_data["ref"]

        print(f"📦 Repository: {repo_full_name}")
        print(f"🔄 Reference: {ref}")
        print(f"📍 Before SHA: {before_sha[:7]}")
        print(f"📍 After SHA: {after_sha[:7]}")

        if ref != "refs/heads/main" and ref != "refs/heads/master":
            print("⏭️  Skipping - not main/master branch")
            return

        # Simulate file change detection
        if "commits" in event_data:
            print(f"📝 Commits in push: {len(event_data['commits'])}")
            for commit in event_data["commits"]:
                print(f"  • {commit['message']}")
                if "added" in commit:
                    print(f"    Added: {commit['added']}")
                if "modified" in commit:
                    print(f"    Modified: {commit['modified']}")
                if "removed" in commit:
                    print(f"    Removed: {commit['removed']}")

        print("🎯 In real mode, this would:")
        print("  1. Get file contents from GitHub API")
        print("  2. Generate documentation with AI")
        print("  3. Push to separate docs repository")
        print("  4. Set commit status to success")
        print("✅ Test processing complete!")

    except Exception as e:
        print(f"❌ Error in test handler: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
