---
name: osp-session
description: Start Open Science Pillars work by stable roadmap ID, with dependency, gate, ownership, and acceptance checks.
disable-model-invocation: true
---

# OSP Session Bootstrap

You are starting Open Science Pillars work `$ARGUMENTS`.

1. If `$ARGUMENTS` is a historical numeric session, use its archived block in
   `build-kit/build-record/IMPLEMENTATION-GUIDE.md` and `build-kit/build-record/PROGRESS.md`. State that
   this is compatibility mode and do not create new numbered sessions.
2. Otherwise run `uv run build-kit/scripts/roadmap.py brief $ARGUMENTS`. If the
   deliverable is blocked, declined, or has an incomplete dependency or gate,
   STOP.
3. Read the owning repository's `.osp/governance.yaml`, the linked issue when
   present, and the relevant specification. If the deliverable is proposed,
   starting it means: an issue in the owning repository naming the roadmap id,
   the status set to `active`, and the issue number recorded in the YAML (with
   human confirmation; never invent a number).
4. Restate in one screen: outcome, owning repository, acceptance criteria,
   dependencies, gate, contributor prerequisites, and verification plan. Wait
   for confirmation before changing files.
5. During the work, cite the specification's rules by name when
   authoring ("per the specification's report confirmation gate");
   when you and the spec disagree, flag it, do not improvise silently.
6. If a dataset peculiarity surfaces during testing, immediately draft
   the knowledge concept (correct type, frontmatter, links) and queue
   it for approval. This is the ingest loop; it is never deferred.
