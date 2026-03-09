"""
utils/format_loader.py
Loads and validates grant format JSON files from the grant_formats/ directory.
Provides runtime validation and custom format registration.
"""

import json
import os
import glob
from typing import Optional

# Required top-level keys for a valid format record
REQUIRED_FORMAT_KEYS = {
    "format_id",
    "name",
    "funding_body",
    "domain_keywords",
    "emphasis",
    "sections"
}

# Required keys within each section object
REQUIRED_SECTION_KEYS = {"name", "required"}


class FormatValidationError(Exception):
    """Raised when a grant format JSON fails schema validation."""
    pass


def validate_format(fmt: dict) -> list[str]:
    """
    Validate a grant format dict against the schema.
    Returns a list of error strings (empty list = valid).
    """
    errors = []

    # Check top-level required keys
    missing = REQUIRED_FORMAT_KEYS - set(fmt.keys())
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")

    # Check format_id syntax
    fmt_id = fmt.get("format_id", "")
    if fmt_id:
        if " " in fmt_id or "/" in fmt_id or "\\" in fmt_id:
            errors.append("format_id must use underscores only, no spaces or slashes")
        if fmt_id != fmt_id.lower():
            errors.append("format_id must be lowercase")
        if fmt_id == "your_format_id_here":
            errors.append("format_id must be changed from the template default")

    # Check domain_keywords is a non-empty list
    keywords = fmt.get("domain_keywords", [])
    if not isinstance(keywords, list) or len(keywords) == 0:
        errors.append("domain_keywords must be a non-empty list of strings")

    # Check sections is a non-empty list with valid structure
    sections = fmt.get("sections", [])
    if not isinstance(sections, list) or len(sections) == 0:
        errors.append("sections must be a non-empty list")
    else:
        for i, section in enumerate(sections):
            missing_s = REQUIRED_SECTION_KEYS - set(section.keys())
            if missing_s:
                errors.append(f"Section {i} missing keys: {sorted(missing_s)}")
            if "max_words" not in section and "max_pages" not in section:
                errors.append(
                    f"Section '{section.get('name', i)}' must have max_words or max_pages (can be null)"
                )

    # Warn if instructions block was not removed
    if "_instructions" in fmt:
        errors.append(
            "Remove the '_instructions' block before uploading — it is for reference only"
        )

    return errors


def load_all_formats(formats_dir: Optional[str] = None) -> dict:
    """
    Load all grant format JSON files from the grant_formats/ directory.
    Returns a dict keyed by format_id.
    Skips files that fail validation (with a warning), never crashes.
    """
    if formats_dir is None:
        formats_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "grant_formats"
        )

    formats = {}
    pattern = os.path.join(formats_dir, "*.json")
    paths = sorted(glob.glob(pattern))

    if not paths:
        print(f"[FormatLoader] Warning: no format files found in {formats_dir}")
        return formats

    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                fmt = json.load(f)

            errors = validate_format(fmt)
            if errors:
                print(f"[FormatLoader] Skipping {os.path.basename(path)} — validation errors:")
                for err in errors:
                    print(f"  • {err}")
                continue

            fmt_id = fmt["format_id"]
            if fmt_id in formats:
                print(
                    f"[FormatLoader] Warning: duplicate format_id '{fmt_id}' in "
                    f"{os.path.basename(path)} — skipping (first loaded wins)"
                )
                continue

            formats[fmt_id] = fmt
            print(f"[FormatLoader] Loaded: {fmt_id} ({fmt['name']})")

        except json.JSONDecodeError as e:
            print(f"[FormatLoader] Skipping {os.path.basename(path)} — invalid JSON: {e}")
        except Exception as e:
            print(f"[FormatLoader] Skipping {os.path.basename(path)} — unexpected error: {e}")

    print(f"[FormatLoader] {len(formats)} format(s) loaded.")
    return formats


def register_custom_format(fmt_dict: dict, formats: dict) -> tuple[bool, list[str]]:
    """
    Validate and register a user-uploaded custom format into the in-memory formats dict.
    Returns (success: bool, errors: list[str]).
    The formats dict is mutated in place on success.
    """
    errors = validate_format(fmt_dict)
    if errors:
        return False, errors

    fmt_id = fmt_dict["format_id"]

    # Mark as custom so UI can indicate its origin
    fmt_dict["_custom"] = True

    formats[fmt_id] = fmt_dict
    return True, []


def format_summary_list(formats: dict) -> list[dict]:
    """
    Return a lightweight summary list for UI dropdowns and LLM matching prompts.
    Each entry: format_id, name, funding_body, emphasis blurb, domain_keywords, is_custom.
    Deliberately excludes full section specs to keep the matcher prompt compact.
    """
    return [
        {
            "format_id": fid,
            "name": fmt["name"],
            "funding_body": fmt["funding_body"],
            "typical_award_usd": fmt.get("typical_award_usd", "N/A"),
            "typical_duration_years": fmt.get("typical_duration_years", "N/A"),
            "emphasis_blurb": fmt.get("emphasis", "")[:200],   # truncate for prompt compactness
            "domain_keywords": fmt.get("domain_keywords", []),
            "rhetorical_tone": fmt.get("rhetorical_tone", ""),
            "is_custom": fmt.get("_custom", False),
        }
        for fid, fmt in formats.items()
    ]
