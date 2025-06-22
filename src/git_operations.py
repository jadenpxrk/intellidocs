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
            docs_branch_exists = False
            try:
                docs_branch = repo_client.get_branch("docs")
                print("📝 Using existing docs branch")
                docs_branch_exists = True
            except:
                print("📝 Docs branch doesn't exist - will create docs-only branch")
                docs_branch_exists = False

            # Always sync docs branch with main branch first
            try:
                # Get the latest commit from main branch
                try:
                    main_branch = repo_client.get_branch("main")
                    latest_main_sha = main_branch.commit.sha
                except:
                    try:
                        master_branch = repo_client.get_branch("master")
                        latest_main_sha = master_branch.commit.sha
                    except:
                        # Use the latest commit
                        commits = repo_client.get_commits()
                        latest_main_sha = commits[0].sha

                if not docs_branch_exists:
                    # Create the docs branch from latest main
                    repo_client.create_git_ref(
                        ref="refs/heads/docs", sha=latest_main_sha
                    )
                    print("✅ Created docs branch from latest main")
                else:
                    # Don't reset docs branch - just update source files that have changed
                    print(
                        "✅ Using existing docs branch (preserving existing documentation)"
                    )

                    # Sync source files with main branch (keep docs branch updated with latest source)
                print("🔄 Syncing source files with main branch...")
                try:
                    # Get all files in the docs branch
                    docs_contents = repo_client.get_contents("", ref="docs")

                    # Get all files in main branch
                    main_contents = repo_client.get_contents("", ref="main")

                    def collect_all_files(contents, path_prefix=""):
                        files = {}
                        for content in contents:
                            if content.type == "file":
                                files[content.path] = content
                            elif content.type == "dir" and not content.name.startswith(
                                "."
                            ):
                                try:
                                    sub_contents = repo_client.get_contents(
                                        content.path,
                                        ref=(
                                            content.ref
                                            if hasattr(content, "ref")
                                            else "main"
                                        ),
                                    )
                                    files.update(
                                        collect_all_files(
                                            sub_contents, content.path + "/"
                                        )
                                    )
                                except:
                                    pass
                        return files

                    # Get file maps
                    docs_files = collect_all_files(docs_contents)
                    main_files = collect_all_files(main_contents)

                    # Update/add source files that exist in main
                    for main_path, main_content in main_files.items():
                        # Skip documentation files and config files
                        if (
                            main_path.startswith("docs/")
                            or main_path
                            in [
                                "README.md",
                                "LICENSE",
                                ".gitignore",
                                "requirements.txt",
                                "package.json",
                                "Dockerfile",
                            ]
                            or main_path.endswith(".md")
                        ):
                            continue

                        try:
                            # Get file content from main
                            main_file = repo_client.get_contents(main_path, ref="main")
                            file_content = main_file.decoded_content.decode("utf-8")

                            if main_path in docs_files:
                                # File exists in docs - update it
                                docs_file = docs_files[main_path]
                                try:
                                    repo_client.update_file(
                                        main_path,
                                        f"docs: Update {main_path} from main",
                                        file_content,
                                        docs_file.sha,
                                        branch="docs",
                                    )
                                    print(f"🔄 Updated: {main_path}")
                                except Exception as update_error:
                                    if "does not match" in str(update_error):
                                        # SHA mismatch - get fresh SHA and retry
                                        try:
                                            fresh_file = repo_client.get_contents(
                                                main_path, ref="docs"
                                            )
                                            repo_client.update_file(
                                                main_path,
                                                f"docs: Update {main_path} from main",
                                                file_content,
                                                fresh_file.sha,
                                                branch="docs",
                                            )
                                            print(f"🔄 Updated: {main_path} (retried)")
                                        except Exception as retry_error:
                                            print(
                                                f"⚠️  Could not update {main_path} after retry: {retry_error}"
                                            )
                                    else:
                                        raise update_error
                            else:
                                # File doesn't exist in docs - add it
                                repo_client.create_file(
                                    main_path,
                                    f"docs: Add {main_path} from main",
                                    file_content,
                                    branch="docs",
                                )
                                print(f"📥 Added: {main_path}")

                        except Exception as e:
                            print(f"⚠️  Could not sync {main_path}: {e}")

                    # Remove source files from docs that no longer exist in main (but keep their documentation)
                    for docs_path, docs_file in docs_files.items():
                        if (
                            not docs_path.startswith("docs/")
                            and docs_path
                            not in [
                                "README.md",
                                "LICENSE",
                                ".gitignore",
                                "requirements.txt",
                                "package.json",
                                "Dockerfile",
                            ]
                            and not docs_path.endswith(".md")
                            and docs_path not in main_files
                        ):
                            try:
                                repo_client.delete_file(
                                    docs_path,
                                    f"docs: Remove {docs_path} (deleted from main)",
                                    docs_file.sha,
                                    branch="docs",
                                )
                                print(f"🗑️  Removed: {docs_path} (no longer in main)")
                            except Exception as e:
                                print(f"⚠️  Could not remove {docs_path}: {e}")

                except Exception as e:
                    print(f"⚠️  Could not sync source files: {e}")

                # Now add/update documentation files in the docs branch
                for doc_path, content in docs_content.items():
                    try:
                        # Try to get existing file in docs branch
                        try:
                            existing_file = repo_client.get_contents(
                                doc_path, ref="docs"
                            )
                            # Update existing file
                            repo_client.update_file(
                                doc_path,
                                f"docs: Update {doc_path}",
                                content,
                                existing_file.sha,
                                branch="docs",
                            )
                            print(f"📝 Updated: {doc_path}")
                        except:
                            # Create new file
                            repo_client.create_file(
                                doc_path,
                                f"docs: Add {doc_path}",
                                content,
                                branch="docs",
                            )
                            print(f"📝 Created: {doc_path}")

                    except Exception as e:
                        print(f"❌ Failed to create/update {doc_path}: {e}")
                        continue

            except Exception as e:
                print(f"❌ Failed to sync docs branch: {e}")
                raise

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
