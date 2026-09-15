from __future__ import annotations

import requests

from .config import PaperlessConfig


class PaperlessClient:
    def __init__(self, config: PaperlessConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def upload_document(self, filename: str, content: bytes, title: str | None = None) -> None:
        headers = {"Authorization": f"Token {self.config.token}"} if self.config.token else {}
        files = {"document": (filename, content)}
        data = {"title": title} if title else {}
        response = self.session.post(
            f"{self.config.url}/api/documents/post_document/",
            headers=headers, files=files, data=data,
            timeout=self.config.timeout,
        )
        response.raise_for_status()
