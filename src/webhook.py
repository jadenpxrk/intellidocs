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
            installation_id = event_data["installation"]["id"]
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

                changed_files = await self.get_changed_files(
                    repo_client, before_sha, after_sha
                )

                if not changed_files:
                    self.set_commit_status(
                        repo_client, after_sha, "success", "No code files changed"
                    )
                    return

                await self.generate_and_commit_docs(
                    repo_client, repo_full_name, changed_files, after_sha
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
