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

from ..sphinx import build_sphinx
from ..toc import build_toc
from ..pdf import html_to_pdf


@click.group()
def main():
    """Build and manage books with Jupyter."""
    pass


@main.command()
@click.argument("path-book")
@click.option("--path-output", default=None, help="Path to the output artifacts")
@click.option("--config", default=None, help="Path to the YAML configuration file")
@click.option("--toc", default=None, help="Path to the Table of Contents YAML file")
@click.option(
    "--build",
    default="html",
    help="What kind of output to build. Currently only 'html' is supported.",
)
def build(path_book, path_output, config, toc, build):
    """Convert a collection of Jupyter Notebooks into HTML suitable for a book.
    """
    # Paths for our notebooks
    PATH_BOOK = Path(path_book).absolute()

    book_config = {}
    build_dict = {
        "html": "html",
        "pdf_html": "singlehtml",
        "latex": "latex",
        "latexpdf": "latex",
    }
    if build not in build_dict.keys():
        raise ValueError(
            f"Value for --build must be one of {tuple(build_dict.keys())}. Got '{build}'"
        )
    builder = build_dict[build]

    # Table of contents
    if toc is None:
        if PATH_BOOK.joinpath("_toc.yml").exists():
            toc = PATH_BOOK.joinpath("_toc.yml")
        else:
            raise ValueError(
                f"Couldn't find a Table of Contents file. To auto-generate one, run\n\n\tjupyter-book build {path_book}"
            )
    book_config["globaltoc_path"] = str(toc)

    # Configuration file
    if config is None:
        if PATH_BOOK.joinpath("_config.yml").exists():
            config = PATH_BOOK.joinpath("_config.yml")

    if config is not None:
        book_config["yaml_config_path"] = str(config)

    # Builder-specific overrides
    if build == "pdf_html":
        book_config["html_theme_options"] = {"single_page": True}
    if build == "latexpdf":
        book_config["latex_engine"] = "xelatex"

    BUILD_PATH = path_output if path_output is not None else PATH_BOOK
    BUILD_PATH = Path(BUILD_PATH).joinpath("_build")
    if build in ["html", "pdf_html"]:
        OUTPUT_PATH = BUILD_PATH.joinpath("html")
    elif build in ["latex", "latexpdf"]:
        OUTPUT_PATH = BUILD_PATH.joinpath("latex")

    # Now call the Sphinx commands to build
    build_sphinx(
        PATH_BOOK,
        OUTPUT_PATH,
        noconfig=True,
        confoverrides=book_config,
        builder=builder,
    )

    # Builder-specific options
    if build == "pdf_html":
        print("Finished generating HTML for book...")
        print("Converting book HTML into PDF...")
        path_pdf_output = BUILD_PATH.joinpath("pdf")
        path_pdf_output.mkdir(exist_ok=True)
        path_pdf_output = path_pdf_output.joinpath("book.pdf")
        html_to_pdf(OUTPUT_PATH.joinpath("index.html"), path_pdf_output)
        path_pdf_output_rel = path_pdf_output.relative_to(Path(".").resolve())
        print(f"A PDF of your book can be found at: {path_pdf_output_rel}")
    elif build == "latexpdf":
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
    """Convert a single notebook page to HTML or PDF.
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


@main.command()
@click.argument("path-output")
def create(path_output):
    """Create a simple Jupyter Book that you can customize."""

    PATH_OUTPUT = Path(path_output)
    if PATH_OUTPUT.is_dir():
        raise ValueError(f"The output book already exists. Delete {path_output} first.")
    template_path = Path(__file__).parent.parent.joinpath("book_template")
    sh.copytree(template_path, PATH_OUTPUT)
    print(f"Your book template can be found at {PATH_OUTPUT}")


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
    print(f"Table of Contents written to {output_file}")
