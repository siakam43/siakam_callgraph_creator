import hashlib


def compute_uid(file: str, func: str, line: int, expression: str) -> str:
    """Generate an 8-char hex uid from (file, func, line, expression)."""
    raw = f"{file}:{func}:{line}:{expression}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]
