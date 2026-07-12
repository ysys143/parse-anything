#!/usr/bin/env bash
# Bootstrap the VM from CANONICAL sources (no scp of local files) and run the sweep.
#   parse-anything : official install.sh (curl|sh) -> self-contained bundle under ~/.local
#   harness + doc  : git clone of the repo (harness lives in $HARNESS_SUBDIR)
# Then: build the scanned stress PDF, run run_bench.py, and pull results back.
set -euo pipefail

PROJECT="${PROJECT:-ops-check}"
INSTANCE="${INSTANCE:-pa-ocr-l4}"
REPO_URL="${REPO_URL:-https://github.com/ysys143/parse-anything}"
REPO_BRANCH="${REPO_BRANCH:-feat/unlimited-wholedoc}"
HARNESS_SUBDIR="${HARNESS_SUBDIR:-benchmarks/ocr-sweep}"   # where the harness lives in the repo
INSTALL_URL="${INSTALL_URL:-https://raw.githubusercontent.com/ysys143/parse-anything/main/install.sh}"
ONLY="${ONLY:-}"                                            # optional: comma-separated model ids
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
REMOTE_RESULTS_DIR="${REMOTE_RESULTS_DIR:-results-$RUN_ID}"
RESULTS_LOCAL_ROOT="${RESULTS_LOCAL_ROOT:-./results-from-vm}"
RESULTS_LOCAL="${RESULTS_LOCAL:-$RESULTS_LOCAL_ROOT/$RUN_ID}"
SOURCE_MODE="${SOURCE_MODE:-git}"
FAIL_ON_LEAK="${FAIL_ON_LEAK:-0}"

case "$SOURCE_MODE" in
  git|local) ;;
  *) echo "[deploy] ERROR: SOURCE_MODE must be git or local" >&2; exit 2 ;;
esac

if [[ -z "${ZONE:-}" ]]; then
  ZONE="$(gcloud compute instances list --project="$PROJECT" --filter="name=($INSTANCE)" \
    --format='value(zone)' | head -n 1 | awk -F/ '{print $NF}')"
fi
[ -n "${ZONE:-}" ] || { echo "[deploy] ERROR: could not resolve zone for $INSTANCE" >&2; exit 1; }

ssh_do() { gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --command="$1"; }

echo "[deploy] run_id=$RUN_ID zone=$ZONE source_mode=$SOURCE_MODE results=~/$REMOTE_RESULTS_DIR"

echo "[deploy] 1/6 stage repo (harness + document.pdf + parse-anything SOURCE)"
if [[ "$SOURCE_MODE" == "local" ]]; then
  archive="/tmp/parse-anything-$RUN_ID.tgz"
  tar \
    --exclude='.git' --exclude='.venv' --exclude='.local' --exclude='.pytest_cache' \
    --exclude='.ruff_cache' --exclude='.env' --exclude='.debug-journal.md' \
    --exclude='worktree-*' --exclude='results-from-vm' \
    --exclude='benchmarks/**/results' --exclude='benchmarks/ocr-sweep/results' \
    --exclude='benchmarks/ocr-sweep/results-from-vm' \
    -czf "$archive" .
  ssh_do "rm -rf ~/pa-repo && mkdir -p ~/pa-repo"
  gcloud compute scp --project="$PROJECT" --zone="$ZONE" "$archive" "$INSTANCE:~/pa-repo/source.tgz"
  ssh_do "cd ~/pa-repo && tar -xzf source.tgz && rm source.tgz && ls $HARNESS_SUBDIR"
  rm -f "$archive"
else
  ssh_do "rm -rf ~/pa-repo && git clone --depth 1 --branch '$REPO_BRANCH' '$REPO_URL' ~/pa-repo && ls ~/pa-repo/$HARNESS_SUBDIR"
fi

# Source install (NOT the release bundle) so branch-only features (e.g. --whole-doc) are present. The
# DLVM ships system python3.10 but parse-anything needs >=3.11, so uv builds a 3.12 venv; ODL needs Java 17.
echo "[deploy] 2/6 install parse-anything FROM SOURCE (uv venv py3.12) + Java 17 for ODL"
ssh_do "set -e
  sudo apt-get update -q && sudo apt-get install -y -q openjdk-17-jre-headless
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\$HOME/.local/bin:\$PATH
  uv venv --python 3.12 ~/pa-repo/.venv
  uv pip install --python ~/pa-repo/.venv/bin/python -e ~/pa-repo
  mkdir -p ~/.local/bin && ln -sf ~/pa-repo/.venv/bin/parse-anything ~/.local/bin/parse-anything
  ~/.local/bin/parse-anything --help >/dev/null && echo parse-anything-source-OK"

echo "[deploy] 3/6 build the scanned stress PDF (image-only, no text layer)"
ssh_do "(command -v pip3 >/dev/null || sudo apt-get install -y -q python3-pip) && \
  python3 -m pip install -q pypdfium2 pillow && \
  cd ~/pa-repo && python3 $HARNESS_SUBDIR/make_scan_pdf.py --pdf document.pdf --out scan.pdf --dpi 150 --grayscale"

echo "[deploy] 4/6 run the sweep (one model at a time; docker pulls per-model vLLM images)"
ssh_do "cd ~/pa-repo && export PATH=\$HOME/.local/bin:\$PATH && \
  ~/pa-repo/.venv/bin/python $HARNESS_SUBDIR/run_bench.py --models-file $HARNESS_SUBDIR/models.json \
    --born document.pdf --scan scan.pdf --results ~/$REMOTE_RESULTS_DIR ${ONLY:+--only $ONLY}"

echo "[deploy] 5/6 render comparison report + adapter matrix"
matrix_flag=""
[[ "$FAIL_ON_LEAK" == "1" ]] && matrix_flag="--fail-on-leak"
set +e
ssh_do "cd ~/pa-repo && \
  ~/pa-repo/.venv/bin/python $HARNESS_SUBDIR/make_report.py --results ~/$REMOTE_RESULTS_DIR --out ~/$REMOTE_RESULTS_DIR/report.md && \
  ~/pa-repo/.venv/bin/python $HARNESS_SUBDIR/adapter_matrix.py --results ~/$REMOTE_RESULTS_DIR \
    --models-file $HARNESS_SUBDIR/models.json --out ~/$REMOTE_RESULTS_DIR/adapter_matrix.json $matrix_flag && \
  echo report-and-matrix-OK"
matrix_status=$?
set -e

echo "[deploy] 6/6 pull results back"
mkdir -p "$RESULTS_LOCAL"
gcloud compute scp --recurse --project="$PROJECT" --zone="$ZONE" "$INSTANCE:~/$REMOTE_RESULTS_DIR" "$RESULTS_LOCAL/"
echo "[deploy] DONE. Results in $RESULTS_LOCAL/$REMOTE_RESULTS_DIR/ (adapter_matrix.json + report.md). Run teardown.sh immediately."
exit "$matrix_status"
