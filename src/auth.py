import os
import jwt
import time
import requests
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

    def get_jwt_token(self):
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 600, "iss": int(self.app_id)}
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def get_installation_access_token(self, installation_id):
        jwt_token = self.get_jwt_token()

        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        url = (
            f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        )
        response = requests.post(url, headers=headers)

        if response.status_code != 201:
            raise Exception(
                f"Failed to get access token: {response.status_code} - {response.text}"
            )

        return response.json()["token"]

    def get_installation_client(self, installation_id):
        access_token = self.get_installation_access_token(installation_id)
        return Github(access_token)

    def get_repo_client(self, repo_full_name, installation_id):
        client = self.get_installation_client(installation_id)
        return client.get_repo(repo_full_name)
