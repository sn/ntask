from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(slots=True)
class RemoteCacheConfig:
    type: str  # "local-fs" | "http" | "s3" | "gcs"
    path: str | None = None           # local-fs
    url: str | None = None            # http
    auth_header: str | None = None    # http
    bucket: str | None = None         # s3 / gcs
    prefix: str = ""                  # s3 / gcs
    endpoint_url: str | None = None   # s3


@dataclass(slots=True)
class ProjectConfig:
    cache_dir: str = ".ntask"
    default_concurrency: int = 1
    remote_cache: RemoteCacheConfig | None = None
    tui: bool | None = None  # None = auto; False = force off; True = force on


def load_project_config(project_root: Path) -> ProjectConfig:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return ProjectConfig()
    data = tomllib.loads(pyproject.read_text())
    tool = data.get("tool", {}).get("ntask", {})

    remote_cache: RemoteCacheConfig | None = None
    rc = tool.get("remote_cache")
    if rc is not None:
        # Expand $VAR in string fields at load time.
        def _exp(v: object) -> object:
            return os.path.expandvars(v) if isinstance(v, str) else v

        def _exp_opt(key: str) -> str | None:
            v = rc.get(key)
            return cast(str, _exp(v)) if v is not None else None

        remote_cache = RemoteCacheConfig(
            type=str(_exp(rc.get("type", ""))),
            path=_exp_opt("path"),
            url=_exp_opt("url"),
            auth_header=_exp_opt("auth_header"),
            bucket=_exp_opt("bucket"),
            prefix=str(_exp(rc.get("prefix", ""))),
            endpoint_url=_exp_opt("endpoint_url"),
        )

    return ProjectConfig(
        cache_dir=tool.get("cache_dir", ".ntask"),
        default_concurrency=int(tool.get("default_concurrency", 1)),
        remote_cache=remote_cache,
        tui=tool.get("tui"),
    )
