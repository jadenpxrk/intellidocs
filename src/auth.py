import os
from github import Github, Auth
from cryptography.hazmat.primitives import serialization


class GitHubAppAuth:
    def __init__(self):
        self.app_id = os.getenv("GITHUB_APP_ID")
        self.private_key_path = os.getenv(
            "GITHUB_PRIVATE_KEY_PATH", "app_private_key.pem"
        )

        if not self.app_id:
            raise ValueError("GITHUB_APP_ID environment variable is required")

        try:
            with open(self.private_key_path, "rb") as key_file:
                private_key_bytes = key_file.read()
            self.private_key = serialization.load_pem_private_key(
                private_key_bytes, password=None
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Private key file not found at '{self.private_key_path}'. "
                "Ensure GITHUB_PRIVATE_KEY_PATH is set correctly."
            )

    def get_installation_client(self, installation_id):
        auth = Auth.AppAuth(int(self.app_id), self.private_key)

        # Get an installation access token
        installation_auth = auth.get_installation_auth(installation_id)

        # Return a PyGithub client authenticated as the installation
        return Github(auth=installation_auth)

    def get_repo_client(self, repo_full_name, installation_id):
        client = self.get_installation_client(installation_id)
        return client.get_repo(repo_full_name)
