# Intent Map

A plain-language description of what a system must do, anchored to the
code that does it and the tests that prove it — and a small tool that
fails loudly when those anchors stop being true.

You should be able to ask "what does this system do?", get a page of
sentences a human wrote, and trust every sentence, because each one names
the function that implements it and the test that proves it, and something
checks that those still exist.

## The three documents

| file | what it is | who writes it |
|---|---|---|
| `docs/INTENT.md` | verbatim record of what was asked for, append-only, never edited | the human, quoted exactly |
| `docs/DESC.md` | the current minimal description: overview + numbered statements | derived from INTENT, rewritten whole |
| `map/intent-map.yaml` | each statement's anchors into code and tests | maintained with every code change |

`INTENT.md` is the authority. `DESC.md` has no memory — when the intent
grows, the description is rewritten rather than patched, because a
description that accumulates its own history stops being a description.
The identifiers (`R-1`, `R-2`, …) are stable across rewordings, so anchors
and discussion stay attached to the requirement, not to a sentence.

## Anchors are symbols, never line numbers

```yaml
- id: R-4
  statement: >
    Each requirement must be anchored to the code that implements it by
    file path plus function or class name.
  implementation:
    - intentmap/resolve.py::Anchor
    - intentmap/resolve.py::parse_anchor
  tests:
    - tests/test_resolve.py::TestParseAnchor
```

Line numbers change on every edit above them; a map keyed by line number
is stale by lunchtime. Symbols move rarely, and when one does, that is
exactly the moment a human should look. The tool computes current line
numbers on demand, and when an anchor breaks it searches git history to
tell you where the symbol went.

## Using it

```bash
python -m intentmap check      # every anchor still real? exit 1 if not
python -m intentmap show       # the description, with anchors resolved
python -m intentmap show R-7   # just one requirement
python -m intentmap where intentmap/resolve.py::resolve
python -m intentmap orphans    # claimed-but-unbuilt, built-but-unclaimed
python -m intentmap stats      # one-line coverage summary
```

`--root` points at any repository and `--map` at any map file, so the
tool can live in one place and check another. No third-party
dependencies: the map parser is hand-rolled precisely so adopting this
costs a folder and nothing else.

To make the map and the code move together, install the hook:

```bash
ln -s ../../hooks/pre-commit .git/hooks/pre-commit
```

A commit that breaks an anchor is then blocked until the map is updated
alongside the code — which is the entire discipline in one sentence.

## Adopting it in an existing project

1. Copy `intentmap/` and `hooks/pre-commit` into the repo (or point
   `--root` at the repo from here).
2. Write `docs/INTENT.md` by pasting what was actually asked for.
3. Distill `docs/DESC.md` from it: an overview sentence, then one
   sentence per behavior the system must have.
4. Write `map/intent-map.yaml`, anchoring each statement to the functions
   that implement it and the tests that prove it. Requirements with no
   test are listed as `UNPROVEN` rather than quietly omitted — an honest
   gap beats a false claim.
5. Run `python -m intentmap check` and install the hook.

Nothing has to be restructured: the map sits beside the code and names it
by path.

## Reading this project as the example

This repository maps itself. `docs/DESC.md` describes Intent Map, every
statement in it is anchored in `map/intent-map.yaml`, and
`tests/test_selfmap.py` fails if any anchor breaks or any requirement
lacks an implementation or a test. If the pattern cannot keep its own
house honest, it has no business asking anyone else to.

```bash
python3 -m unittest discover tests    # 76 tests
python3 -m intentmap check
```

## Status

Version 0.1.0 — a working pattern, deliberately small. The obvious next
steps: richer non-Python symbol resolution, an `intentmap init`
scaffolder, and a `--json` output mode for editor integrations.
