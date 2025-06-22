import os
from github import GithubException
from src.auth import GitHubAppAuth
from src.git_operations import GitOperations
from src.docs_generator import DocsGenerator


class WebhookHandler:
    def __init__(self):
        self.auth = GitHubAppAuth()
        self.git_ops = GitOperations()
        self.docs_gen = DocsGenerator()

    async def handle_push(self, event_data):
        try:
            repo_full_name = event_data["repository"]["full_name"]

            print(f"🔍 Debug: Webhook payload keys: {list(event_data.keys())}")
            if "installation" in event_data:
                print(f"🔍 Debug: Installation data: {event_data['installation']}")

            installation_id = None
            if "installation" in event_data and "id" in event_data["installation"]:
                installation_id = event_data["installation"]["id"]
                print(f"🔍 Debug: Found installation ID in payload: {installation_id}")
            else:
                installation_id = os.getenv("GITHUB_INSTALLATION_ID")
                if installation_id:
                    print(
                        f"🔍 Debug: Using installation ID from env: {installation_id}"
                    )
                else:
                    print(
                        "❌ Debug: No installation ID found in webhook payload or environment variables"
                    )
                    print(
                        f"❌ Debug: Available webhook keys: {list(event_data.keys())}"
                    )
                    raise ValueError(
                        "No installation ID found in webhook payload or environment variables"
                    )

            before_sha = event_data["before"]
            after_sha = event_data["after"]
            ref = event_data["ref"]

            if ref != "refs/heads/main" and ref != "refs/heads/master":
                return

            repo_client = self.auth.get_repo_client(repo_full_name, installation_id)

            try:
                self.set_commit_status(
                    repo_client, after_sha, "pending", "Generating documentation..."
                )

                # Check if docs branch exists to determine strategy
                docs_branch_exists = False
                try:
                    repo_client.get_branch("docs")
                    docs_branch_exists = True
                    print("✅ Found existing docs branch")
                except:
                    print(
                        "📝 Docs branch doesn't exist - will create with full codebase documentation"
                    )

                if docs_branch_exists:
                    # Docs branch exists - only document changed files (incremental)
                    changed_files = await self.get_changed_files(
                        repo_client, before_sha, after_sha
                    )

                    if not changed_files:
                        print("📝 No code files to document")
                        return

                    print(f"📄 Code files to document: {len(changed_files)}")
                    for file_info in changed_files:
                        print(f"  • {file_info['filename']}")

                    await self.generate_and_commit_docs(
                        repo_client, repo_full_name, changed_files, after_sha
                    )
                else:
                    # No docs branch - document entire codebase (initial)
                    print("🔄 Creating initial documentation for entire codebase...")
                    all_files = await self.get_all_code_files(repo_client, after_sha)

                    if not all_files:
                        self.set_commit_status(
                            repo_client, after_sha, "success", "No code files found"
                        )
                        return

                    print(f"📄 Found {len(all_files)} code files in entire repository")
                    for file_info in all_files:
                        print(f"  • {file_info['filename']}")

                    await self.generate_and_commit_docs(
                        repo_client, repo_full_name, all_files, after_sha
                    )

                self.set_commit_status(
                    repo_client,
                    after_sha,
                    "success",
                    "Documentation updated successfully",
                )

            except Exception as e:
                self.set_commit_status(
                    repo_client,
                    after_sha,
                    "error",
                    f"Failed to generate docs: {str(e)}",
                )
                raise

        except Exception as e:
            print(f"Error handling push event: {e}")

    async def get_changed_files(self, repo_client, before_sha, after_sha):
        try:
            comparison = repo_client.compare(before_sha, after_sha)
            changed_files = []

            code_extensions = {
                ".py",
                ".js",
                ".ts",
                ".java",
                ".cpp",
                ".c",
                ".go",
                ".rs",
                ".rb",
                ".php",
            }

            for file in comparison.files:
                if file.status in ["added", "modified"]:
                    file_ext = os.path.splitext(file.filename)[1]
                    if file_ext in code_extensions:
                        changed_files.append(
                            {
                                "filename": file.filename,
                                "content": repo_client.get_contents(
                                    file.filename, ref=after_sha
                                ).decoded_content.decode("utf-8"),
                            }
                        )

            return changed_files

        except Exception as e:
            print(f"Error getting changed files: {e}")
            return []

    async def get_all_code_files(self, repo_client, commit_sha):
        """Get all code files in the repository"""
        try:
            all_files = []
            code_extensions = {
                ".py",
                ".js",
                ".ts",
                ".java",
                ".cpp",
                ".c",
                ".go",
                ".rs",
                ".rb",
                ".php",
            }

            def collect_files(contents, path_prefix=""):
                for content in contents:
                    if content.type == "file":
                        file_ext = os.path.splitext(content.name)[1]
                        if file_ext in code_extensions:
                            try:
                                file_content = repo_client.get_contents(
                                    content.path, ref=commit_sha
                                ).decoded_content.decode("utf-8")
                                all_files.append(
                                    {
                                        "filename": content.path,
                                        "content": file_content,
                                    }
                                )
                                print(f"📖 Processing: {content.path}")
                                print(f"✅ Collected content for: {content.path}")
                            except Exception as e:
                                print(f"⚠️  Could not read {content.path}: {e}")
                    elif content.type == "dir" and not content.name.startswith("."):
                        try:
                            sub_contents = repo_client.get_contents(
                                content.path, ref=commit_sha
                            )
                            collect_files(sub_contents, content.path + "/")
                        except Exception as e:
                            print(f"⚠️  Could not read directory {content.path}: {e}")

            # Start from root
            root_contents = repo_client.get_contents("", ref=commit_sha)
            collect_files(root_contents)

            return all_files

        except Exception as e:
            print(f"Error getting all code files: {e}")
            return []

    async def generate_and_commit_docs(
        self, repo_client, repo_full_name, changed_files, commit_sha
    ):
        docs_content = {}

        for file_info in changed_files:
            filename = file_info["filename"]
            content = file_info["content"]

            doc_content = self.docs_gen.summarise_file(filename, content)
            doc_filename = f"docs/{filename.replace('/', '_')}.md"
            docs_content[doc_filename] = doc_content

        await self.git_ops.commit_docs_to_branch(
            repo_client, docs_content, f"docs: sync {commit_sha[:7]}"
        )

    def set_commit_status(self, repo_client, commit_sha, state, description):
        try:
            commit = repo_client.get_commit(commit_sha)
            commit.create_status(
                state=state,
                description=description,
                context="intellidocs/documentation",
            )
        except GithubException as e:
            print(f"Failed to set commit status: {e}")
