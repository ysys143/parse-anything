#!/usr/bin/env bash
# Delete the L4 VM so billing stops. Run this the moment the sweep + result fetch are done.
set -euo pipefail
PROJECT="${PROJECT:-ops-check}"
ZONE="${ZONE:-us-central1-a}"
INSTANCE="${INSTANCE:-pa-ocr-l4}"
echo "[teardown] deleting $INSTANCE ($ZONE) — this stops billing."
gcloud compute instances delete "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --quiet
echo "[teardown] deleted."
