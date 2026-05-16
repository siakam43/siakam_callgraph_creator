import fnmatch
import os


def parse_siakamignore(project_dir: str) -> list[str]:
    ignore_path = os.path.join(project_dir, ".siakamignore")
    if not os.path.isfile(ignore_path):
        return []

    patterns = []
    with open(ignore_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


def should_exclude(patterns: list[str], file_path: str) -> bool:
    excluded = False
    for pattern in patterns:
        if pattern.startswith("!"):
            negated = pattern[1:]
            if _match_pattern(negated, file_path):
                excluded = False
        else:
            if _match_pattern(pattern, file_path):
                excluded = True
    return excluded


def _match_pattern(pattern: str, path: str) -> bool:
    if "/" not in pattern.rstrip("/"):
        if fnmatch.fnmatch(os.path.basename(path), pattern):
            return True
        if fnmatch.fnmatch(path, pattern):
            return True
        if fnmatch.fnmatch(path, "*/" + pattern):
            return True
        if fnmatch.fnmatch(path, pattern + "/*"):
            return True
        return False
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern + "/*")
