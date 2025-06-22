import os
import tempfile
import shutil
from git import Repo
from github import GithubException


class GitOperations:
    async def commit_docs_to_branch(self, repo_client, docs_content, commit_message):
        docs_repo_name = os.getenv("DOCS_REPO", "intellidocs-output")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Clone the docs repository (different from source repo)
                docs_repo_url = (
                    f"https://github.com/{repo_client.owner.login}/{docs_repo_name}.git"
                )

                try:
                    # Try to clone existing docs repo
                    repo = Repo.clone_from(docs_repo_url, temp_dir)
                except:
                    # If docs repo doesn't exist, create it from source repo
                    print(
                        f"Docs repository {docs_repo_name} not found. Creating new repository structure."
                    )
                    # Initialize a new repo
                    repo = Repo.init(temp_dir)

                    # Create initial README
                    readme_path = os.path.join(temp_dir, "README.md")
                    with open(readme_path, "w") as f:
                        f.write(f"# {docs_repo_name}\n\nAuto-generated documentation\n")

                    repo.index.add(["README.md"])
                    repo.index.commit("Initial commit")

                # Ensure we're on main branch
                try:
                    main_branch = repo.heads.main
                    main_branch.checkout()
                except:
                    try:
                        main_branch = repo.heads.master
                        main_branch.checkout()
                    except:
                        # Create main branch if it doesn't exist
                        main_branch = repo.create_head("main")
                        main_branch.checkout()

                # Create docs directory
                docs_dir = os.path.join(temp_dir, "docs")
                os.makedirs(docs_dir, exist_ok=True)

                # Write all documentation files
                for doc_path, content in docs_content.items():
                    full_path = os.path.join(temp_dir, doc_path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)

                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)

                # Add and commit changes
                repo.git.add("docs/")

                if repo.is_dirty():
                    repo.index.commit(commit_message)

                    # Push to docs repository
                    if repo.remotes:
                        origin = repo.remotes.origin
                        origin.push("main")
                    else:
                        print(
                            f"No remote configured. You'll need to manually create and push to {docs_repo_name}"
                        )

            except Exception as e:
                print(f"Error in git operations: {e}")
                # Fallback: create docs in same repo if separate repo fails
                await self.fallback_to_same_repo(
                    repo_client, docs_content, commit_message
                )
                raise

    async def fallback_to_same_repo(self, repo_client, docs_content, commit_message):
        """Fallback method to create docs branch in same repository"""
        with tempfile.TemporaryDirectory() as temp_dir:
            clone_url = repo_client.clone_url
            repo = Repo.clone_from(clone_url, temp_dir)

            try:
                docs_branch = repo.heads.docs
                docs_branch.checkout()
            except:
                docs_branch = repo.create_head("docs")
                docs_branch.checkout()

            docs_dir = os.path.join(temp_dir, "docs")
            os.makedirs(docs_dir, exist_ok=True)

            for doc_path, content in docs_content.items():
                full_path = os.path.join(temp_dir, doc_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            repo.git.add("docs/")

            if repo.is_dirty():
                repo.index.commit(commit_message)
                origin = repo.remotes.origin
                origin.push("docs")
