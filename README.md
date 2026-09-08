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
| `docs/INTENT.md` | verbatim record of what was asked for, append-only, never edited | captured automatically by a hook |
| `docs/DESC.md` | the current minimal description: overview + numbered statements | derived from INTENT, rewritten whole |
| `map/intent-map.yaml` | each statement's anchors, plus the prose explaining them | maintained with every code change |

`INTENT.md` is the authority. `DESC.md` has no memory — when the intent
grows, the description is rewritten rather than patched, because a
description that accumulates its own history stops being a description.
The identifiers (`R-1`, `R-2`, …) are stable across rewordings, so anchors
and discussion stay attached to the requirement, not to a sentence.

## What an entry looks like

```yaml
- id: R-8
  statement: >
    The tool must detect when pinned lines have changed since the commit
    they were pinned at, and flag exactly those requirements for review.
  how: >
    pin_drift runs `git log -L<start>,<end>:<file> <commit>..HEAD`, which
    follows that specific range through history rather than comparing raw
    line numbers. No commits means the lines are untouched.
  implementation:
    - intentmap/resolve.py::pin_drift@a0af2a5:229-255
    - intentmap/report.py::check@6360f45:51-74
  tests:
    - tests/test_resolve.py::TestPinDrift
  depends:
    - "R-7: there is nothing to detect drift against without a pin"
  gotchas: >
    Drift is flagged, never fatal. Changed lines mean "confirm the
    statement still holds", which is a judgment call, not an error.
```

**Anchors name symbols, not lines.** Line numbers change on every edit
above them; a map keyed by line number is stale by lunchtime. Symbols
move rarely, and when one does, that is exactly the moment a human should
look. Current line numbers are computed on demand, and a broken anchor
triggers a git-history search for where the symbol went.

**A pin is a historical fact.** `@a0af2a5:229-255` says "in commit
a0af2a5, these lines are what satisfied this requirement". That never
needs rewriting — the file can grow by a thousand lines above it and the
statement stays true. `intentmap pin path::symbol` writes one;
`intentmap drift` reports which pinned ranges have since been *edited*,
which is the only list of documents genuinely worth revisiting. Moving a
function down the file produces no drift; changing a line inside it does.

**The prose is the map's real content.** Because the map never copies
code, it has room to explain: `how` the anchored code produces the
behavior, what it `depends` on, and the `gotchas` a maintainer needs.
Expect to retune it continually — that explanation is what a person
actually reads.

## Using it

```bash
python -m intentmap check      # every anchor still real? exit 1 if not
python -m intentmap show       # the description, with prose and anchors
python -m intentmap show R-8   # just one requirement
python -m intentmap drift      # which pinned lines actually changed
python -m intentmap pin intentmap/resolve.py::resolve   # write/refresh a pin
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
alongside the code — which is the entire discipline in one sentence. Note
the division of labor: a **broken** anchor fails the check and blocks the
commit, while **drift** is only ever reported, because "these lines
changed, does the statement still hold?" is a judgment a human makes.

To capture intent automatically instead of remembering to, install
`hooks/capture-intent.py` as a `UserPromptSubmit` hook (see the docstring
in that file for the `.claude/settings.json` snippet). Every prompt is
appended to `docs/INTENT.md` verbatim, under a dated heading.

## Adopting it in an existing project

1. Copy `intentmap/` and `hooks/` into the repo (or point `--root` at the
   repo from here).
2. Write `docs/INTENT.md` by pasting what was actually asked for.
3. Distill `docs/DESC.md` from it: an overview sentence, then one
   sentence per behavior the system must have.
4. Write `map/intent-map.yaml`, anchoring each statement to the functions
   that implement it and the tests that prove it. Requirements with no
   test are listed as `UNPROVEN` rather than quietly omitted — an honest
   gap beats a false claim.
5. Run `python -m intentmap check` and install the hooks.

Nothing has to be restructured: the map sits beside the code and names it
by path. `--map` accepts a **directory** as well as a file, so a large
project can split the map into files that mirror its source tree —
`map/models/training.yaml` beside `src/models/training.py` — while a
small one keeps a single document. Ids stay unique across the whole map
either way.

## Reading this project as the example

This repository maps itself. `docs/DESC.md` describes Intent Map, every
statement in it is anchored in `map/intent-map.yaml`, and
`tests/test_selfmap.py` fails if any anchor breaks or any requirement
lacks an implementation or a test. If the pattern cannot keep its own
house honest, it has no business asking anyone else to.

```bash
python3 -m unittest discover tests    # 124 tests
python3 -m intentmap check
python3 -m intentmap drift
```

## Status

Version 0.2.0 — a working pattern, deliberately small. The obvious next
steps: richer non-Python symbol resolution, an `intentmap init`
scaffolder, a `--json` output mode for editor integrations, and a
`re-pin` command that refreshes drifted pins in the map file itself once
a human has confirmed the statements still hold.
