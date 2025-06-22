import os
import hmac
import hashlib
import json
from urllib.parse import unquote
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv

from src.auth import GitHubAuth
from src.webhook import handle_push_event
from src.git_operations import GitOperations
from src.docs_generator import DocsGenerator

load_dotenv()

app = FastAPI(title="IntelliDocs GitHub App", version="1.0.0")


@app.get("/")
async def root():
    return {"message": "IntelliDocs GitHub App is running", "status": "ready"}


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


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
        background_tasks.add_task(process_push_event, event_data)
        return {"message": "Push event received and processing in background"}

    return {"message": f"Event '{event_type}' received but ignored (not a push event)"}


async def process_push_event(event_data):
    """Process push events with real GitHub API calls and documentation generation"""
    try:
        repo_full_name = event_data["repository"]["full_name"]
        before_sha = event_data["before"]
        after_sha = event_data["after"]
        ref = event_data["ref"]
        repository = event_data["repository"]

        print(f"📦 Repository: {repo_full_name}")
        print(f"🔄 Reference: {ref}")
        print(f"📍 Before SHA: {before_sha[:7]}")
        print(f"📍 After SHA: {after_sha[:7]}")

        # Only process main/master branch
        if ref not in ["refs/heads/main", "refs/heads/master"]:
            print("⏭️  Skipping - not main/master branch")
            return

        # Initialize GitHub authentication
        try:
            github_auth = GitHubAuth()
            github_client = github_auth.get_installation_client(
                repository["owner"]["login"]
            )
            print("✅ GitHub authentication successful")
        except Exception as e:
            print(f"❌ GitHub authentication failed: {e}")
            return

        # Get the repository object
        try:
            repo = github_client.get_repo(repo_full_name)
            print(f"✅ Connected to repository: {repo_full_name}")
        except Exception as e:
            print(f"❌ Failed to get repository: {e}")
            return

        # Get changed files from the push
        changed_files = []
        if "commits" in event_data:
            print(f"📝 Processing {len(event_data['commits'])} commits")
            for commit in event_data["commits"]:
                print(f"  • {commit['message']}")
                if "added" in commit:
                    changed_files.extend(commit["added"])
                if "modified" in commit:
                    changed_files.extend(commit["modified"])

        # Remove duplicates and filter for code files
        changed_files = list(set(changed_files))
        code_extensions = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".cpp",
            ".c",
            ".go",
            ".rs",
            ".php",
            ".rb",
            ".swift",
            ".kt",
            ".scala",
            ".html",
            ".css",
            ".scss",
            ".less",
            ".sql",
            ".sh",
            ".bash",
            ".yaml",
            ".yml",
            ".json",
        }

        code_files = [
            f for f in changed_files if any(f.endswith(ext) for ext in code_extensions)
        ]

        if not code_files:
            print("📝 No code files to document")
            return

        print(f"📄 Code files to document: {len(code_files)}")
        for file in code_files[:10]:  # Show first 10
            print(f"  • {file}")

        # Initialize documentation generator
        docs_generator = DocsGenerator()

        # Initialize git operations for docs repository
        docs_repo_owner = os.getenv("DOCS_REPO_OWNER", repository["owner"]["login"])
        docs_repo_name = os.getenv("DOCS_REPO_NAME", f"{repository['name']}-docs")

        try:
            git_ops = GitOperations(github_client, docs_repo_owner, docs_repo_name)
            print(f"✅ Initialized docs repository: {docs_repo_owner}/{docs_repo_name}")
        except Exception as e:
            print(f"❌ Failed to initialize docs repository: {e}")
            return

        # Process each file and generate documentation
        docs_created = 0
        for file_path in code_files:
            try:
                print(f"📖 Processing: {file_path}")

                # Get file content from GitHub
                file_content = repo.get_contents(file_path, ref=after_sha)
                if file_content.size > 1000000:  # Skip files > 1MB
                    print(
                        f"⏭️  Skipping {file_path} - too large ({file_content.size} bytes)"
                    )
                    continue

                content = file_content.decoded_content.decode("utf-8")

                # Generate documentation
                print(f"🤖 Generating AI documentation for {file_path}")
                documentation = docs_generator.summarise_file(file_path, content)

                # Create docs file path
                docs_file_path = f"docs/{file_path}.md"

                # Save documentation to docs repository
                git_ops.create_or_update_file(
                    docs_file_path,
                    documentation,
                    f"Update documentation for {file_path}",
                    after_sha,
                )

                docs_created += 1
                print(f"✅ Created documentation: {docs_file_path}")

            except Exception as e:
                print(f"❌ Failed to process {file_path}: {e}")
                continue

        if docs_created > 0:
            print(f"🎉 Successfully created {docs_created} documentation files!")

            # Set commit status to success
            try:
                repo.create_status(
                    after_sha,
                    state="success",
                    description=f"Generated docs for {docs_created} files",
                    context="intellidocs/documentation",
                )
                print("✅ Set commit status to success")
            except Exception as e:
                print(f"⚠️  Failed to set commit status: {e}")
        else:
            print("❌ No documentation files were created")

    except Exception as e:
        print(f"❌ Error in push event processing: {e}")

        # Try to set commit status to failure
        try:
            if "repo" in locals() and "after_sha" in locals():
                repo.create_status(
                    after_sha,
                    state="failure",
                    description="Failed to generate documentation",
                    context="intellidocs/documentation",
                )
        except:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
