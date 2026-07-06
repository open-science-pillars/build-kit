#!/usr/bin/env bash
# Open Science Pillars: development workspace bootstrap.
#
# Clones the org repos flat into a workspace directory and wires the session
# harness so `/osp-session` and `/osp-close` are available when you run Claude
# Code from that workspace. Idempotent: re-running updates clones and re-links.
#
# Usage:  ./bootstrap.sh [workspace-dir]   (default: ./osp-workspace)
set -euo pipefail

ORG="https://github.com/open-science-pillars"
WORKSPACE="${1:-$(pwd)/osp-workspace}"
# Repos a developer needs cloned to continue the build. Add domain repos as
# they are created (e.g. remote-sensing in Phase 3).
REPOS=(marketplace core ocean-science hydrology tutorials \
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

# Wire the harness as project skills so they load when Claude Code runs here.
mkdir -p "$WORKSPACE/.claude/skills"
for s in osp-session osp-close; do
  ln -sfn "$WORKSPACE/build-kit/harness/skills/$s" "$WORKSPACE/.claude/skills/$s"
  echo "  linked skill: $s"
done

# Seed the workspace law from the template if not already present.
if [ ! -f "$WORKSPACE/CLAUDE.md" ]; then
  cp "$WORKSPACE/build-kit/CLAUDE.template.md" "$WORKSPACE/CLAUDE.md"
  echo "  created CLAUDE.md from template (review the version pins before your first session)"
fi

cat <<EOF

Done. Next:
  cd "$WORKSPACE"
  claude
  > /osp-session <N>

Read build-kit/DEVELOPING.md first if this is your first session, and
marketplace/docs/phase2-preregistration.md before any Phase-3 domain work.
EOF
