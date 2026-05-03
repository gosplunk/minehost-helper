from __future__ import annotations

import os
import re
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .config import JAVA_DIR, ensure_directories
from .utils import hidden_subprocess_kwargs

DEFAULT_JAVA_FEATURE_VERSION = 25
DOWNLOAD_HEADERS = {
    "User-Agent": "MineHostHelper/0.1 (+https://adoptium.net/)",
    "Accept": "application/octet-stream,*/*",
}


def _java_exe_name() -> str:
    return "java.exe" if os.name == "nt" else "java"


def temurin_jre_url(feature_version: int) -> str:
    return (
        f"https://api.adoptium.net/v3/binary/latest/{feature_version}/ga/windows/x64/"
        "jre/hotspot/normal/eclipse?project=jdk"
    )


def class_major_to_java_version(major_version: int) -> int:
    if major_version < 45:
        raise ValueError(f"Unsupported Java class file version: {major_version}")
    if major_version <= 48:
        return major_version - 44
    return major_version - 44


def required_java_version_for_jar(jar_path: Path) -> int | None:
    if not jar_path.exists() or not zipfile.is_zipfile(jar_path):
        return None
    with zipfile.ZipFile(jar_path) as archive:
        class_names = archive.namelist()
        preferred = "net/minecraft/bundler/Main.class"
        selected = preferred if preferred in class_names else next((name for name in class_names if name.endswith(".class")), None)
        if not selected:
            return None
        header = archive.read(selected)[:8]
    if len(header) < 8 or header[:4] != b"\xca\xfe\xba\xbe":
        return None
    major_version = int.from_bytes(header[6:8], "big")
    return class_major_to_java_version(major_version)


def java_feature_version(java_path: Path | None = None) -> int | None:
    version = java_version(java_path)
    if not version:
        return None
    match = re.search(r'version "([^"]+)"', version)
    if not match:
        return None
    raw = match.group(1)
    if raw.startswith("1."):
        parts = raw.split(".")
        return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    feature = raw.split(".", 1)[0]
    return int(feature) if feature.isdigit() else None


def _compatible_java(candidates: list[Path], min_version: int | None = None) -> Path | None:
    compatible: list[tuple[int, Path]] = []
    for candidate in candidates:
        feature = java_feature_version(candidate)
        if feature is None:
            continue
        if min_version is None or feature >= min_version:
            compatible.append((feature, candidate))
    if not compatible:
        return candidates[0] if candidates and min_version is None else None
    compatible.sort(key=lambda item: item[0])
    return compatible[0][1]


def bundled_java_path(min_version: int | None = None) -> Path | None:
    candidates = sorted(JAVA_DIR.glob("**/bin/java.exe"))
    return _compatible_java(candidates, min_version)


def system_java_path() -> Path | None:
    found = shutil.which("java")
    return Path(found) if found else None


def get_java_path(min_version: int | None = None) -> Path | None:
    bundled = bundled_java_path(min_version)
    if bundled:
        return bundled
    system = system_java_path()
    if not system:
        return None
    if min_version is not None:
        feature = java_feature_version(system)
        if feature is None or feature < min_version:
            return None
    return system


def java_version(java_path: Path | None = None) -> str | None:
    java = java_path or get_java_path()
    if not java:
        return None
    try:
        result = subprocess.run(
            [str(java), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        return (result.stderr or result.stdout).splitlines()[0]
    except Exception:
        return None


def status() -> dict[str, str | bool | None]:
    bundled = bundled_java_path(DEFAULT_JAVA_FEATURE_VERSION) or bundled_java_path()
    java = get_java_path(DEFAULT_JAVA_FEATURE_VERSION) or get_java_path()
    return {
        "available": java is not None,
        "path": str(java) if java else None,
        "bundled": bundled is not None and java == bundled,
        "version": java_version(java),
        "feature_version": java_feature_version(java),
    }


def _powershell_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def _is_certificate_error(exc: Exception) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, ssl.SSLCertVerificationError):
        return True
    text = str(exc).lower()
    return "certificate verify failed" in text or "unable to get local issuer certificate" in text


def _download_file_with_powershell(url: str, destination: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell was not found for Windows-native download fallback")

    temp_path = destination.with_suffix(destination.suffix + ".download")
    script = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$headers = @{{
  'User-Agent' = '{_powershell_quote(DOWNLOAD_HEADERS["User-Agent"])}'
  'Accept' = '{_powershell_quote(DOWNLOAD_HEADERS["Accept"])}'
}}
Invoke-WebRequest -Uri '{_powershell_quote(url)}' -OutFile '{_powershell_quote(temp_path)}' -Headers $headers -UseBasicParsing -MaximumRedirection 10
"""
    result = subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Windows-native download fallback failed: {output or result.returncode}")
    if not temp_path.exists() or temp_path.stat().st_size < 1024 * 1024:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError("Windows-native download fallback produced an unexpectedly small Java archive")
    temp_path.replace(destination)


def _download_file(url: str, destination: Path, attempts: int = 3) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".download")
    last_error: Exception | None = None
    saw_certificate_error = False
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers=DOWNLOAD_HEADERS)
            with urllib.request.urlopen(request, timeout=90) as response, temp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            if temp_path.stat().st_size < 1024 * 1024:
                raise RuntimeError("Downloaded Java archive was unexpectedly small")
            temp_path.replace(destination)
            return
        except urllib.error.HTTPError as exc:
            last_error = exc
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if exc.code == 403:
                raise RuntimeError(
                    "Eclipse Temurin download was blocked with HTTP 403. "
                    "This is usually a network, proxy, antivirus, or GitHub release asset restriction. "
                    "Try again, use a different network, or install Java from https://adoptium.net/temurin/releases/."
                ) from exc
        except Exception as exc:
            last_error = exc
            saw_certificate_error = saw_certificate_error or _is_certificate_error(exc)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if saw_certificate_error and os.name == "nt":
                break
        if attempt < attempts:
            time.sleep(1.5 * attempt)

    if saw_certificate_error and os.name == "nt":
        try:
            _download_file_with_powershell(url, destination)
            return
        except Exception as fallback_error:
            raise RuntimeError(
                "Could not download Eclipse Temurin Java because Windows/Python could not verify the SSL certificate, "
                f"and the Windows-native fallback also failed: {fallback_error}"
            ) from fallback_error

    raise RuntimeError(f"Could not download Eclipse Temurin Java: {last_error}") from last_error


def install_temurin_jre(feature_version: int = DEFAULT_JAVA_FEATURE_VERSION) -> dict[str, str | bool | int | None]:
    ensure_directories()
    if bundled_java_path(feature_version):
        return status()
    zip_path = JAVA_DIR / f"temurin-jre-{feature_version}.zip"
    _download_file(temurin_jre_url(feature_version), zip_path)
    if not zipfile.is_zipfile(zip_path):
        zip_path.unlink(missing_ok=True)
        raise RuntimeError("Downloaded Java archive was not a valid zip file")
    extract_dir = JAVA_DIR / f"temurin-{feature_version}"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    zip_path.unlink(missing_ok=True)
    if not bundled_java_path(feature_version):
        raise RuntimeError(f"Temurin Java {feature_version} downloaded, but java.exe was not found in the archive")
    return status()
