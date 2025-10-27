import json
from pathlib import Path, PurePosixPath
import re

# --------------------------------------------------
# Global configuration
# --------------------------------------------------
PREFIX = "/content/data/data/"   # <--- change here if your mount changes

with open("drive_map.json", "r", encoding="utf-8") as f:
    DRIVE_MAP = json.load(f)


def get_public_link(local_path: str) -> str:
    """
    Convert a local file path into a shareable public link using DRIVE_MAP.
    Only responsibility: Normalize → Strip PREFIX → Lookup → Return link.
    """
    local_path = str(Path(local_path))

    # Remove prefix if present
    if local_path.startswith(PREFIX):
        relative = local_path[len(PREFIX):]
    else:
        # Try alternative mount variant (e.g. full Colab mount)
        alt_root = "/content/drive/MyDrive/dev/SPE/GeoHackathon 2025/data"
        relative = str(Path(local_path).relative_to(alt_root))

    entry = DRIVE_MAP.get(relative)
    if entry is None:
        raise KeyError(f"Path not found in drive_map.json: {relative}")

    return entry["share_link"]


def pretty_tree_from_path(
    path: str,
    skip_pattern=r"^Well-\d+-\d{8}T\d{6}Z-\d+(?:-\d+)?$",
) -> str:
    """
    Convert a full path into a pretty tree:
    - strips PREFIX
    - skips timestamp folder (Well-XYZ-<timestamp>-N)
    - prints hierarchy with staggered hyphen indentation
    """
    p = str(PurePosixPath(path))

    if p.startswith(PREFIX):
        p = p[len(PREFIX):]

    parts = [seg for seg in p.split("/") if seg]

    # Drop auto-generated "Well-###-timestamp" layer
    if parts and re.match(skip_pattern, parts[0]):
        parts = parts[1:]

    lines = []
    for i, seg in enumerate(parts):
        hyphens = "-" * (2 * i + 1)
        lines.append(f"{hyphens} {seg}")

    return "\n".join(lines)


def markdown_tree_with_link(path: str, link: str, page=None) -> str:
    """
    Builds a Markdown bullet-tree where only the final element is clickable.
    """
    parts = pretty_tree_from_path(path).split("\n")
    parts = [p.strip("- ").strip() for p in parts]

    lines = []
    for i, segment in enumerate(parts):
        indent = "  " * i

        if i == len(parts) - 1:  # final level
            lines.append(f"{indent}- [{segment}]({link})")
        else:
            lines.append(f"{indent}- {segment}")

    if page is not None:
        indent = "  " * (len(parts))
        lines.append(f"{indent}- page: {page}")

    return "\n".join(lines)


def format_document_link(metadata) -> str:
    """
    Entry point: Takes a metadata dict with:
      metadata["source"], metadata.get("page")
    Returns a Markdown tree with the final link clickable.
    """
    local_path = metadata["source"]
    share_link = get_public_link(local_path)

    page = metadata.get("page")
    if page:
        share_link += f"#page={page}"

    return markdown_tree_with_link(local_path, share_link, page)
