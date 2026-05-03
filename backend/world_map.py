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


def _region_dir(server_dir: Path, dimension: str) -> Path:
    if dimension not in DIMENSIONS:
        raise ValueError("Unknown world dimension")
    return server_dir / _level_name(server_dir) / DIMENSIONS[dimension]["region_path"]


def list_dimensions(server_dir: Path) -> list[dict[str, Any]]:
    return [
        {
            "id": dimension_id,
            "label": details["label"],
            "available": _region_dir(server_dir, dimension_id).exists(),
        }
        for dimension_id, details in DIMENSIONS.items()
    ]


def scan_dimension(server_dir: Path, dimension: str = "overworld") -> dict[str, Any]:
    region_dir = _region_dir(server_dir, dimension)
    chunks: list[dict[str, int]] = []
    region_count = 0
    bounds: dict[str, int | None] = {"min_x": None, "max_x": None, "min_z": None, "max_z": None}

    if region_dir.exists():
        for path in sorted(region_dir.glob("r.*.*.mca")):
            match = REGION_RE.match(path.name)
            if not match:
                continue
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
        "world_name": _level_name(server_dir),
        "region_path": str(region_dir),
        "available": region_dir.exists(),
        "dimensions": list_dimensions(server_dir),
        "chunks": chunks,
        "chunk_count": len(chunks),
        "region_count": region_count,
        "bounds": bounds,
        "note": "This map shows chunks saved by vanilla Minecraft. It is an explored-area overview, not a live terrain render.",
    }
