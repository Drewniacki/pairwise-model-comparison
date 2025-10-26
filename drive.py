import json
from pathlib import Path, PurePosixPath
import re

# Load once — do this outside the function (not every call)
with open("drive_map.json", "r", encoding="utf-8") as f:
    DRIVE_MAP = json.load(f)

def get_public_link(local_path: str, prefix="/content/data/") -> str:
    """
    Convert a local file path into a shareable public link using drive_map.json
    """
    # Normalize path
    local_path = str(Path(local_path))

    # Remove prefix if present
    if local_path.startswith(prefix):
        relative = local_path[len(prefix):]
    else:
        # Also try removing full mounted path form if used
        relative = str(Path(local_path).relative_to(
            "/content/drive/MyDrive/dev/SPE/GeoHackathon 2025/data"
        ))

    # Look up relative path in our mapping
    entry = DRIVE_MAP.get(relative)
    if entry is None:
        raise KeyError(f"Path not found in drive_map.json: {relative}")

    return entry["share_link"]

def pretty_tree_from_path(
    path: str,
    root_prefix="/content/data/",
    skip_pattern=r"^Well-\d+-\d{8}T\d{6}Z-\d+(?:-\d+)?$",
) -> str:
    """
    Convert a full path into a pretty tree:
    - strips the fixed prefix (default: /content/data/)
    - skips the middle 'Well-<id>-<timestamp>Z-...' payload folder if present
    - keeps the human 'Well X' level
    - uses 1, 3, 5, ... hyphens for indentation
    """
    # Normalize separators and strip the prefix
    p = str(PurePosixPath(path))
    if p.startswith(root_prefix):
        p = p[len(root_prefix):]

    parts = [seg for seg in p.split("/") if seg]  # drop empty segments

    # If first segment matches skip pattern, drop it
    if parts and re.match(skip_pattern, parts[0]):
        parts = parts[1:]

    # Build lines with 1, 3, 5, ... hyphens
    lines = []
    for i, seg in enumerate(parts):
        hyphens = "-" * (2 * i + 1)
        lines.append(f"{hyphens} {seg}")

    return "\n".join(lines)

def markdown_tree_with_link(path: str, link: str, page=None) -> str:
    """
    Builds a markdown bullet-tree where only the *last* element is clickable.
    """
    # Convert to pretty parts again
    parts = pretty_tree_from_path(path).split("\n")
    parts = [p.strip("- ").strip() for p in parts]  # clean dash prefix
    
    lines = []
    for i, segment in enumerate(parts):
        indent = "  " * i  # 2 spaces per level
        
        if i == len(parts) - 1:
            # Last element → clickable link
            lines.append(f"{indent}- [{segment}]({link})")
        else:
            lines.append(f"{indent}- {segment}")
    
    if page is not None:
        indent = "  " * (i+1)
        lines.append(f"{indent}- page: {page}")

    return "\n".join(lines)

def format_document_link(metadata, prefix="/content/data/") -> str:

    local_path = metadata["source"]
    share_link = get_public_link(local_path)
    page = metadata['page'] if "page" in metadata else None
    
    if page:
        share_link += f"#page={page}"

    return markdown_tree_with_link(local_path, share_link, page)
