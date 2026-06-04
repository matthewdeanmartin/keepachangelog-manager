#!/usr/bin/env python3
"""
Rewrite git history via git-filter-repo:
  1. Strip all Co-Authored-By / Co-authored-by trailers from commit messages.
  2. Rephrase every commit subject in keepachangelog style
     (Added / Changed / Fixed / Removed / …).

Run from the repo root:
    python scripts/rewrite_history.py

git-filter-repo must be on PATH.

IMPORTANT: git-filter-repo requires a "clean clone" — i.e. no remote named
'origin' (or you must pass --force).  See the note at the bottom of this
script for how to satisfy that requirement.
"""

import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# Commit-message map  (original subject  →  new full message)
# ---------------------------------------------------------------------------
# Rules:
#   Added:   new files, features, content
#   Changed: edits to existing files, restructuring, config tweaks
#   Fixed:   bug fixes, broken-build corrections
#   Removed: deletions
# ---------------------------------------------------------------------------

COMMIT_MAP: dict[str, str] = {
    # oldest → newest
    "Initial commit": "Added: initial project skeleton",
    # ETC
}

# ---------------------------------------------------------------------------
# Trailer-stripping regex
# ---------------------------------------------------------------------------
COAUTHOR_RE = re.compile(
    r"\n?^Co-[Aa]uthored?-[Bb]y:.*$",
    re.MULTILINE,
)


def build_callback_script() -> str:
    """Return a Python snippet suitable for git-filter-repo --commit-callback."""

    # Embed the map as a literal dict inside the callback string.
    map_lines = ["COMMIT_MAP = {\n"]
    for k, v in COMMIT_MAP.items():
        # repr() gives us safe Python string literals.
        map_lines.append(f"    {repr(k)}: {repr(v)},\n")
    map_lines.append("}\n")
    map_str = "".join(map_lines)

    callback = (
        "import re\n"
        "COAUTHOR_RE = re.compile(\n"
        r'    r"\n?^Co-[Aa]uthored?-[Bb]y:.*$",' "\n"
        "    re.MULTILINE,\n"
        ")\n"
        + map_str
        + """
original = commit.message.decode("utf-8", errors="replace")

# 1. Strip Co-Authored-By trailers
cleaned = COAUTHOR_RE.sub("", original)

# 2. Remap subject if it's in our map
subject_line = cleaned.split("\\n", 1)[0].strip()
if subject_line in COMMIT_MAP:
    rest = cleaned.split("\\n", 1)[1] if "\\n" in cleaned else ""
    # Use the canonical new message; if new message already has a body, keep it;
    # otherwise append any existing body that wasn't the co-author trailer.
    new_msg = COMMIT_MAP[subject_line]
    # If the new mapping already contains a body, use it as-is.
    if "\\n" not in new_msg:
        # No body in map — append whatever was left after stripping trailers.
        body_after_strip = rest.strip()
        if body_after_strip:
            new_msg = new_msg + "\\n\\n" + body_after_strip
    cleaned = new_msg

# 3. Ensure message ends with a single newline
cleaned = cleaned.rstrip() + "\\n"

commit.message = cleaned.encode("utf-8")
"""
    )
    return callback


def check_prerequisites() -> None:
    result = subprocess.run(
        ["git-filter-repo", "--version"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("ERROR: git-filter-repo not found on PATH.", file=sys.stderr)
        sys.exit(1)

    # Check for clean-clone requirement: git-filter-repo refuses to run when
    # a remote named 'origin' exists unless --force is passed.
    remotes = subprocess.run(
        ["git", "remote"], capture_output=True, text=True
    ).stdout.strip().splitlines()
    if "origin" in remotes:
        print(
            "\nWARNING: This repo has a remote named 'origin'.\n"
            "git-filter-repo requires either:\n"
            "  (a) a fresh clone with no remotes, OR\n"
            "  (b) the --force flag (which this script will add automatically).\n"
            "Proceeding with --force.\n"
        )
        return True  # signal caller to add --force
    return False


def main() -> None:
    needs_force = check_prerequisites()

    callback_code = build_callback_script()

    cmd = ["git-filter-repo", "--commit-callback", callback_code]
    if needs_force:
        cmd.append("--force")

    print("Running git-filter-repo …")
    print("Command:", " ".join(cmd[:3]), "<callback>", *cmd[3:])
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nERROR: git-filter-repo failed.", file=sys.stderr)
        sys.exit(result.returncode)

    print("\nDone. New history:")
    subprocess.run(["git", "log", "--oneline"])


if __name__ == "__main__":
    main()
