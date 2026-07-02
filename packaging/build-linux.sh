#!/usr/bin/env bash
# Build the linux-x86_64 release bundle inside a manylinux_2_28 container (glibc 2.28 floor).
#
# Why a container: freezing on ubuntu-latest links against glibc 2.39, so the bundle fails to start on
# Debian 12 / Ubuntu 22.04 LTS / RHEL 9 (`GLIBC_2.38 not found`). manylinux_2_28 lowers the floor to
# glibc 2.28 (RHEL/Rocky 8+, Debian 10+, Ubuntu 18.04+, Amazon Linux 2023).
#
# The manylinux system CPython is static (Py_ENABLE_SHARED=0) and PyInstaller needs a shared libpython,
# so we fetch a pinned python-build-standalone interpreter (install_only => bundles libpython3.12.so).
# jlink needs jmods, which distro openjdk-devel packages may omit, so we use a Temurin JDK tarball.
#
# Invoked as: docker run -v "$PWD":/src:ro -v "$PWD/io":/io manylinux_2_28 bash /src/packaging/build-linux.sh <tag>
# Verified locally on debian:12 (glibc 2.36) and rockylinux:8 (glibc 2.28).
set -euxo pipefail

TAG="${1:-v0.0.0}"
PLATFORM="linux-x86_64"
SRC=/src
BUILD=/build
OUT=/io/out

echo "=== glibc floor ==="; ldd --version | head -1 || true

# 1. shared CPython 3.12 (install_only bundles libpython3.12.so.1.0 -> PyInstaller can bundle it).
# Pinned for reproducibility; baseline x86_64 (NOT v2/v3/v4) so the bundle runs on any x86_64 CPU.
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13%2B20260623-x86_64-unknown-linux-gnu-install_only.tar.gz"
echo "PBS_URL=$PBS_URL"
curl -fsSL "$PBS_URL" -o /tmp/py.tar.gz
mkdir -p /opt/py && tar -xzf /tmp/py.tar.gz -C /opt/py --strip-components=1
PY=/opt/py/bin/python3
"$PY" -c "import sysconfig; print('Py_ENABLE_SHARED =', sysconfig.get_config_var('Py_ENABLE_SHARED'))"

# 2. JDK 17 with jmods (Temurin) for jlink
curl -fsSL -o /tmp/jdk.tar.gz "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"
mkdir -p /opt/jdk && tar -xzf /tmp/jdk.tar.gz -C /opt/jdk --strip-components=1
export JAVA_HOME=/opt/jdk

# 3. stage only what `pip install .` needs (avoid copying .git/.venv/worktree from the mounted checkout)
mkdir -p "$BUILD"
for p in pyproject.toml README.md LICENSE LICENSE.txt src packaging; do
  [ -e "$SRC/$p" ] && cp -a "$SRC/$p" "$BUILD/"
done
cd "$BUILD"

# 4. install app + PyInstaller with the shared interpreter
"$PY" -m pip install --upgrade pip
"$PY" -m pip install . pyinstaller

# 5. trimmed JRE
"$JAVA_HOME/bin/jlink" --add-modules java.se,jdk.unsupported \
  --strip-debug --no-header-files --no-man-pages --compress=2 --output jre

# 6. freeze (same flags as the macOS/Windows build in release.yml)
"$PY" -m PyInstaller --noconfirm --onedir --name parse-anything \
  --collect-submodules parse_anything \
  --collect-data parse_anything \
  --collect-all pypdfium2 \
  --collect-all PIL \
  --collect-all numpy \
  --collect-data opendataloader_pdf \
  --collect-submodules opendataloader_pdf \
  --collect-data pdf_inspector \
  packaging/entry.py

# 7. assemble bundle (jre shipped next to the frozen exe)
name="parse-anything-${TAG}-${PLATFORM}"
cp -R jre "dist/parse-anything/jre"
mv "dist/parse-anything" "dist/${name}"
mkdir -p "$OUT"
tar -C dist -czf "$OUT/${name}.tar.gz" "${name}"
"$PY" -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" \
  "$OUT/${name}.tar.gz" > "$OUT/${name}.tar.gz.sha256"
ls -lh "$OUT"
echo "=== BUILD OK ==="
