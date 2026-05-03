from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .properties_manager import read_properties

REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
IGNORED_SCAN_DIRS = {
    ".git",
    "__pycache__",
    "backups",
    "cache",
    "config",
    "crash-reports",
    "libraries",
    "logs",
    "mods",
    "plugins",
    "versions",
}

DIMENSIONS: dict[str, dict[str, str]] = {
    "overworld": {"label": "Overworld", "region_path": "region"},
    "nether": {"label": "Nether", "region_path": "DIM-1/region"},
    "end": {"label": "The End", "region_path": "DIM1/region"},
}


def _level_name(server_dir: Path) -> str:
    try:
        return str(read_properties(server_dir).get("level-name") or "world")
    except Exception:
        return "world"


def _classify_region_dir(server_dir: Path, region_dir: Path) -> dict[str, Any] | None:
    if region_dir.name.lower() != "region":
        return None
    try:
        relative = region_dir.relative_to(server_dir)
    except ValueError:
        return None
    files = sorted(path for path in region_dir.glob("r.*.*.mca") if REGION_RE.match(path.name))
    if not files:
        return None

    parent = region_dir.parent
    if parent.name == "DIM-1":
        dimension = "nether"
        world_dir = parent.parent
    elif parent.name == "DIM1":
        dimension = "end"
        world_dir = parent.parent
    else:
        world_dir = parent
        lowered = world_dir.name.lower()
        if lowered.endswith("_nether") or lowered in {"nether", "world_nether"}:
            dimension = "nether"
        elif lowered.endswith("_the_end") or lowered.endswith("_end") or lowered in {"end", "the_end", "world_the_end"}:
            dimension = "end"
        else:
            dimension = "overworld"

    return {
        "dimension": dimension,
        "world_dir": world_dir,
        "region_dir": region_dir,
        "relative_region_path": relative.as_posix(),
        "region_files": files,
    }


