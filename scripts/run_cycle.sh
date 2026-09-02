#!/usr/bin/env bash
# One link in the chain.
#
# GitHub's scheduler proved unusable for this repo. On 27 August 2026 it fired
# zero of sixteen scheduled slots; the day before, three of ten, one to three
# hours apart rather than the twenty minutes configured. The workflow was
# active and every hand-triggered run succeeded, so this was GitHub dropping
# the schedule, not a misconfiguration.
#
# So the board no longer depends on that clock. Each run refreshes on a loop
# for a few hours and then asks GitHub to start the next run. The schedule
# trigger is left in place as a free restart if it ever starts behaving.
 
set -uo pipefail
 
MAX_RUN_SECONDS=${MAX_RUN_SECONDS:-14400}   # 4h, comfortably under the 6h job cap
SLOT_SECONDS=${SLOT_SECONDS:-1200}          # 20 minutes between refreshes
IDLE_SECONDS=${IDLE_SECONDS:-1800}          # how long to doze outside market hours
REPO="${GITHUB_REPOSITORY:-fiserhl/else-screen}"
START=$(date +%s)
 
# US regular session, with a little margin, in UTC. Covers 8:30-15:00 Central
# in both CST and CDT.
in_window() {
  local dow hhmm
  dow=$(date -u +%u)                        # 1=Mon .. 7=Sun
  # 10# forces base ten so 0830 is not read as octal. It has to live inside
  # $(( )): handed to [ as a string it is rejected as "not an integer", which
  # made every run since 27 August think the market was closed.
  hhmm=$(( 10#$(date -u +%H%M) ))
  [ "$dow" -ge 1 ] && [ "$dow" -le 5 ] || return 1
  [ "$hhmm" -ge 1320 ] && [ "$hhmm" -le 2110 ]
}
 
refresh() {
  if ! python3 scripts/fetch_quotes.py; then
    echo "fetch failed; keeping the previous quotes rather than blanking the board"
    return 0
  fi
  git add quotes.json
  if git diff --cached --quiet; then echo "no change"; return 0; fi
  git commit -m "quotes: $(date -u '+%Y-%m-%d %H:%M UTC')"
  git push || { git pull --rebase --autostash && git push; }
}
 
git config user.name  "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
 
while : ; do
  if in_window; then refresh; else echo "$(date -u '+%H:%M') UTC - outside market hours"; fi
  now=$(date +%s)
  elapsed=$(( now - START ))
  [ "$elapsed" -ge "$MAX_RUN_SECONDS" ] && break
  remaining=$(( MAX_RUN_SECONDS - elapsed ))
  if in_window; then nap=$SLOT_SECONDS; else nap=$IDLE_SECONDS; fi
  [ "$nap" -gt "$remaining" ] && nap=$remaining
  [ "$nap" -le 0 ] && break
  echo "sleeping ${nap}s"
  sleep "$nap"
done
 
# Hand off. Without a token this link is the last one, which is why the
# workflow keeps the (unreliable) schedule as a fallback restart.
if [ -z "${CHAIN_TOKEN:-}" ]; then
  echo "CHAIN_TOKEN is not set, so the chain stops here."
  echo "Add a repo secret named CHAIN_TOKEN with contents:write to keep it going."
  exit 0
fi
 
echo "handing off to the next run"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $CHAIN_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/dispatches" \
  -d '{"event_type":"refresh-quotes"}')
echo "handoff HTTP $code"
if [ "$code" != "204" ]; then
  echo "WARNING: handoff failed. The chain has stopped and needs a manual restart."
  exit 1
fi
