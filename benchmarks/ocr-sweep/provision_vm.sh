#!/usr/bin/env bash
# Provision ONE on-demand L4 VM in the existing project for the OCR sweep.
# Idempotent-ish: fails loudly if the instance already exists (delete with teardown.sh first).
set -euo pipefail

PROJECT="${PROJECT:-ops-check}"
ZONE="${ZONE:-us-central1-a}"          # us-central1 has NVIDIA_L4 quota (=8) in this project
INSTANCE="${INSTANCE:-pa-ocr-l4}"
MACHINE="${MACHINE:-g2-standard-8}"    # L4 comes attached to g2 machine types
DISK_GB="${DISK_GB:-300}"              # 7 models (~10GB each) + 7 vLLM docker images
# Deep Learning VM: ships NVIDIA driver + Docker + nvidia-container-toolkit.
# common-cu129-ubuntu-2204-nvidia-580 = CUDA 12.9, driver 580 (covers all 7 models incl. torch2.10/cu128).
IMAGE_FAMILY="${IMAGE_FAMILY:-common-cu129-ubuntu-2204-nvidia-580}"
IMAGE_PROJECT="${IMAGE_PROJECT:-deeplearning-platform-release}"

echo "[provision] project=$PROJECT zone=$ZONE instance=$INSTANCE machine=$MACHINE + 1x L4 (on-demand)"

gcloud compute instances create "$INSTANCE" \
  --project="$PROJECT" --zone="$ZONE" \
  --machine-type="$MACHINE" \
  --accelerator="type=nvidia-l4,count=1" \
  --maintenance-policy=TERMINATE --restart-on-failure \
  --image-family="$IMAGE_FAMILY" --image-project="$IMAGE_PROJECT" \
  --boot-disk-size="${DISK_GB}GB" --boot-disk-type=pd-balanced \
  --metadata="install-nvidia-driver=True" \
  --scopes=storage-ro,logging-write,monitoring-write

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
  echo "[provision] READY: GPU + Docker + nvidia runtime confirmed."; exit 0
fi
echo "[provision] WARN: GPU-in-Docker check failed; inspect the instance manually." >&2
exit 1
