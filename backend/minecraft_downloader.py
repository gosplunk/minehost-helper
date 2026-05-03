from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

from .config import MINECRAFT_RUNTIME_DIR, ensure_directories

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def _download_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_version_manifest() -> dict[str, Any]:
    return _download_json(VERSION_MANIFEST_URL)


def list_versions() -> dict[str, Any]:
    manifest = get_version_manifest()
    releases = [
        {"id": item["id"], "type": item["type"]}
        for item in manifest.get("versions", [])
        if item.get("type") == "release"
    ][:30]
    return {"latest": manifest.get("latest", {}).get("release"), "releases": releases}


def resolve_version(version: str) -> dict[str, Any]:
    manifest = get_version_manifest()
    target = manifest.get("latest", {}).get("release") if version == "latest" else version
    for item in manifest.get("versions", []):
        if item.get("id") == target:
            metadata = _download_json(item["url"])
            server = metadata.get("downloads", {}).get("server")
            if not server:
                raise RuntimeError(f"Minecraft {target} does not provide a server jar")
            return {"id": target, "server": server}
    raise RuntimeError(f"Minecraft version {target} was not found in Mojang's manifest")


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_server_jar(version: str) -> tuple[str, Path]:
    ensure_directories()
    resolved = resolve_version(version)
    version_id = resolved["id"]
    server = resolved["server"]
    jar_dir = MINECRAFT_RUNTIME_DIR / version_id
    jar_dir.mkdir(parents=True, exist_ok=True)
    jar_path = jar_dir / "server.jar"
    expected_sha1 = server.get("sha1")
    if jar_path.exists() and (not expected_sha1 or _sha1(jar_path) == expected_sha1):
        return version_id, jar_path
    temp_path = jar_path.with_suffix(".jar.download")
    urllib.request.urlretrieve(server["url"], temp_path)
    if expected_sha1 and _sha1(temp_path) != expected_sha1:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError("Downloaded Minecraft server jar did not match Mojang's SHA1 checksum")
    temp_path.replace(jar_path)
    return version_id, jar_path
