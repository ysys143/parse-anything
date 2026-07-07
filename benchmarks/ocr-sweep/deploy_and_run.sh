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

echo "[deploy] 1/5 clone repo (harness + document.pdf + parse-anything SOURCE) from branch $REPO_BRANCH"
ssh_do "rm -rf ~/pa-repo && git clone --depth 1 --branch '$REPO_BRANCH' '$REPO_URL' ~/pa-repo && ls ~/pa-repo/$HARNESS_SUBDIR"

# Source install (NOT the release bundle) so branch-only features (e.g. --whole-doc) are present. The
# DLVM ships system python3.10 but parse-anything needs >=3.11, so uv builds a 3.12 venv; ODL needs Java 17.
echo "[deploy] 2/5 install parse-anything FROM SOURCE (uv venv py3.12) + Java 17 for ODL"
ssh_do "set -e
  sudo apt-get update -q && sudo apt-get install -y -q openjdk-17-jre-headless
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\$HOME/.local/bin:\$PATH
  uv venv --python 3.12 ~/pa-repo/.venv
  uv pip install --python ~/pa-repo/.venv/bin/python -e ~/pa-repo
  mkdir -p ~/.local/bin && ln -sf ~/pa-repo/.venv/bin/parse-anything ~/.local/bin/parse-anything
  ~/.local/bin/parse-anything --help >/dev/null && echo parse-anything-source-OK"

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
