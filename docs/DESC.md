# DESC — Intent Map

Intent Map is a documentation pattern plus a small tool that keeps a
plain-language description of what a system must do, anchored to the exact
functions that do it and the tests that prove it.

This file is derived from `INTENT.md`. It is rewritten whole whenever the
intent grows — it has no memory of its own past versions, because the
conversation in `INTENT.md` and the history in git are the memory.

Every `R-` statement below is a requirement. Each one is anchored in
`map/intent-map.yaml` to the code that implements it and the tests that
prove it, and `intentmap check` fails if any anchor has gone stale.

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

## How it anchors to code

**R-4** — Each requirement must be anchored to the code that implements it
by file path plus function or class name — never by line number, because
line numbers change constantly and would rot the map on every edit.

**R-5** — Each requirement must be anchored to the tests that prove it, by
the same path-plus-name addressing, so a reader can see what evidence
exists for each claim.

**R-6** — A requirement that has no test must be marked as unproven rather
than silently listed, so the reader can tell verified claims from
asserted ones.

**R-7** — Anchors must be checkable: a tool must confirm every anchored
file exists and every anchored function or class is actually present in
it, and report anything stale.

**R-8** — Because anchors name symbols rather than lines, the tool must be
able to resolve any anchor to its current line number on demand, so a
human can jump straight to the code.

**R-9** — When a symbol has been renamed or moved, git history must be
used to find where it went and to report the last commit that touched it,
so a stale anchor can be repaired rather than merely reported broken.

## How it stays honest

**R-10** — The map must be machine-readable and human-editable, one entry
per requirement, kept in the repository next to the code it describes.

**R-11** — The tool must be able to report coverage: which requirements
have implementation anchors, which have test anchors, and which have
neither.

**R-12** — The tool must be able to find orphans in both directions:
requirements with no anchors, and source symbols that no requirement
claims — the second is how you notice code nobody asked for.

**R-13** — The check must be runnable as one command that exits non-zero
on failure, so it can run in CI or a pre-commit hook and block a change
that breaks the correspondence.

**R-14** — The tool must run standalone with no third-party dependencies,
so adopting the pattern costs a folder and nothing else.

**R-15** — The pattern must be adoptable by an existing repository without
restructuring it: the map lives beside the code and names it by path.

## How it is meant to be used

**R-16** — Updating the code and updating the map must be treated as one
action, not two, so the map cannot drift out of date between commits.

**R-17** — A human must be able to ask for the description at any time and
receive a report showing each requirement with its implementation, its
tests, and its verification status.

**R-18** — The pattern must remain useful as documentation on its own: the
description must read as prose a person can follow without running any
tool.
