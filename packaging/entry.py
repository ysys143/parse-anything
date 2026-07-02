"""PyInstaller freeze entry point for the `parse-anything` bundle.

The release bundle ships a trimmed JRE next to the executable (``<exe dir>/jre``). The ODL structure
layer (opendataloader-pdf) shells out to ``java`` on PATH, so before the CLI runs we point PATH +
JAVA_HOME at the bundled JRE -- the resulting binary needs no system Python or Java.
"""
import os
import sys
from pathlib import Path


def _use_bundled_jre() -> None:
    if not getattr(sys, "frozen", False):   # only inside the PyInstaller bundle
        return
    jre = Path(sys.executable).resolve().parent / "jre"
    java_bin = jre / "bin"
    if java_bin.is_dir():
        os.environ["JAVA_HOME"] = str(jre)
        os.environ["PATH"] = str(java_bin) + os.pathsep + os.environ.get("PATH", "")


def main() -> int:
    _use_bundled_jre()
    from parse_anything.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
