# DESC — Intent Map

Intent Map is a documentation pattern plus a small tool that keeps a
plain-language description of what a system must do, anchored to the exact
code that does it and the tests that prove it, and that flags the moment
those anchors stop being true.

This file is derived from `INTENT.md`. It is rewritten whole whenever the
intent grows — it has no memory of its own past versions, because the
conversation in `INTENT.md` and the history in git are the memory.

Every `R-` statement below is a requirement. Each one is anchored in
`map/intent-map.yaml`, and `intentmap check` fails if any anchor has gone
stale.

## What it is

**R-1** — The verbatim intent must be preserved unedited, append-only, in
`docs/INTENT.md`, and treated as the authority when any derived document
disagrees with it.

**R-2** — The description must be a single, current, minimal document in
human language: an overview plus a flat list of statements of how the
system must behave. It is regenerated whole rather than patched, and keeps
no record of its own past versions.

**R-3** — Each requirement must carry a stable identifier that survives
rewording, so anchors and history stay attached to the requirement rather
than to a sentence.

**R-4** — Capturing intent must be automatic rather than remembered: the
project must ship a hook that appends the conversation to the intent
folder, so the record stays complete without anyone choosing to keep it.

## How it anchors to code

**R-5** — Each requirement must be anchored to the code that implements it
by file path plus function or class name, and to the tests that prove it
by the same addressing, so a reader can see both what does the work and
what evidence exists for it.

**R-6** — A requirement that has no test must be marked as unproven rather
than silently listed, so the reader can tell verified claims from asserted
ones.

**R-7** — An anchor may additionally be pinned to a commit and the line
range that satisfied the requirement in that commit. A pin is a historical
fact that never needs rewriting: it stays true no matter how the file
moves around it, and only becomes worth revisiting when those particular
lines themselves change.

**R-8** — The tool must detect when pinned lines have changed since the
commit they were pinned at, and flag exactly those requirements for
review, so nobody is told to update documentation that no longer needs
updating.

**R-9** — Anchors must be checkable: the tool must confirm every anchored
file exists and every anchored function or class is present in it, and
report anything stale.

**R-10** — Because anchors name symbols rather than lines, the tool must
resolve any anchor to its current line number on demand, so a human can
jump straight to the code.

**R-11** — When a symbol has been renamed or moved, git history must be
used to find where it went and to report the last commit that touched it,
so a stale anchor can be repaired rather than merely reported broken.

## What the map carries

**R-12** — Because the map does not copy code, it must carry prose: a
human-level explanation of how the anchored code produces the described
behavior, what it depends on, and the gotchas worth knowing. That
explanation is the map's real content and is expected to be retuned
continually.

**R-13** — The map must be machine-readable and human-editable, one entry
per requirement, kept in the repository next to the code it describes.

**R-14** — The map must work either as one file or as many files organized
to mirror the code, so a small project can keep one document and a large
one can split the map along the same seams as its source.

## How it stays honest

**R-15** — The tool must report coverage: which requirements have
implementation anchors, which have test anchors, and which have neither.

**R-16** — The tool must find orphans in both directions: requirements
with no anchors, and source symbols that no requirement claims — the
second is how you notice code nobody asked for.

**R-17** — The check must be runnable as one command that exits non-zero
on failure, so it can run in CI or a pre-commit hook and block a change
that breaks the correspondence.

**R-18** — The tool must run standalone with no third-party dependencies,
so adopting the pattern costs a folder and nothing else.

**R-19** — The pattern must be adoptable by an existing repository without
restructuring it: the map lives beside the code and names it by path.

## How it is meant to be used

**R-20** — Updating the code and updating the map must be treated as one
action, not two, so the map cannot drift out of date between commits.

**R-21** — A human must be able to ask for the description at any time and
receive a report showing each requirement with its explanation, its
implementation, its tests, and its verification status.

**R-22** — The pattern must remain useful as documentation on its own: the
description must read as prose a person can follow without running any
tool.
