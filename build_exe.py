"""
Nuitka build script.
Compiles 2 separate executables for GUI and CLI.
"""
import pathlib
import re
import subprocess
import sys

from setuptools_scm import get_version


def get_version_tuple():
    """Get sanitized version tuple for Windows exe metadata."""
    root = pathlib.Path(__file__).parent
    
    raw_version = get_version(root=root, version_scheme="post-release", local_scheme="no-local-version")
    print("Raw version:", raw_version)

    # Extract numeric parts only
    numbers = [int(x) for x in re.findall(r"\d+", raw_version)]
    while len(numbers) < 4:
        numbers.append(0)
    version_tuple = tuple(numbers[:4])

    print("Windows version tuple:", version_tuple)
    return version_tuple

# Dot-separated 4-digit version number
VERSION = ".".join(map(str, get_version_tuple()))

build_options = [
    "--product-name=FictionPub",
    "--company-name=TinyRaindrop",
    "--file-description=FB2 to EPUB converter",
    f"--file-version={VERSION}",
    f"--product-version={VERSION}",
    "--onefile",    # Single .exe
    "--standalone",
    "--output-dir=./dist/",
    "--lto=yes",
    "--static-libpython=auto",
    "--follow-imports",
    "--assume-yes-for-downloads",
    "--include-package=fictionpub.resources",
    "--include-data-dir=fictionpub/resources=fictionpub/resources",
    "--msvc=latest",    # Requires Windows SDK
    # "--mingw64",
]

PLUGIN_EXCLUDES = [
    # "PIL.BmpImagePlugin",
    "PIL.DdsImagePlugin",
    "PIL.PcxImagePlugin",
    "PIL.PpmImagePlugin",
    "PIL.GifImagePlugin",
    "PIL.PsdImagePlugin",
    "PIL.MpoImagePlugin",
    "PIL.PdfImagePlugin",
    "PIL.PdfParser",
    "PIL.SpiderImagePlugin",
    "PIL.PalmImagePlugin",
    "PIL.Hdf5StubImagePlugin",
    "PIL.EpsImagePlugin",
    "PIL.WebpImagePlugin",
    "PIL.ImageFilter",
    "PIL.ImageEnhance",
    "PIL.ImageOps",
    "PIL.ImageDraw",
    "PIL.ImageFont",
]

PLUGIN_EXCLUDES_CLI = [
    "tkinter",
    "tkinterdnd2",
]

exclude_options = [f"--nofollow-import-to={module}" for module in PLUGIN_EXCLUDES]

# TODO: Remove tkinter and PIL from CLI build
# Breaks loader.py which does `from PIL import Image, ImageTk` at top level
# exclude_options_cli = [f"--nofollow-import-to={module}" for module in PLUGIN_EXCLUDES_CLI]

def compile_cli():
    print("\n--- Building CLI Version ---")
    options = build_options + exclude_options + [
        "--output-filename=fictionpub_cli.exe",
        "--windows-icon-from-ico=fictionpub/resources/icons/app_cli.ico",
        "--windows-console-mode=force",     # Force console for CLI
        "--enable-plugin=tk-inter",         # TODO: remove
        "run_app_cli.py"
    ]
    subprocess.check_call([sys.executable, "-m", "nuitka"] + options)

def compile_gui():
    print("\n--- Building GUI Version ---")
    options = build_options + exclude_options + [
        "--output-filename=fictionpub.exe",
        "--windows-icon-from-ico=fictionpub/resources/icons/app.ico",
        "--windows-console-mode=disable",   # Hide console for GUI
        "--enable-plugin=tk-inter",
        "run_app_gui.py"
    ]
    subprocess.check_call([sys.executable, "-m", "nuitka"] + options)

if __name__ == "__main__":
    compile_gui()
    compile_cli()