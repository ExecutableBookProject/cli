"""Defines the commands that the CLI will use."""
import sys
import os
import os.path as op
from pathlib import Path
import click
from glob import glob
import shutil as sh
import subprocess
from subprocess import run, PIPE
import asyncio
from sphinx.util.osutil import cd
import yaml

from ..sphinx import build_sphinx
from ..toc import build_toc
from ..pdf import html_to_pdf
from ..utils import _message_box, _error


@click.group()
def main():
    """Build and manage books with Jupyter."""
    pass


BUILD_OPTIONS = ["html", "pdf_html"]


@main.command()
@click.argument("path-book")
@click.option("--path-output", default=None, help="Path to the output artifacts")
@click.option("--config", default=None, help="Path to the YAML configuration file")
@click.option("--toc", default=None, help="Path to the Table of Contents YAML file")
@click.option("-W", "--warningiserror", is_flag=True, help="Error on warnings.")
@click.option(
    "--build",
    default="html",
    help="What kind of output to build. Must be one of {BUILD_OPTIONS}",
)
def build(path_book, path_output, config, toc, warningiserror, build):
    """Convert your book's content to HTML or a PDF."""
    # Paths for our notebooks
    PATH_BOOK = Path(path_book).absolute()
    if not PATH_BOOK.is_dir():
        _error(f"Path to book isn't a directory: {PATH_BOOK}")

    book_config = {}
    build_dict = {
        "html": "html",
        "pdfhtml": "singlehtml",
        "latex": "latex",
        "pdflatex": "latex",
    }
    if build not in build_dict.keys():
        allowed_keys = tuple(build_dict.keys())
        _error(f"Value for --build must be one of {allowed_keys}. Got '{build}'")
    builder = build_dict[build]

    # Table of contents
    if toc is None:
        if PATH_BOOK.joinpath("_toc.yml").exists():
            toc = PATH_BOOK.joinpath("_toc.yml")
        else:
            _error(
                f"Couldn't find a Table of Contents file. To auto-generate "
                "one, run\n\n\tjupyter-book toc {path_book}"
            )
    book_config["globaltoc_path"] = str(toc)

    # Configuration file
    if config is None:
        if PATH_BOOK.joinpath("_config.yml").exists():
            config = PATH_BOOK.joinpath("_config.yml")

    extra_extensions = None
    if config is not None:
        book_config["yaml_config_path"] = str(config)
        config_yaml = yaml.safe_load(config.read_text())

        # Pop the extra extensions since we need to append, not replace
        extra_extensions = config_yaml.pop("sphinx", {}).get("extra_extensions")

    # Builder-specific overrides
    if build == "pdfhtml":
        book_config["html_theme_options"] = {"single_page": True}

    BUILD_PATH = path_output if path_output is not None else PATH_BOOK
    BUILD_PATH = Path(BUILD_PATH).joinpath("_build")
    if build in ["html", "pdfhtml"]:
        OUTPUT_PATH = BUILD_PATH.joinpath("html")
    elif build in ["latex", "pdflatex"]:
        OUTPUT_PATH = BUILD_PATH.joinpath("latex")

    # Now call the Sphinx commands to build
    exc = build_sphinx(
        PATH_BOOK,
        OUTPUT_PATH,
        noconfig=True,
        confoverrides=book_config,
        builder=builder,
        warningiserror=warningiserror,
        extra_extensions=extra_extensions,
    )

    if exc:
        _error(
            "There was an error in building your book. "
            "Look above for the error message.",
        )
    else:
        # Builder-specific options
        if build == "html":
            path_output_rel = Path(op.relpath(OUTPUT_PATH, Path()))
            path_index = path_output_rel.joinpath("index.html")
            _message_box(
                f"""\
            Finished generating HTML for book.

            Your book's HTML pages are here:
                {path_output_rel}{os.sep}

            You can look at your book by opening this file in a browser:
                {path_index}\
            """
            )
        if build == "pdfhtml":
            print("Finished generating HTML for book...")
            print("Converting book HTML into PDF...")
            path_pdf_output = OUTPUT_PATH.parent.joinpath("pdf")
            path_pdf_output.mkdir(exist_ok=True)
            path_pdf_output = path_pdf_output.joinpath("book.pdf")
            html_to_pdf(OUTPUT_PATH.joinpath("index.html"), path_pdf_output)
            path_pdf_output_rel = Path(op.relpath(path_pdf_output, Path()))
            _message_box(
                f"""\
            Finished generating PDF via HTML for book. Your PDF is here:

                {path_pdf_output_rel}\
            """
            )
        elif build == "pdflatex":
            print("Finished generating latex for book...")
            print("Converting book latex into PDF...")
            # Convert to PDF via tex and template built Makefile and make.bat
            if sys.platform == 'win32':
                makecmd = os.environ.get('MAKE', 'make.bat')
            else:
                makecmd = os.environ.get('MAKE', 'make')
            try:
                with cd(OUTPUT_PATH):
                    out = subprocess.call([makecmd, 'all-pdf'])
                print(f"A PDF of your book can be found at: {OUTPUT_PATH}")
            except OSError:
                print('Error: Failed to run: %s' % makecmd)
                return 1


