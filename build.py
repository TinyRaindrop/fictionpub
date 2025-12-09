"""
Nuitka build script.
Compiles 2 separate executables for GUI and CLI.
"""
import subprocess
import sys


build_options = [
    "--product-name=FictionPub",
    "--company-name=TinyRaindrop",
    "--file-description=FB2 to EPUB converter",
    "--file-version=1.0.0",
    "--product-version=1.0.0",
    "--onefile",    # Single .exe
    "--standalone",
    "--output-dir=./dist/",
    "--lto=yes",
    "--assume-yes-for-downloads",
    "--enable-plugin=tk-inter",
    "--include-package=fictionpub.resources",
    "--include-data-dir=fictionpub/resources=fictionpub/resources",
    "--windows-icon-from-ico=fictionpub/resources/icons/app.ico",
    "--static-libpython=auto",
    "--follow-imports",
]

def compile_cli():
    print("--- Building CLI Version ---")
    options = build_options + [
        "--output-filename=fictionpub_cli.exe",
        "--windows-console-mode=force",     # Force console for CLI
        "run_app_cli.py"
    ]
    subprocess.check_call([sys.executable, "-m", "nuitka"] + options)

def compile_gui():
    print("--- Building GUI Version ---")
    options = build_options + [
        "--output-filename=fictionpub.exe",
        "--windows-console-mode=disable",   # Hide console for GUI
        "run_app.py"
    ]
    subprocess.check_call([sys.executable, "-m", "nuitka"] + options)

if __name__ == "__main__":
    # compile_cli()
    compile_gui()