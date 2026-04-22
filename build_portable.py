"""
LumaFlow portable package build script.
Builds a one-file executable and bundles it into a distributable zip archive.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from core.metadata import APP_METADATA


BASE_DIR = Path(__file__).resolve().parent
BUILD_DIR = BASE_DIR / "build"
DIST_DIR = BASE_DIR / "dist"
SPEC_PATH = BASE_DIR / "LumaFlow.spec"
README_PATH = DIST_DIR / "README.txt"
EXE_PATH = DIST_DIR / "LumaFlow.exe"
ZIP_PATH = BASE_DIR / f'LumaFlow_Portable_v{APP_METADATA["version"]}.zip'


def clean_build():
    """Remove previous build outputs."""
    for path in (BUILD_DIR, DIST_DIR):
        if path.exists():
            print(f"Cleaning {path}...")
            shutil.rmtree(path)


def build_exe():
    """Build the executable via the project spec file."""
    print("Building executable...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        str(SPEC_PATH),
    ]
    subprocess.run(cmd, check=True, cwd=BASE_DIR)


def create_readme():
    """Create the portable package README."""
    readme = f"""LumaFlow Portable

Usage:
1. Extract this archive to any folder.
2. Double-click LumaFlow.exe to run.

System requirements:
- Windows 10/11 64-bit
- VLC Media Player installed and available on PATH
- FFmpeg installed and available on PATH

Notes:
- First launch may take a few seconds.
- Some antivirus tools may raise false positives for one-file bundles.

Version: {APP_METADATA['version']}
Author: {APP_METADATA['author']}
"""
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text(readme, encoding="utf-8")


def create_zip():
    """Create the final portable archive."""
    print("Creating zip archive...")

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
        if EXE_PATH.exists():
            zipf.write(EXE_PATH, "LumaFlow.exe")
        if README_PATH.exists():
            zipf.write(README_PATH, "README.txt")

    print(f"Created archive: {ZIP_PATH.name}")
    print(f"Size: {ZIP_PATH.stat().st_size / 1024 / 1024:.1f} MB")


def main():
    print("LumaFlow portable build tool")
    print("=" * 50)

    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            check=True,
            capture_output=True,
            cwd=BASE_DIR,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: PyInstaller is not installed.")
        print("Please run: pip install pyinstaller")
        return 1

    clean_build()
    build_exe()
    create_readme()
    create_zip()

    print("\nBuild complete.")
    print(f"Output file: {ZIP_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
