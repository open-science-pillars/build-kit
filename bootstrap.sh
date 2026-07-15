#!/usr/bin/env bash
# Open Science Pillars: development workspace bootstrap.
#
# Clones the org repos flat into a workspace directory and wires the session
# harness for Claude Code and Codex. Idempotent: re-running updates clones and
# re-links.
#
# Usage:  ./bootstrap.sh [workspace-dir]   (default: ./osp-workspace)
set -euo pipefail

ORG="https://github.com/open-science-pillars"
WORKSPACE="${1:-$(pwd)/osp-workspace}"
# Repos a developer needs cloned to continue the build. Add domain repos as
# they are created (e.g. remote-sensing in Phase 3).
REPOS=(.github marketplace core ocean-science hydrology tutorials \
       plugin-template knowledge-template nasa-daac-knowledge evals build-kit)

echo "Workspace: $WORKSPACE"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

for r in "${REPOS[@]}"; do
  if [ -d "$r/.git" ]; then
    echo "  updating $r"; git -C "$r" pull --ff-only --quiet || echo "    (skip: $r not fast-forwardable)"
  else
    echo "  cloning $r"; git clone --quiet "$ORG/$r.git" "$r"
  fi
done

# Wire one canonical skill source into both supported coding agents.
mkdir -p "$WORKSPACE/.claude/skills" "$WORKSPACE/.agents/skills"
for s in osp-roadmap osp-session osp-close; do
  ln -sfn "$WORKSPACE/build-kit/harness/skills/$s" "$WORKSPACE/.claude/skills/$s"
  ln -sfn "$WORKSPACE/build-kit/harness/skills/$s" "$WORKSPACE/.agents/skills/$s"
  echo "  linked skill for Claude and Codex: $s"
done

# Seed the workspace law from the template if not already present.
if [ ! -f "$WORKSPACE/CLAUDE.md" ]; then
  # Import, do not copy: the workspace CLAUDE.md pulls in the single tracked
  # law via Claude Code's @-import, so it can never drift from the source.
  printf '# Open Science Pillars workspace\n\n@build-kit/CLAUDE.template.md\n' > "$WORKSPACE/CLAUDE.md"
  echo "  created CLAUDE.md importing build-kit/CLAUDE.template.md (single source, no drift)"
fi

cat <<EOF

Done. Next:
  cd "$WORKSPACE"
  claude
  > /osp-roadmap audit
  > /osp-session <roadmap-id>

Codex users can invoke \$osp-roadmap and \$osp-session from the same workspace.
Read build-kit/DEVELOPING.md first if this is your first session, and
marketplace/docs/phase2-preregistration.md before any Phase-3 domain work.
EOF
