"""HTTP backend using stdlib urllib - PUT/GET/HEAD against any URL."""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ._tar import extract_tar, tar_directory


class HTTPBackend:
    """GET/PUT/HEAD against a base URL. Optional Authorization header."""

    def __init__(self, *, base_url: str, auth_header: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header

    def _url(self, *parts: str) -> str:
        return self.base_url + "/" + "/".join(parts)

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.auth_header is not None:
            h["Authorization"] = self.auth_header
        return h

    def _head(self, url: str) -> int:
        req = Request(url, method="HEAD", headers=self._headers())  # noqa: S310
        try:
            with urlopen(req) as resp:  # noqa: S310
                return cast(int, resp.status)
        except HTTPError as e:
            return e.code

    def _get(self, url: str) -> bytes | None:
        req = Request(url, method="GET", headers=self._headers())  # noqa: S310
        try:
            with urlopen(req) as resp:  # noqa: S310
                return cast(bytes, resp.read())
        except HTTPError as e:
            if e.code == 404:
                return None
            raise

    def _put(self, url: str, body: bytes) -> None:
        req = Request(  # noqa: S310
            url,
            data=body,
            method="PUT",
            headers={**self._headers(), "Content-Length": str(len(body))},
        )
        try:
            with urlopen(req) as resp:  # noqa: S310
                if resp.status >= 300:
                    raise RuntimeError(f"PUT {url} returned {resp.status}")
        except HTTPError as e:
            raise RuntimeError(f"PUT {url} failed: HTTP {e.code}") from e

    def has_entry(self, fqn: str, key: str) -> bool:
        return self._head(self._url("entries", fqn, f"{key}.json")) == 200

    def get_entry(self, fqn: str, key: str) -> dict[str, object] | None:
        body = self._get(self._url("entries", fqn, f"{key}.json"))
        if body is None:
            return None
        return cast(dict[str, object], json.loads(body))

    def put_entry(self, fqn: str, key: str, entry: dict[str, object]) -> None:
        self._put(
            self._url("entries", fqn, f"{key}.json"),
            json.dumps(entry, indent=2).encode("utf-8"),
        )

    def has_output(self, outputs_hash: str) -> bool:
        return self._head(self._url("outputs", f"{outputs_hash}.tar.gz")) == 200

    def get_output(self, outputs_hash: str, dest_dir: Path) -> None:
        body = self._get(self._url("outputs", f"{outputs_hash}.tar.gz"))
        if body is None:
            raise FileNotFoundError(outputs_hash)
        extract_tar(body, dest_dir)

    def put_output(self, outputs_hash: str, source_dir: Path) -> None:
        self._put(
            self._url("outputs", f"{outputs_hash}.tar.gz"),
            tar_directory(source_dir),
        )
