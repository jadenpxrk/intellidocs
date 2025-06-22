import os
import tempfile
import shutil
from git import Repo
from github import GithubException


class GitOperations:
    def __init__(self):
        pass

    async def commit_docs_to_repository(
        self, github_client, repo_owner, repo_name, docs_content, commit_message
    ):
        """Commit documentation to a separate docs repository"""
        docs_repo_name = f"{repo_name}-docs"

        # Try to get or create the docs repository
        try:
            docs_repo = github_client.get_repo(f"{repo_owner}/{docs_repo_name}")
            print(f"✅ Using existing docs repository: {repo_owner}/{docs_repo_name}")
        except:
            # Create new docs repository using GitHub API directly
            try:
                import requests

                # Get the access token from the github_client
                access_token = github_client._Github__requester._Requester__authorizationHeader.split(
                    " "
                )[
                    1
                ]

                # Create repository using GitHub API
                create_repo_url = "https://api.github.com/user/repos"
                headers = {
                    "Authorization": f"token {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }

                repo_data = {
                    "name": docs_repo_name,
                    "description": f"Auto-generated documentation for {repo_name}",
                    "auto_init": True,
                    "private": False,
                }

                response = requests.post(
                    create_repo_url, headers=headers, json=repo_data
                )

                if response.status_code == 201:
                    print(
                        f"✅ Created new docs repository: {repo_owner}/{docs_repo_name}"
                    )
                    # Get the newly created repository
                    docs_repo = github_client.get_repo(f"{repo_owner}/{docs_repo_name}")
                else:
                    print(
                        f"❌ Failed to create docs repository: {response.status_code} {response.text}"
                    )
                    raise Exception(
                        f"Failed to create repository: {response.status_code} - {response.text}"
                    )

            except Exception as e:
                print(f"❌ Failed to create docs repository: {e}")
                raise

        # Create or update files in the docs repository
        for doc_path, content in docs_content.items():
            try:
                # Try to get existing file
                try:
                    existing_file = docs_repo.get_contents(doc_path)
                    # Update existing file
                    docs_repo.update_file(
                        doc_path, f"Update {doc_path}", content, existing_file.sha
                    )
                    print(f"📝 Updated: {doc_path}")
                except:
                    # Create new file
                    docs_repo.create_file(doc_path, f"Create {doc_path}", content)
                    print(f"📝 Created: {doc_path}")
            except Exception as e:
                print(f"❌ Failed to create/update {doc_path}: {e}")
                continue

    async def commit_docs_to_branch(self, repo_client, docs_content, commit_message):
        """Create or update documentation in a docs branch of the same repository"""
        try:
            # Check if docs branch exists
            try:
                docs_branch = repo_client.get_branch("docs")
                print("📝 Using existing docs branch")
                base_sha = docs_branch.commit.sha
            except:
                # Create docs branch from main/master
                try:
                    main_branch = repo_client.get_branch("main")
                    base_sha = main_branch.commit.sha
                    print("📝 Creating docs branch from main")
                except:
                    try:
                        master_branch = repo_client.get_branch("master")
                        base_sha = master_branch.commit.sha
                        print("📝 Creating docs branch from master")
                    except:
                        # Use the latest commit as base
                        commits = repo_client.get_commits()
                        base_sha = commits[0].sha
                        print("📝 Creating docs branch from latest commit")

                # Create the docs branch
                repo_client.create_git_ref(ref="refs/heads/docs", sha=base_sha)
                print("✅ Created docs branch")

            # Create or update each documentation file
            for doc_path, content in docs_content.items():
                try:
                    # Try to get existing file in docs branch
                    try:
                        existing_file = repo_client.get_contents(doc_path, ref="docs")
                        # Update existing file
                        repo_client.update_file(
                            doc_path,
                            f"Update {doc_path}",
                            content,
                            existing_file.sha,
                            branch="docs",
                        )
                        print(f"📝 Updated: {doc_path}")
                    except:
                        # Create new file
                        repo_client.create_file(
                            doc_path, f"Create {doc_path}", content, branch="docs"
                        )
                        print(f"📝 Created: {doc_path}")

                except Exception as e:
                    print(f"❌ Failed to create/update {doc_path}: {e}")
                    continue

            print(f"✅ Successfully updated docs branch with {len(docs_content)} files")

        except Exception as e:
            print(f"❌ Error in docs branch operations: {e}")
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
