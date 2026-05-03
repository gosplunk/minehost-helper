from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .properties_manager import read_properties

REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")

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


def _dimension_region_path(world_dir: Path, dimension: str) -> Path:
    if dimension not in DIMENSIONS:
        raise ValueError("Unknown world dimension")
    return world_dir / DIMENSIONS[dimension]["region_path"]


def _has_region_files(world_dir: Path, dimension: str) -> bool:
    region_dir = _dimension_region_path(world_dir, dimension)
    return region_dir.exists() and any(REGION_RE.match(path.name) for path in region_dir.glob("r.*.*.mca"))


def _candidate_world_dirs(server_dir: Path) -> list[Path]:
    configured = server_dir / _level_name(server_dir)
    candidates: list[Path] = [configured]
    for common in ("world", "World", "WORLD"):
        candidates.append(server_dir / common)
    try:
        for child in server_dir.iterdir():
            if child.is_dir() and any(_has_region_files(child, dimension) for dimension in DIMENSIONS):
                candidates.append(child)
    except OSError:
        pass

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve() if candidate.exists() else candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _world_dir(server_dir: Path, dimension: str) -> Path:
    candidates = _candidate_world_dirs(server_dir)
    for candidate in candidates:
        if _has_region_files(candidate, dimension):
            return candidate
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _region_dir(server_dir: Path, dimension: str) -> Path:
    return _dimension_region_path(_world_dir(server_dir, dimension), dimension)


def list_dimensions(server_dir: Path) -> list[dict[str, Any]]:
    world_dirs = _candidate_world_dirs(server_dir)
    return [
        {
            "id": dimension_id,
            "label": details["label"],
            "available": any(_has_region_files(world_dir, dimension_id) for world_dir in world_dirs),
        }
        for dimension_id, details in DIMENSIONS.items()
    ]


def scan_dimension(server_dir: Path, dimension: str = "overworld") -> dict[str, Any]:
    world_dir = _world_dir(server_dir, dimension)
    region_dir = _region_dir(server_dir, dimension)
    chunks: list[dict[str, int]] = []
    region_count = 0
    bounds: dict[str, int | None] = {"min_x": None, "max_x": None, "min_z": None, "max_z": None}

    region_files_found = 0
    if region_dir.exists():
        for path in sorted(region_dir.glob("r.*.*.mca")):
            match = REGION_RE.match(path.name)
            if not match:
                continue
            region_files_found += 1
            region_x = int(match.group(1))
            region_z = int(match.group(2))
            try:
                header = path.read_bytes()[:4096]
            except OSError:
                continue
            if len(header) < 4096:
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
        "dimension": dimension,
        "label": DIMENSIONS[dimension]["label"],
        "world_name": world_dir.name,
        "configured_world_name": _level_name(server_dir),
        "world_path": str(world_dir),
        "region_path": str(region_dir),
        "available": region_dir.exists() and region_files_found > 0,
        "dimensions": list_dimensions(server_dir),
        "chunks": chunks,
        "chunk_count": len(chunks),
        "region_count": region_count,
        "region_files_found": region_files_found,
        "bounds": bounds,
        "note": _map_note(region_dir, region_files_found, len(chunks)),
    }


def _map_note(region_dir: Path, region_files_found: int, chunk_count: int) -> str:
    if not region_dir.exists():
        return (
            "No vanilla region folder was found for this dimension. Start the server once, let the world finish generating, "
            "then refresh the map. If this is an imported server, check that level-name points at the folder containing region files."
        )
    if region_files_found == 0:
        return (
            "The world folder exists, but no vanilla .mca region files were found for this dimension yet. "
            "Join the world or let spawn finish generating, then refresh the map."
        )
    if chunk_count == 0:
        return (
            "Region files were found, but their chunk headers are empty. Stop the server, make sure Minecraft saved the world, "
            "then refresh the map."
        )
    return "This map shows chunks saved by vanilla Minecraft. It is an explored-area overview, not a live terrain render."
