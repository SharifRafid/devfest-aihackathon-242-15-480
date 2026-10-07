#!/usr/bin/env bash
# Commit all changes and push to GitHub.
# Commit message = summary of changed files + the prompts (from PROMPT.md) entered since the last push.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
marker=".git/last_push_prompt_count"
branch="$(git rev-parse --abbrev-ref HEAD)"

git add -A
if git diff --cached --quiet; then
  echo "[push] nothing to commit"; git push -q origin "$branch" 2>/dev/null || true; exit 0
fi

# prompts since last push
last=0; [ -f "$marker" ] && last="$(cat "$marker")"
total=$(grep -c '^## \[' PROMPT.md 2>/dev/null || echo 0)
prompts=""
if [ "$total" -gt "$last" ]; then
  prompts="$(awk -v last="$last" '
    /^## \[/ { n++; if (n>last) { inblk=1; sub(/^## /,""); hdr=$0; next } else inblk=0 }
    inblk && NF { if (hdr!="") { printf "- (%s) ", hdr; hdr="" } else printf "  "; print }
  ' PROMPT.md)"
fi

# change summary
stat="$(git diff --cached --stat | tail -1 | sed 's/^ *//')"
files="$(git diff --cached --name-status | awk '{printf "%s %s\n", ($1=="A"?"added":($1=="D"?"deleted":($1~/^R/?"renamed":"modified"))), $NF}')"

# subject: first new prompt (truncated) or generic
first="$(printf '%s' "$prompts" | grep -m1 '^- (' | sed -E 's/^- \([^)]*\) //' | tr -d '\n' | cut -c1-60)"
subject="${first:-snapshot: $(date '+%H:%M')}"
[ ${#first} -ge 60 ] && subject="$subject..."

msg="$subject

Changes ($stat):
$files
"
if [ -n "$prompts" ]; then
  msg="$msg
Prompts used (from PROMPT.md):
$prompts
"
fi
msg="$msg
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

git commit -q -m "$msg"
echo "$total" > "$marker"
if git push -q origin "$branch"; then
  echo "[push] $(date '+%H:%M:%S') committed+pushed: $subject ($stat)"
else
  echo "[push] commit ok, push FAILED (network?). Will retry next run." >&2; exit 1
fi
