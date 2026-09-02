from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import RspamdConfig


@dataclass(frozen=True)
class RspamdResult:
    score: float
    required_score: float
    action: str
    symbols: dict[str, Any]


class RspamdClient:
    def __init__(self, config: RspamdConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def check(self, raw_message: bytes) -> RspamdResult:
        headers = {"Content-Type": "message/rfc822"}
        if self.config.password:
            headers["Password"] = self.config.password
        response = self.session.post(
            f"{self.config.url}/checkv2", data=raw_message, headers=headers,
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        result = response.json()
        return RspamdResult(
            score=float(result.get("score", 0)),
            required_score=float(result.get("required_score", 0)),
            action=str(result.get("action", "no action")),
            symbols=dict(result.get("symbols", {})),
        )
