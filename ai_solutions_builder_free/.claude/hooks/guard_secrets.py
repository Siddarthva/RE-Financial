"""PreToolUse hook: block Read/Grep/Bash access to secret files (.env, *token*, *credential*).

Exit 2 blocks the call and sends stderr back to Claude. Exit 0 allows it.
Matching is by file name only, case-insensitive; .env.example/.sample/.template are allowed.
"""
import fnmatch
import json
import os
import re
import sys

PATTERNS = (".env", ".env.*", "*token*", "*credential*")
SAFE_SUFFIXES = (".example", ".sample", ".template")


def is_secret(path):
    name = re.split(r"[\\/]", path.strip())[-1].lower()
    if not name or name.endswith(SAFE_SUFFIXES):
        return False
    return any(fnmatch.fnmatch(name, p) for p in PATTERNS)


def secret_words(command):
    """Path-like words in a shell command that name a secret file."""
    hits = []
    for word in re.split(r"""[\s'"`()=,;|&<>]+""", command):
        # A bare word like `token` in `grep token src` is a search term, not a file: require a path
        # separator or an extension. A literal `.env` always counts.
        pathlike = bool(re.search(r"[\\/]", word)) or bool(re.search(r"\w\.\w", word)) or word.lower().startswith(".env")
        if word and pathlike and is_secret(word):
            hits.append(word)
    return hits


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:  # fail closed: an unreadable event must not let a secret read through
        print("Blocked by project hook: could not parse the tool call.", file=sys.stderr)
        return 2
    tool, args = event.get("tool_name", ""), event.get("tool_input", {}) or {}
    if tool == "Bash":
        hits = secret_words(args.get("command", ""))
    else:  # Read, Grep, Glob
        hits = [p for p in (args.get("file_path"), args.get("path"), args.get("pattern")) if p and is_secret(str(p))]
    if hits:
        print(f"Blocked by project hook: {tool} touches a secret file ({', '.join(map(str, hits))}). "
              "CLAUDE.md forbids reading .env, token and credential files; ask the user instead.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
