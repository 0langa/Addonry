#!/usr/bin/env python3
"""Generate Claude/Kimi manual command from canonical Codex workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "create-chrome-extension" / "SKILL.md"
COMMAND = ROOT / "commands" / "create-chrome-extension.md"
HEADER = """---
description: Build, test, and install a personal Chrome extension end to end
argument-hint: <extension request>
---

Addonry manual activation. Treat following command arguments as user's extension request:

`$ARGUMENTS`

Execute canonical workflow below. Do not stop after explaining it.

"""


def render() -> str:
    source = SKILL.read_text(encoding="utf-8")
    parts = source.split("---", 2)
    if len(parts) != 3:
        raise ValueError("canonical skill frontmatter is malformed")
    body = parts[2].lstrip("\r\n")
    body = body.replace("(references/", "(../skills/create-chrome-extension/references/")
    return HEADER + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.write:
        COMMAND.parent.mkdir(parents=True, exist_ok=True)
        COMMAND.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Updated {COMMAND.relative_to(ROOT)}")
        return 0
    if not COMMAND.is_file() or COMMAND.read_text(encoding="utf-8") != expected:
        print("Manual command drift detected. Run scripts/sync_manual_command.py --write.")
        return 1
    print("Manual command matches canonical workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
