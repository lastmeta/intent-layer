#!/usr/bin/env python3
"""
Capture intent automatically, so the record does not depend on anyone
remembering to keep it.

This is a Claude Code `UserPromptSubmit` hook: the harness feeds it JSON
on stdin for every prompt the human submits, and it appends that prompt
verbatim to `docs/INTENT.md` under a dated heading. Nothing is
summarized, reworded, or dropped -- INTENT is the authority precisely
because it is unedited.

Install (in the project whose intent you are capturing), in
`.claude/settings.json`:

    {
      "hooks": {
        "UserPromptSubmit": [
          {
            "hooks": [
              {
                "type": "command",
                "command": "python3 hooks/capture-intent.py"
              }
            ]
          }
        ]
      }
    }

Other harnesses: anything that can pipe the user's message to stdin works
--  `echo "$MESSAGE" | python3 hooks/capture-intent.py --plain`.

Design notes:
  - Appends only; never rewrites existing content.
  - Skips slash-commands and trivially short prompts, which are
    operating the tool rather than expressing intent. Override with
    --keep-all.
  - Exits 0 no matter what: a capture failure must never block the
    human's actual work.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

INTENT_HEADER = """# INTENT

Verbatim record of what the owner asked for. Never edited, never
summarized in place, only appended to. Everything else in this project is
derived from this file, and when a derived document disagrees with this
one, this one wins.
"""

MIN_CHARS = 40


def read_prompt(argv) -> str:
    """The submitted prompt, from harness JSON on stdin or plain text."""
    raw = sys.stdin.read()
    if '--plain' in argv:
        return raw.strip()
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return raw.strip()
    for key in ('prompt', 'user_prompt', 'message', 'text', 'content'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def is_intent(prompt: str, keep_all: bool) -> bool:
    """Filter out tool-operating chatter; keep anything that says something."""
    if keep_all:
        return bool(prompt)
    if not prompt or prompt.startswith('/'):
        return False
    return len(prompt) >= MIN_CHARS


def append(prompt: str, path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(INTENT_HEADER)

    text = path.read_text()
    heading = f"## {date.today().isoformat()}"
    parts = ["\n"]
    if heading not in text:
        parts.append(f"---\n\n{heading}\n\n")
    # Blockquote every line so multi-paragraph prompts stay verbatim
    parts.append("\n".join(f"> {line}" if line.strip() else ">"
                           for line in prompt.splitlines()))
    parts.append("\n")

    with path.open('a') as f:
        f.write("".join(parts))


def main(argv) -> int:
    try:
        target = Path(os.environ.get('INTENT_FILE', 'docs/INTENT.md'))
        prompt = read_prompt(argv)
        if is_intent(prompt, '--keep-all' in argv):
            append(prompt, target)
    except Exception as e:  # never block the human's work
        print(f"capture-intent: skipped ({e})", file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
