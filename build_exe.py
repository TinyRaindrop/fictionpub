"""
Nuitka build script.
Compiles 2 separate executables for GUI and CLI.
"""

import pathlib
import re
import subprocess
import sys

from setuptools_scm import get_version

ROOT = pathlib.Path(__file__).parent


def get_version_tuple() -> tuple[int, ...]:
    """Get sanitized version tuple for Windows exe metadata."""
    raw = get_version(
        root=ROOT,
        version_scheme="post-release",
        local_scheme="no-local-version",
        write_to="fictionpub/_version.py",
    )
    print("Raw version:", raw)
    numbers = [int(x) for x in re.findall(r"\d+", raw)]
    while len(numbers) < 4:
        numbers.append(0)
    t: tuple[int, ...] = tuple(numbers[:4])
    print("Windows version tuple:", t)
    return t


VERSION = ".".join(map(str, get_version_tuple()))


build_options = [
    # ---- Metadata
    "--product-name=FictionPub",
    "--company-name=TinyRaindrop",
    "--file-description=FB2 to EPUB converter",
    f"--file-version={VERSION}",
    f"--product-version={VERSION}",
    # ---- Output
    "--onefile",  # Single .exe
    "--standalone",
    "--output-dir=./dist/",
    # ---- Compilation
    "--lto=yes",
    "--static-libpython=auto",
    "--follow-imports",
    # "--msvc=latest",  # Requires Windows SDK
    "--mingw64",
    # ---- Size reduction
    "--python-flag=no_docstrings",
    "--nofollow-import-to=importlib.metadata",  # exclude csv
    # ---- Resources
    "--assume-yes-for-downloads",
    "--include-package=fictionpub.resources",
    "--include-data-dir=fictionpub/resources=fictionpub/resources",
]

PLUGIN_EXCLUDES = [
    # Pillow - unused image formats
    "PIL.BlpImagePlugin",
    "PIL.BufrStubImagePlugin",
    "PIL.CurImagePlugin",
    "PIL.DcxImagePlugin",
    "PIL.DdsImagePlugin",
    "PIL.EpsImagePlugin",
    "PIL.FliImagePlugin",
    "PIL.FpxImagePlugin",
    "PIL.FtexImagePlugin",
    "PIL.GbrImagePlugin",
    "PIL.GribStubImagePlugin",
    "PIL.Hdf5StubImagePlugin",
    "PIL.IcnsImagePlugin",
    "PIL.IcoImagePlugin",
    "PIL.ImImagePlugin",
    "PIL.ImtImagePlugin",
    "PIL.IptcImagePlugin",
    "PIL.Jpeg2KImagePlugin",
    "PIL.McIdasImagePlugin",
    "PIL.MicImagePlugin",
    "PIL.MpegImagePlugin",
    "PIL.MpoImagePlugin",
    "PIL.MspImagePlugin",
    "PIL.PalmImagePlugin",
    "PIL.PcdImagePlugin",
    "PIL.PcxImagePlugin",
    "PIL.PdfImagePlugin",
    "PIL.PdfParser",
    "PIL.PixarImagePlugin",
    "PIL.PpmImagePlugin",
    "PIL.PsdImagePlugin",
    "PIL.SgiImagePlugin",
    "PIL.SpiderImagePlugin",
    "PIL.SunImagePlugin",
    "PIL.TgaImagePlugin",
    "PIL.WmfImagePlugin",
    "PIL.XVThumbImagePlugin",
    "PIL.XbmImagePlugin",
    "PIL.XpmImagePlugin",
    # "PIL.WebpImagePlugin",   # WebP is not supported in FB2
    # "PIL.TiffImagePlugin",
    "PIL.ImageQt",
    "PIL.ImageShow",  # opens images in external viewer
    "PIL.ImageWin",  # Windows printing API
    "PIL.ImageCms",  # ICC color profiles
    "PIL.ImageFilter",
    "PIL.ImageEnhance",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    # lxml extras
    "lxml.html",  # we only use lxml.etree
    "lxml.objectify",
    # stdlib test/dev, setuptools
    "unittest",
    "doctest",
    "pdb",
    "difflib",
    "py_compile",
    "compileall",
    "setuptools",
    "pkg_resources",
    "distutils",
]

PLUGIN_EXCLUDES_CLI = [
    "tkinter",
    "tkinterdnd2",
    "PIL.ImageTk",
]

exclude_options = [f"--nofollow-import-to={module}" for module in PLUGIN_EXCLUDES]
exclude_options_cli = [f"--nofollow-import-to={module}" for module in PLUGIN_EXCLUDES_CLI]


def compile_cli() -> None:
    print("\n--- Building CLI Version ---")
    options = (
        build_options
        + exclude_options
        + exclude_options_cli
        + [
            "--output-filename=fictionpub_cli.exe",
            "--windows-icon-from-ico=fictionpub/resources/icons/app_cli.ico",
            "--windows-console-mode=force",  # Force console for CLI
            "run_app_cli.py",
        ]
    )
    subprocess.check_call([sys.executable, "-m", "nuitka", *options])


def compile_gui() -> None:
    print("\n--- Building GUI Version ---")
    options = (
        build_options
        + exclude_options
        + [
            "--output-filename=fictionpub.exe",
            "--windows-icon-from-ico=fictionpub/resources/icons/app.ico",
            "--windows-console-mode=disable",  # Hide console for GUI
            "--enable-plugin=tk-inter",
            "run_app_gui.py",
        ]
    )
    subprocess.check_call([sys.executable, "-m", "nuitka", *options])


if __name__ == "__main__":
    compile_gui()
    # compile_cli()
