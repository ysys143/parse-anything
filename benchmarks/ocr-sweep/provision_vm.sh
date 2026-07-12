#!/usr/bin/env bash
# Provision ONE on-demand L4 VM in the existing project for the OCR sweep.
# Idempotent-ish: fails loudly if the instance already exists (delete with teardown.sh first).
set -euo pipefail

PROJECT="${PROJECT:-ops-check}"
ZONE="${ZONE:-}"
ZONE_CANDIDATES="${ZONE_CANDIDATES:-us-west1-a us-central1-a us-central1-b us-central1-c us-east1-b us-east1-c us-east1-d us-east4-a us-east4-b us-east4-c}"
INSTANCE="${INSTANCE:-pa-ocr-l4}"
MACHINE="${MACHINE:-g2-standard-8}"    # L4 comes attached to g2 machine types
DISK_GB="${DISK_GB:-300}"              # 7 models (~10GB each) + 7 vLLM docker images
# Deep Learning VM: ships NVIDIA driver + Docker + nvidia-container-toolkit.
# common-cu129-ubuntu-2204-nvidia-580 = CUDA 12.9, driver 580 (covers all 7 models incl. torch2.10/cu128).
IMAGE_FAMILY="${IMAGE_FAMILY:-common-cu129-ubuntu-2204-nvidia-580}"
IMAGE_PROJECT="${IMAGE_PROJECT:-deeplearning-platform-release}"

existing="$(gcloud compute instances list --project="$PROJECT" --filter="name=($INSTANCE)" --format='value(name,zone,status)' || true)"
if [[ -n "$existing" ]]; then
  echo "[provision] ERROR: instance name already exists: $existing" >&2
  exit 1
fi

if [[ -n "$ZONE" ]]; then
  candidates="$ZONE"
else
  candidates="$ZONE_CANDIDATES"
fi

selected_zone=""
for candidate in $candidates; do
  echo "[provision] trying project=$PROJECT zone=$candidate instance=$INSTANCE machine=$MACHINE + 1x L4 (on-demand)"
  if gcloud compute instances create "$INSTANCE" \
      --project="$PROJECT" --zone="$candidate" \
      --machine-type="$MACHINE" \
      --accelerator="type=nvidia-l4,count=1" \
      --maintenance-policy=TERMINATE --restart-on-failure \
      --image-family="$IMAGE_FAMILY" --image-project="$IMAGE_PROJECT" \
      --boot-disk-size="${DISK_GB}GB" --boot-disk-type=pd-balanced \
      --metadata="install-nvidia-driver=True" \
      --scopes=storage-ro,logging-write,monitoring-write; then
    selected_zone="$candidate"
    break
  fi
  echo "[provision] zone unavailable: $candidate"
done

[ -n "$selected_zone" ] || { echo "[provision] ERROR: no candidate zone created an L4 VM." >&2; exit 1; }
ZONE="$selected_zone"
echo "[provision] created in zone=$ZONE"

echo "[provision] created. Waiting for SSH + NVIDIA driver to settle..."
ready=0
for i in $(seq 1 40); do
  if gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --command="nvidia-smi -L" 2>/dev/null; then
    ready=1; break
  fi
  sleep 15
done
[ "$ready" = 1 ] || { echo "[provision] ERROR: GPU not reachable over SSH within timeout." >&2; exit 1; }

# This CUDA base image ships nvidia-container-toolkit (nvidia-ctk) but NOT Docker. Install Docker,
# wire in the nvidia runtime, and add the user to the docker group (applies on the next SSH session).
echo "[provision] installing Docker + nvidia runtime..."
gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --command="
  set -e
  if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sudo sh; fi
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
  sudo usermod -aG docker \$USER
"
# Verify GPU is visible INSIDE a container (the thing the sweep actually needs).
echo "[provision] verifying GPU-in-Docker..."
if gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" \
     --command="sudo docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L" 2>/dev/null; then
  echo "[provision] READY: GPU + Docker + nvidia runtime confirmed. export ZONE=$ZONE"; exit 0
fi
echo "[provision] WARN: GPU-in-Docker check failed; inspect the instance manually." >&2
exit 1
