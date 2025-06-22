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

                # Only remove/update source files that have changed, preserve existing docs
                print("🧹 Updating only changed source code files in docs branch...")
                try:
                    # Get all files in the docs branch
                    contents = repo_client.get_contents("", ref="docs")

                    def collect_changed_source_files(contents):
                        files_to_remove = []
                        for content in contents:
                            if content.type == "file":
                                # Only remove source code files that exist in main branch
                                # This preserves docs for files that were deleted from main
                                if (
                                    not content.path.startswith("docs/")
                                    and content.path
                                    not in [
                                        "README.md",
                                        "LICENSE",
                                        ".gitignore",
                                        "requirements.txt",
                                        "package.json",
                                        "Dockerfile",
                                    ]
                                    and not content.path.endswith(".md")
                                ):
                                    # Check if this source file still exists in main
                                    try:
                                        repo_client.get_contents(
                                            content.path, ref="main"
                                        )
                                        # File exists in main, so remove it from docs (will be re-added with latest version)
                                        files_to_remove.append(content)
                                    except:
                                        # File doesn't exist in main anymore, keep it in docs
                                        print(
                                            f"📚 Preserving docs for deleted file: {content.path}"
                                        )
                            elif content.type == "dir" and content.name not in [
                                "docs",
                                ".git",
                                ".github",
                            ]:
                                # Handle source directories
                                try:
                                    sub_contents = repo_client.get_contents(
                                        content.path, ref="docs"
                                    )
                                    files_to_remove.extend(
                                        collect_changed_source_files(sub_contents)
                                    )
                                except:
                                    pass
                        return files_to_remove

                    source_files_to_remove = collect_changed_source_files(contents)

                    # Remove only the source files that still exist in main
                    for file_content in source_files_to_remove:
                        try:
                            repo_client.delete_file(
                                file_content.path,
                                f"docs: Remove source file {file_content.path} for update",
                                file_content.sha,
                                branch="docs",
                            )
                            print(f"🔄 Removed for update: {file_content.path}")
                        except Exception as e:
                            print(f"⚠️  Could not remove {file_content.path}: {e}")

                except Exception as e:
                    print(f"⚠️  Could not clean source files: {e}")

                # Add current source files from main to docs branch
                print("📥 Adding latest source files from main to docs branch...")
                try:
                    # Get all source files from main branch
                    main_contents = repo_client.get_contents("", ref="main")

                    def add_source_files_to_docs(contents, path_prefix=""):
                        for content in contents:
                            if content.type == "file":
                                # Add source code files (but not config files)
                                if (
                                    not content.path.startswith("docs/")
                                    and content.path
                                    not in [
                                        "README.md",
                                        "LICENSE",
                                        ".gitignore",
                                        "requirements.txt",
                                        "package.json",
                                        "Dockerfile",
                                    ]
                                    and not content.path.endswith(".md")
                                ):
                                    try:
                                        # Get file content from main
                                        main_file = repo_client.get_contents(
                                            content.path, ref="main"
                                        )
                                        file_content = main_file.decoded_content.decode(
                                            "utf-8"
                                        )

                                        # Add to docs branch
                                        repo_client.create_file(
                                            content.path,
                                            f"docs: Add latest {content.path}",
                                            file_content,
                                            branch="docs",
                                        )
                                        print(f"📥 Added: {content.path}")
                                    except Exception as e:
                                        print(f"⚠️  Could not add {content.path}: {e}")
                            elif content.type == "dir" and content.name not in [
                                "docs",
                                ".git",
                                ".github",
                            ]:
                                try:
                                    sub_contents = repo_client.get_contents(
                                        content.path, ref="main"
                                    )
                                    add_source_files_to_docs(
                                        sub_contents, content.path + "/"
                                    )
                                except:
                                    pass

                    add_source_files_to_docs(main_contents)

                except Exception as e:
                    print(f"⚠️  Could not add source files: {e}")

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