@main.command()
@click.argument("path-page")
@click.option("--path-output", default=None, help="Path to the output artifacts")
@click.option("--config", default=None, help="Path to the YAML configuration file")
@click.option("--execute", default=None, help="Whether to execute the notebook first")
def page(path_page, path_output, config, execute):
    """Convert a single content file to HTML or PDF.
    """
    # Paths for our notebooks
    PATH_PAGE = Path(path_page)
    PATH_PAGE_FOLDER = PATH_PAGE.parent.absolute()
    PAGE_NAME = PATH_PAGE.with_suffix("").name
    if config is None:
        config = ""
    if not execute:
        execute = "off"

    OUTPUT_PATH = path_output if path_output is not None else PATH_PAGE_FOLDER
    OUTPUT_PATH = Path(OUTPUT_PATH).joinpath("_build/html")

    # Find all files that *aren't* the page we're building and exclude them
    to_exclude = glob(str(PATH_PAGE_FOLDER.joinpath("**", "*")), recursive=True)
    to_exclude = [
        op.relpath(ifile, PATH_PAGE_FOLDER)
        for ifile in to_exclude
        if ifile != str(PATH_PAGE.absolute())
    ]
    to_exclude.extend(["_build", "Thumbs.db", ".DS_Store", "**.ipynb_checkpoints"])

    # Now call the Sphinx commands to build
    config = {
        "master_doc": PAGE_NAME,
        "yaml_config_path": config,
        "globaltoc_path": "",
        "exclude_patterns": to_exclude,
        "jupyter_execute_notebooks": execute,
        "html_theme_options": {"single_page": True},
    }

    build_sphinx(
        PATH_PAGE_FOLDER,
        OUTPUT_PATH,
        noconfig=True,
        confoverrides=config,
        builder="html",
    )

    path_output_rel = Path(op.relpath(OUTPUT_PATH, Path()))
    path_page = path_output_rel.joinpath(f"{PAGE_NAME}.html")
    _message_box(f"Page build finished. Open your page at:\n\n    {path_page}")


@main.command()
@click.argument("path-output")
def create(path_output):
    """Create a simple Jupyter Book that you can customize."""

    PATH_OUTPUT = Path(path_output)
    if PATH_OUTPUT.is_dir():
        _error(f"The output book already exists. Delete {PATH_OUTPUT}{os.sep} first.")
    template_path = Path(__file__).parent.parent.joinpath("book_template")
    sh.copytree(template_path, PATH_OUTPUT)
    _message_box(f"Your book template can be found at\n\n    {PATH_OUTPUT}{os.sep}")


@main.command()
@click.argument("path")
@click.option(
    "--filename_split_char",
    default="_",
    help="A character used to split file names for titles",
)
@click.option(
    "--skip_text",
    default=None,
    help="If this text is found in any files or folders, they will be skipped.",
)
@click.option(
    "--output-folder",
    default=None,
    help="A folder where the TOC will be written. Default is `path`",
)
def toc(path, filename_split_char, skip_text, output_folder):
    """Generate a _toc.yml file for your content folder (and sub-directories).
    The alpha-numeric name of valid conten files will be used to choose the
    order of pages/sections. If any file is called "index.{extension}", it will be
    chosen as the first file.
    """
    out_yaml = build_toc(path, filename_split_char, skip_text)
    if output_folder is None:
        output_folder = path
    output_file = Path(output_folder).joinpath("_toc.yml")
    output_file.write_text(out_yaml)

    _message_box(f"Table of Contents written to {output_file}")
