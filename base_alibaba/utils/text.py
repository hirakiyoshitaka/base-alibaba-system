"""Text utility helpers."""

import re


def sanitize_dirname(name: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', '_', name).strip()
