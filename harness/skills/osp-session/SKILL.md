---
name: osp-session
description: Start an Open Science Pillars build session N. Loads the session plan from IMPLEMENTATION-GUIDE.md and current state from PROGRESS.md, and restates goals, steps, and checkpoint before any work.
disable-model-invocation: true
---

# OSP Session Bootstrap

You are starting build session $ARGUMENTS for Open Science Pillars.

1. Read marketplace/docs/IMPLEMENTATION-GUIDE.md and extract the
   full block for Session $ARGUMENTS (goal, time, steps, checkpoint).
2. Read marketplace/docs/PROGRESS.md. Report: items already green
   that this session depends on; anything red or yellow that blocks it.
   If a dependency is not green, STOP and say so.
3. Restate, in one screen: today's goal, the ordered steps, the
   checkpoint criteria, and this session's autonomy mode (read it from the
   session block header if stated there; otherwise, for historical sessions,
   from the BUILD-HARNESS autonomy table). Wait for confirmation before
   step one.
4. During the session: cite spec sections when authoring
   ("per SPEC §3.4"); when you and the spec disagree, flag it,
   do not improvise silently.
5. If a dataset peculiarity surfaces during testing, immediately draft
   the knowledge concept (correct type, frontmatter, links) and queue
   it for approval. This is the ingest loop; it is never deferred.
