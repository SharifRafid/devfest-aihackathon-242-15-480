#!/usr/bin/env bash
# UserPromptSubmit hook: appends every prompt entered in Claude Code to PROMPT.md
# Reads hook JSON from stdin ({"prompt": "...", "cwd": "...", ...}).
set -u
input="$(cat)"
root="${CLAUDE_PROJECT_DIR:-$(printf '%s' "$input" | jq -r '.cwd // empty')}"
[ -z "$root" ] && root="$(pwd)"
file="$root/PROMPT.md"
prompt="$(printf '%s' "$input" | jq -r '.prompt // empty')"
[ -z "$prompt" ] && exit 0
# skip harness-generated turns (background task notifications, system notices) — only real human prompts are logged
case "$prompt" in \<task-notification\>*|*"[SYSTEM NOTIFICATION"*|\<system-reminder\>*|\<local-command*) exit 0 ;; esac
# skip slash commands that are just housekeeping
case "$prompt" in /push*|/autopush*|/clear*|/compact*|/effort*|/model*|/cost*|/help*) exit 0 ;; esac
[ -f "$file" ] || printf '# Prompt Log\n\nEvery prompt entered in Claude Code for this project, in order.\n' > "$file"
n=$(grep -c '^## \[' "$file" 2>/dev/null || true); n=$((n+1))
{
  printf '\n## [%s] Prompt #%d\n\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$n"
  printf '%s\n' "$prompt"
} >> "$file"
exit 0