def _discover_region_candidates(server_dir: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not server_dir.exists():
        return candidates

    for root, dirs, _files in os.walk(server_dir):
        current = Path(root)
        dirs[:] = [
            dirname
            for dirname in dirs
            if dirname.lower() not in IGNORED_SCAN_DIRS and not dirname.startswith(".")
        ]
        if current.name.lower() != "region":
            continue
        candidate = _classify_region_dir(server_dir, current)
        if candidate:
            candidates.append(candidate)
    return candidates


def _empty_bounds() -> dict[str, int | None]:
    return {"min_x": None, "max_x": None, "min_z": None, "max_z": None}


def _scan_region_files(region_files: list[Path]) -> dict[str, Any]:
    chunks: list[dict[str, int]] = []
    bounds = _empty_bounds()
    region_count = 0
    unreadable_files = 0
    invalid_files = 0

    for path in region_files:
        match = REGION_RE.match(path.name)
        if not match:
            continue
        region_x = int(match.group(1))
        region_z = int(match.group(2))
        try:
            with path.open("rb") as handle:
                header = handle.read(4096)
        except OSError:
            unreadable_files += 1
            continue
        if len(header) < 4096:
            invalid_files += 1
            continue

        region_has_chunks = False
        for index in range(1024):
            offset = index * 4
            sector_offset = int.from_bytes(header[offset:offset + 3], "big")
            sector_count = header[offset + 3]
            if sector_offset == 0 or sector_count == 0:
                continue
            local_x = index % 32
            local_z = index // 32
            chunk_x = region_x * 32 + local_x
            chunk_z = region_z * 32 + local_z
            chunks.append({"x": chunk_x, "z": chunk_z})
            region_has_chunks = True
            bounds["min_x"] = chunk_x if bounds["min_x"] is None else min(int(bounds["min_x"]), chunk_x)
            bounds["max_x"] = chunk_x if bounds["max_x"] is None else max(int(bounds["max_x"]), chunk_x)
            bounds["min_z"] = chunk_z if bounds["min_z"] is None else min(int(bounds["min_z"]), chunk_z)
            bounds["max_z"] = chunk_z if bounds["max_z"] is None else max(int(bounds["max_z"]), chunk_z)
        if region_has_chunks:
            region_count += 1

    return {
        "chunks": chunks,
        "chunk_count": len(chunks),
        "region_count": region_count,
        "region_files_found": len(region_files),
        "unreadable_files": unreadable_files,
        "invalid_files": invalid_files,
        "bounds": bounds,
    }


def _candidate_score(candidate: dict[str, Any], configured_world_name: str) -> tuple[int, int, str]:
    score = 0
    world_name = candidate["world_dir"].name
    if world_name == configured_world_name:
        score += 200
    if world_name.lower() == configured_world_name.lower():
        score += 80
    if world_name.lower() == "world":
        score += 20
    score += min(50, len(candidate["region_files"]))
    return (score, len(candidate["region_files"]), world_name)


def _world_dir_for_missing(server_dir: Path, dimension: str) -> Path:
    configured = server_dir / _level_name(server_dir)
    expected = configured / DIMENSIONS[dimension]["region_path"]
    if expected.exists():
        return configured
    world = server_dir / "world"
    if (world / DIMENSIONS[dimension]["region_path"]).exists():
        return world
    return configured


def _empty_result(server_dir: Path, dimension: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    world_dir = _world_dir_for_missing(server_dir, dimension)
    region_dir = world_dir / DIMENSIONS[dimension]["region_path"]
    return {
        "dimension": dimension,
        "label": DIMENSIONS[dimension]["label"],
        "world_name": world_dir.name,
        "configured_world_name": _level_name(server_dir),
        "world_path": str(world_dir),
        "region_path": str(region_dir),
        "available": False,
        "dimensions": list_dimensions(server_dir, candidates),
        "worlds": _world_summary(server_dir, candidates),
        "chunks": [],
        "chunk_count": 0,
        "region_count": 0,
        "region_files_found": 0,
        "unreadable_files": 0,
        "invalid_files": 0,
        "bounds": _empty_bounds(),
        "note": _map_note(region_dir, 0, 0, 0, 0, bool(candidates)),
    }


def _world_summary(server_dir: Path, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for candidate in candidates:
        summary.append({
            "world_name": candidate["world_dir"].name,
            "dimension": candidate["dimension"],
            "label": DIMENSIONS[candidate["dimension"]]["label"],
            "relative_region_path": candidate["relative_region_path"],
            "region_files_found": len(candidate["region_files"]),
        })
    return sorted(summary, key=lambda item: (item["world_name"].lower(), item["dimension"]))


def list_dimensions(server_dir: Path, candidates: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    discovered = candidates if candidates is not None else _discover_region_candidates(server_dir)
    dimensions = []
    for dimension_id, details in DIMENSIONS.items():
        matches = [candidate for candidate in discovered if candidate["dimension"] == dimension_id]
        dimensions.append({
            "id": dimension_id,
            "label": details["label"],
            "available": bool(matches),
            "region_files_found": sum(len(candidate["region_files"]) for candidate in matches),
        })
    return dimensions


def scan_dimension(server_dir: Path, dimension: str = "overworld") -> dict[str, Any]:
    if dimension not in DIMENSIONS:
        raise ValueError("Unknown world dimension")

    server_dir = server_dir.resolve()
    configured_world_name = _level_name(server_dir)
    candidates = _discover_region_candidates(server_dir)
    matching = [candidate for candidate in candidates if candidate["dimension"] == dimension]
    if not matching:
        return _empty_result(server_dir, dimension, candidates)

    selected = max(matching, key=lambda candidate: _candidate_score(candidate, configured_world_name))
    scan = _scan_region_files(selected["region_files"])
    region_dir = selected["region_dir"]
    return {
        "dimension": dimension,
        "label": DIMENSIONS[dimension]["label"],
        "world_name": selected["world_dir"].name,
        "configured_world_name": configured_world_name,
        "world_path": str(selected["world_dir"]),
        "region_path": str(region_dir),
        "relative_region_path": selected["relative_region_path"],
        "available": bool(scan["region_files_found"]),
        "dimensions": list_dimensions(server_dir, candidates),
        "worlds": _world_summary(server_dir, candidates),
        **scan,
        "note": _map_note(
            region_dir,
            int(scan["region_files_found"]),
            int(scan["chunk_count"]),
            int(scan["unreadable_files"]),
            int(scan["invalid_files"]),
            bool(candidates),
        ),
    }


def _map_note(
    region_dir: Path,
    region_files_found: int,
    chunk_count: int,
    unreadable_files: int,
    invalid_files: int,
    found_any_worlds: bool,
) -> str:
    if not found_any_worlds:
        return (
            "MineHost Helper did not find any vanilla .mca region files under this server folder. "
            "Start the server once, wait for spawn generation to finish, then refresh the map."
        )
    if not region_dir.exists():
        return (
            "No vanilla region folder was found for this dimension. Try another dimension tab, or start the server and let that dimension generate."
        )
    if region_files_found == 0:
        return (
            "The region folder exists, but no vanilla .mca region files were found for this dimension yet. "
            "Join the world or let spawn finish generating, then refresh the map."
        )
    if chunk_count == 0:
        details = []
        if unreadable_files:
            details.append(f"{unreadable_files} unreadable")
        if invalid_files:
            details.append(f"{invalid_files} too small or invalid")
        suffix = f" ({', '.join(details)} files)." if details else "."
        return (
            "Region files were found, but no saved chunk entries were detected in their headers"
            f"{suffix} Stop the server, make sure Minecraft saved the world, then refresh the map."
        )
    return "This map shows chunks saved by vanilla Minecraft. It is an explored-area overview, not a live terrain render."
