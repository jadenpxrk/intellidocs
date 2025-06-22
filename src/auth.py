import os
import jwt
import time
from github import Github
from cryptography.hazmat.primitives import serialization


class GitHubAppAuth:
    def __init__(self):
        self.app_id = os.getenv("GITHUB_APP_ID")
        self.private_key_path = os.getenv(
            "GITHUB_PRIVATE_KEY_PATH", "app_private_key.pem"
        )

        if not self.app_id:
            raise ValueError("GITHUB_APP_ID environment variable is required")

        with open(self.private_key_path, "rb") as key_file:
            self.private_key = serialization.load_pem_private_key(
                key_file.read(), password=None
            )

    def get_jwt_token(self):
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 600, "iss": self.app_id}

        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def get_installation_client(self, installation_id):
        jwt_token = self.get_jwt_token()
        app_client = Github(jwt=jwt_token)

        installation = app_client.get_app().get_installation(installation_id)
        access_token = installation.get_access_token()

        return Github(access_token.token)

    def get_repo_client(self, repo_full_name, installation_id):
        client = self.get_installation_client(installation_id)
        return client.get_repo(repo_full_name)
