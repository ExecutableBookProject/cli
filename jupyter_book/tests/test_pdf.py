"""Testing PDF functionality of the CLI."""

from pathlib import Path
from subprocess import run

path_tests = Path(__file__).parent


def test_html_pdf(tmpdir):
    path_output = Path(tmpdir).absolute()
    path_template = path_tests.parent.joinpath("book_template")
    cmd = f"jb build {path_template} --path-output {path_output} --build pdfhtml"
    run(cmd.split(), check=True)
    path_html = path_output.joinpath("_build", "html")
    path_pdf = path_output.joinpath("_build", "pdf")
    assert path_html.joinpath("index.html").exists()
    assert path_pdf.joinpath("book.pdf").exists()
