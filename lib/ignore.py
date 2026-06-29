"""
Geode CLI — .geodeignore parser.

Same format as .gitignore. Supports:
  - Blank lines and comments (#)
  - Glob patterns (*, **, ?)
  - Negation patterns (!)
"""

import os
import fnmatch
from typing import List


IGNORE_FILE = ".geodeignore"


def load_patterns(root: str = ".") -> List[str]:
    path = os.path.join(root, IGNORE_FILE)
    if not os.path.exists(path):
        return []
    patterns = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


def should_ignore(filepath: str, patterns: List[str], root: str = ".") -> bool:
    rel = os.path.relpath(filepath, root)
    ignored = False
    for pattern in patterns:
        negate = pattern.startswith("!")
        p = pattern[1:] if negate else pattern

        if p.endswith("/"):
            p = p + "**"

        match = fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p)
        if not match:
            match = fnmatch.fnmatch(rel, p + "/**") or fnmatch.fnmatch(rel, p + "*")
        if not match and "/" in rel:
            match = fnmatch.fnmatch(rel, "**/" + p) or fnmatch.fnmatch(rel, "**/" + p + "/**")

        if match:
            ignored = not negate
    return ignored
