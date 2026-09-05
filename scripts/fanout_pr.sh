#!/usr/bin/env bash
# fanout_pr.sh: the same change, as a pull request in every clone that
# carries it, from branch to merged main in one command.
#
# A cross-repository edit (a rule's wording, a gate step, a dependency
# floor) lands in several clones of the flat workspace bootstrap.sh
# makes. Done by hand, each clone costs the same eight steps and a wait
# on its gates, one after another. This script runs the cycle for every
# clone at once, in parallel: fast-forward main, branch, stage, commit
# with the DCO sign-off, push, open the pull request, watch the checks,
# merge, delete the branch, sync main. One line per repository at the
# end says where each landed; a failure stops that repository at the
# step that failed and leaves the others alone.
#
#   fanout_pr.sh --branch NAME --title TEXT --message PATH --body PATH \
#                [--no-merge] [--root DIR] [--dry-run] [REPO ...]
#   fanout_pr.sh --finish --branch NAME [--root DIR] [REPO ...]
#
#   REPO ...     clone directories under the workspace root; with none
#                given, every clone with uncommitted changes (or, with
#                --finish, every clone sitting on the branch)
#   --message    the commit message file, or a directory holding
#                REPO.txt per repository with default.txt as the
#                fallback; the message carries its own trailers, the
#                sign-off is added by commit -s
#   --body       the pull request body file, or a directory holding
#                REPO.md per repository with default.md as the fallback
#   --no-merge   stop once the pull request is open, for a review gate;
#                --finish later runs the watch, merge and sync
#   --root DIR   the workspace root, default the parent of this repo
#   --dry-run    list the repositories the run would touch and stop
#
# Needs gh authenticated for the organization and a git identity whose
# name and email match the DCO sign-off. Never force-pushes, never
# rewrites history, never touches a clone that is not on main.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
branch= title= message= body= merge=1 finish=0 dry=0
repos=()
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) branch="$2"; shift 2 ;;
    --title) title="$2"; shift 2 ;;
    --message) message="$2"; shift 2 ;;
    --body) body="$2"; shift 2 ;;
    --no-merge) merge=0; shift ;;
    --finish) finish=1; shift ;;
    --root) root="$(cd "$2" && pwd)"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -h|--help) sed -n '2,36p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --*) echo "unknown option $1" >&2; exit 2 ;;
    *) repos+=("$1"); shift ;;
  esac
done
[ -n "$branch" ] || { echo "--branch is required" >&2; exit 2; }
if [ "$finish" -eq 0 ]; then
  [ -n "$title" ] || { echo "--title is required" >&2; exit 2; }
  [ -e "$message" ] || { echo "--message must name a file or directory" >&2; exit 2; }
  [ -e "$body" ] || { echo "--body must name a file or directory" >&2; exit 2; }
  message="$(cd "$(dirname "$message")" && pwd)/$(basename "$message")"
  body="$(cd "$(dirname "$body")" && pwd)/$(basename "$body")"
fi

# The repositories: named, or discovered from the state of the clones.
if [ ${#repos[@]} -eq 0 ]; then
  for d in "$root"/*/; do
    d="${d%/}"; [ -d "$d/.git" ] || continue
    if [ "$finish" -eq 1 ]; then
      [ "$(git -C "$d" rev-parse --abbrev-ref HEAD)" = "$branch" ] && repos+=("$(basename "$d")")
    else
      [ -n "$(git -C "$d" status --porcelain)" ] && repos+=("$(basename "$d")")
    fi
  done
fi
[ ${#repos[@]} -gt 0 ] || { echo "no repositories to run on" >&2; exit 1; }
echo "fanout $branch: ${repos[*]}"
[ "$dry" -eq 1 ] && exit 0

# A per-repository file: PATH itself, or PATH/REPO.EXT, or PATH/default.EXT.
pick() {  # pick PATH REPO EXT
  if [ -d "$1" ]; then
    if [ -f "$1/$2.$3" ]; then echo "$1/$2.$3"; else echo "$1/default.$3"; fi
  else echo "$1"; fi
}

work="$(mktemp -d)"
one() {  # one REPO: the whole cycle for one clone, status to $work/REPO.status
  local repo="$1" dir="$root/$1" log="$work/$1.log" status="$work/$1.status" url= step=
  exec >"$log" 2>&1
  cd "$dir" || { echo "FAILED enter" >"$status"; return; }
  if [ "$finish" -eq 0 ]; then
    step=main
    [ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || { echo "not on main"; echo "FAILED $step" >"$status"; return; }
    step=fast-forward
    git fetch -q origin && git merge -q --ff-only origin/main || { echo "FAILED $step" >"$status"; return; }
    step=branch
    git checkout -q -b "$branch" || { echo "FAILED $step" >"$status"; return; }
    step=stage
    git add -A -- . ':(exclude)**/__pycache__/**' || { echo "FAILED $step" >"$status"; return; }
    step=commit
    git commit -q -s -F "$(pick "$message" "$repo" txt)" || { echo "FAILED $step" >"$status"; return; }
    step=push
    git push -q -u origin "$branch" || { echo "FAILED $step" >"$status"; return; }
    step=pull-request
    url="$(gh pr create --title "$title" --body-file "$(pick "$body" "$repo" md)")" || { echo "FAILED $step" >"$status"; return; }
    echo "$url"
    [ "$merge" -eq 1 ] || { echo "OPEN $url" >"$status"; return; }
  else
    step=find
    url="$(gh pr view "$branch" --json url --jq .url)" || { echo "FAILED $step" >"$status"; return; }
  fi
  # The gates: watch until every check reports; a repository with no
  # checks at all is not a failure, it has nothing to wait for.
  step=checks
  local out
  out="$(gh pr checks "$url" --watch --fail-fast 2>&1)"; local rc=$?
  echo "$out"
  if [ $rc -ne 0 ] && ! grep -q "no checks reported" <<<"$out"; then echo "FAILED $step $url" >"$status"; return; fi
  step=merge
  local n=0
  until gh pr merge "$url" --merge --delete-branch; do
    n=$((n + 1)); [ $n -lt 6 ] || { echo "FAILED $step $url" >"$status"; return; }
    sleep 10
  done
  step=sync
  git checkout -q main && git pull -q --ff-only || { echo "FAILED $step $url" >"$status"; return; }
  git branch -q -D "$branch" 2>/dev/null || true
  echo "MERGED $url" >"$status"
}

for repo in "${repos[@]}"; do one "$repo" & done
wait
echo
fail=0
for repo in "${repos[@]}"; do
  s="$(cat "$work/$repo.status" 2>/dev/null || echo "FAILED unknown")"
  printf '%-24s %s\n' "$repo" "$s"
  case "$s" in FAILED*) fail=1; echo "  --- $work/$repo.log"; tail -n 8 "$work/$repo.log" | sed 's/^/  | /' ;; esac
done
echo "logs: $work"
exit "$fail"
