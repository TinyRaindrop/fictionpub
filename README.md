# FictionPub
FB2 to EPUB3 ebook converter with CLI / GUI.

## Features:
* Fast batch processing of multiple files/folders.
* Resulting EPUB retains original FB2 structure, content and metadata.
* Table of Contents generation.
* Support for EPUB2 readers via NCX/guide generation.
* EPUB3 semantics for footnotes (allows readers to embed them on a page or in popups).
* Valid XHTML, proper tags are used. No more `<div class="calibre19">` for everything.
* Built-in default CSS. Support for custom CSS.

*Future*
* Pass epubcheck.
* Gracefully handle uncommon FB2 structures.
* Image optimization (jpeg resize, pngquant).
* Typographic improvements for better text flow.


## Installation

    pip install git+https://github.com/TinyRaindrop/fictionpub.git

or manually

    git clone https://github.com/TinyRaindrop/fictionpub
    cd fictionpub
    pip install .


## Development

Build package

    python -m pip install build
    python -m build
    pip install dist/fictionpub-*.whl

Prerequisites
- **MSVC** compiler (or switch to Mingw64 in build_exe.py)
- **Make** for makefile scripts (optional)
    
    `winget install GnuWin32.Make`

Install in editable mode with dev dependencies
    
    pip install -e .[dev]

**Compile .exe with Nuitka**

Use Python 3.12. TkInter isn't supported in 3.13, and 3.14 isn't supported by Nuitka at all.

    python build.py

or

    python -m nuitka --onefile --assume-yes-for-downloads run_app.py --output-filename=fictionpub.exe

**Compile .exe with Pyinstaller**

    pyinstaller fictionpub.spec


## Usage
### When installed as a Python package
Run GUI

    python fictionpub

Run CLI

    python fictionpub [input] [args]

**Input** can be file/folder path, or paths separated with spaces.
Run `fictionpub --help` to see the list of possible **arguments**.

### Using compiled .exe
Run GUI: `fictionpub.exe`

Run CLI: `fictionpub_cli.exe [input] [args]`


# Credits
Icons by Freepik - [Flaticon](www.flaticon.com)