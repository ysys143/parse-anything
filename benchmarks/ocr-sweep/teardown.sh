#!/usr/bin/env bash
# Delete the L4 VM so billing stops. Run this the moment the sweep + result fetch are done.
set -euo pipefail
PROJECT="${PROJECT:-ops-check}"
ZONE="${ZONE:-}"
INSTANCE="${INSTANCE:-pa-ocr-l4}"
if [[ -z "$ZONE" ]]; then
  ZONE="$(gcloud compute instances list --project="$PROJECT" --filter="name=($INSTANCE)" \
    --format='value(zone)' | head -n 1 | awk -F/ '{print $NF}')"
fi
if [[ -z "$ZONE" ]]; then
  echo "[teardown] $INSTANCE not found in project=$PROJECT."
  exit 0
fi
echo "[teardown] deleting $INSTANCE ($ZONE) — this stops billing."
gcloud compute instances delete "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --quiet
echo "[teardown] deleted."
