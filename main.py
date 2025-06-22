import os
import hmac
import hashlib
import json
from urllib.parse import unquote
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv

from src.auth import GitHubAppAuth
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


async def get_all_code_files(repo, ref, code_extensions):
    """Get all code files from the repository"""
    code_files = []

    def traverse_contents(contents):
        for content in contents:
            if content.type == "file":
                if any(content.name.endswith(ext) for ext in code_extensions):
                    code_files.append(content.path)
            elif content.type == "dir":
                # Recursively traverse directories
                try:
                    sub_contents = repo.get_contents(content.path, ref=ref)
                    traverse_contents(sub_contents)
                except Exception as e:
                    print(f"⚠️  Skipping directory {content.path}: {e}")

    try:
        root_contents = repo.get_contents("", ref=ref)
        traverse_contents(root_contents)
    except Exception as e:
        print(f"❌ Error getting repository contents: {e}")

    return code_files


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
            # Try to get installation ID from webhook payload first
            installation_id = None
            if "installation" in event_data and "id" in event_data["installation"]:
                installation_id = event_data["installation"]["id"]
                print(f"🔍 Found installation ID in payload: {installation_id}")
            else:
                # Fallback to environment variable
                installation_id = os.getenv("GITHUB_INSTALLATION_ID")
                if installation_id:
                    print(
                        f"🔍 Using installation ID from environment: {installation_id}"
                    )
                else:
                    print(
                        "❌ No installation ID found in webhook payload or environment"
                    )
                    print(f"🔍 Available webhook keys: {list(event_data.keys())}")
                    return

            github_auth = GitHubAppAuth()
            github_client = github_auth.get_installation_client(int(installation_id))
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

        # Check if docs branch exists in the same repository
        docs_branch_exists = False
        try:
            docs_branch = repo.get_branch("docs")
            docs_branch_exists = True
            print("✅ Found existing docs branch")
        except:
            print(
                "📝 Docs branch doesn't exist - will create with full codebase documentation"
            )

        git_ops = GitOperations()
        print("✅ Initialized git operations")

        # If docs branch doesn't exist, document entire codebase
        if not docs_branch_exists:
            print("🔄 Creating initial documentation for entire codebase...")
            code_files = await get_all_code_files(repo, after_sha, code_extensions)
            print(f"📄 Found {len(code_files)} code files in entire repository")
        else:
            # Only document changed files
            if not code_files:
                print("📝 No code files to document")
                return
            print(f"📄 Code files to document: {len(code_files)}")

        for file in code_files[:10]:  # Show first 10
            print(f"  • {file}")
        if len(code_files) > 10:
            print(f"  ... and {len(code_files) - 10} more files")

        # Initialize documentation generator
        docs_generator = DocsGenerator()

        # Process each file and generate documentation
        docs_content = {}
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
                docs_file_path = f"docs/{file_path.replace('/', '_')}.md"
                docs_content[docs_file_path] = documentation

                docs_created += 1
                print(f"✅ Generated documentation: {docs_file_path}")

            except Exception as e:
                print(f"❌ Failed to process {file_path}: {e}")
                continue

        # Commit all documentation to the docs branch
        if docs_content:
            try:
                commit_msg = f"docs: {'Initial documentation' if not docs_branch_exists else f'Update docs for {after_sha[:7]}'}"
                await git_ops.commit_docs_to_branch(
                    repo,
                    docs_content,
                    commit_msg,
                )
                print(f"🎉 Successfully committed {docs_created} documentation files!")
            except Exception as e:
                print(f"❌ Failed to commit documentation: {e}")

        # Set commit status
        if docs_created > 0:
            try:
                commit = repo.get_commit(after_sha)
                commit.create_status(
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
