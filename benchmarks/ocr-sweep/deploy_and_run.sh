#!/usr/bin/env bash
# Bootstrap the VM from CANONICAL sources (no scp of local files) and run the sweep.
#   parse-anything : official install.sh (curl|sh) -> self-contained bundle under ~/.local
#   harness + doc  : git clone of the repo (harness lives in $HARNESS_SUBDIR)
# Then: build the scanned stress PDF, run run_bench.py, and pull results back.
set -euo pipefail

PROJECT="${PROJECT:-ops-check}"
ZONE="${ZONE:-us-central1-a}"
INSTANCE="${INSTANCE:-pa-ocr-l4}"
REPO_URL="${REPO_URL:-https://github.com/ysys143/parse-anything}"
REPO_BRANCH="${REPO_BRANCH:-main}"
HARNESS_SUBDIR="${HARNESS_SUBDIR:-benchmarks/ocr-sweep}"   # where the harness lives in the repo
INSTALL_URL="${INSTALL_URL:-https://raw.githubusercontent.com/ysys143/parse-anything/main/install.sh}"
ONLY="${ONLY:-}"                                            # optional: comma-separated model ids

ssh_do() { gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --command="$1"; }

echo "[deploy] 1/5 install parse-anything via official install.sh"
ssh_do "curl -fsSL '$INSTALL_URL' | sh && ~/.local/bin/parse-anything --help >/dev/null && echo parse-anything-OK"

echo "[deploy] 2/5 clone repo (harness + document.pdf) from canonical source"
ssh_do "rm -rf ~/pa-repo && git clone --depth 1 --branch '$REPO_BRANCH' '$REPO_URL' ~/pa-repo && ls ~/pa-repo/$HARNESS_SUBDIR"

echo "[deploy] 3/5 build the scanned stress PDF (image-only, no text layer)"
ssh_do "(command -v pip3 >/dev/null || sudo apt-get install -y -q python3-pip) && \
  python3 -m pip install -q pypdfium2 pillow && \
  cd ~/pa-repo && python3 $HARNESS_SUBDIR/make_scan_pdf.py --pdf document.pdf --out scan.pdf --dpi 150 --grayscale"

echo "[deploy] 4/5 run the sweep (one model at a time; docker pulls per-model vLLM images)"
ssh_do "cd ~/pa-repo && export PATH=\$HOME/.local/bin:\$PATH && \
  python3 $HARNESS_SUBDIR/run_bench.py --models-file $HARNESS_SUBDIR/models.json \
    --born document.pdf --scan scan.pdf --results ~/results ${ONLY:+--only $ONLY}"

echo "[deploy] 5/5 render comparison report + pull results back"
ssh_do "cd ~/pa-repo && python3 $HARNESS_SUBDIR/make_report.py --results ~/results --out ~/results/report.md && echo report-OK"
mkdir -p ./results-from-vm
gcloud compute scp --recurse --project="$PROJECT" --zone="$ZONE" "$INSTANCE:~/results" ./results-from-vm/
echo "[deploy] DONE. Results in ./results-from-vm/results/ (report.md at the top). Run teardown.sh to stop billing."
