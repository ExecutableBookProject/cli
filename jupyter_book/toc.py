"""A small sphinx extension to use a global table of contents"""
import os
import yaml
from textwrap import dedent
from pathlib import Path
from sphinx import addnodes
from sphinx.util import docname_join
from docutils import nodes

from .utils import _filename_to_title, SUPPORTED_FILE_SUFFIXES


def _no_suffix(path):
    if isinstance(path, str):
        path = str(Path(path).with_suffix(""))
    return path


def find_name(pages, name):
    """
    Takes a dict with nested lists and dicts,
    and searches all dicts for a key of the field
    provided.
    """
    page = None
    if isinstance(pages, dict):
        pages = [pages]

    for page in pages:
        if _no_suffix(page.get("file")) == name:
            return page
        else:
            sections = page.get("pages", [])
            page = find_name(sections, name)
            if page is not None:
                return page


def add_toctree(app, doctree):
    # If no globaltoc is given, we'll skip this part
    if not app.config["globaltoc_path"]:
        return

    # First check whether this page has any descendants
    # If so, then we'll manually add them as a toctree object
    path = app.env.doc2path(app.env.docname, base=None)
    toc = app.config["globaltoc"]
    page = find_name(toc, _no_suffix(path))

    # If we didn't find this page in the TOC, raise an error
    if page is None:
        raise FileNotFoundError(
            f"The following path in your table of contents couldn't be found:\n\n{path}.\n\nDouble check your `_toc.yml` file to make sure the paths are correct."
        )

    # If we have no sections, then don't worry about a toctree
    sections = [(ii.get("title"), ii.get("file")) for ii in page.get("pages", [])]
    if len(sections) == 0:
        return

    for ii, (title, path_sec) in enumerate(sections):
        # Update path so it is relative to the root of the parent
        path_parent_folder = Path(page["file"]).parent
        path_sec = os.path.relpath(path_sec, path_parent_folder)
        sections[ii] = (title, path_sec)

    # Now build a toctree node (what the TocTree directive does basically)
    # Mimic https://github.com/sphinx-doc/sphinx/blob/0ae1bf6f037010b5599d12196b155bbf2cece9ba/sphinx/directives/other.py#L43
    subnode = addnodes.toctree()
    subnode["parent"] = app.env.docname

    # (title, ref) pairs, where ref may be a document, or an external link,
    # and title may be None if the document's title is to be used
    # NOTE: most of these we won't use, the ones we use are at the bottom
    subnode["includefiles"] = []
    subnode["maxdepth"] = -1
    subnode["caption"] = False
    subnode["glob"] = False
    subnode["hidden"] = True
    subnode["includehidden"] = False
    subnode["titlesonly"] = False
    subnode["rawentries"] = ""

    subnode["entries"] = []
    subnode["numbered"] = "numbered" in page

    wrappernode = nodes.compound(classes=["toctree-wrapper"])
    wrappernode.append(subnode)

    # Now parse the content and add the entries to subnode
    # reg = path, title = title
    for (title, path) in sections:
        # absolutize filenames
        path = docname_join(app.env.docname, path)
        subnode["entries"].append((title, path))
        subnode["includefiles"].append(path)

    # Now add the subnode to the last section of the toctree
    doc_sections = list(doctree.traverse(nodes.section))
    doc_sections[-1].append(wrappernode)


def update_indexname(app, config):
    # If no globaltoc is given, we'll skip this part
    if not app.config["globaltoc_path"]:
        return

    # Load the TOC and update the env so we have it later
    toc = yaml.safe_load(Path(app.config["globaltoc_path"]).read_text())
    if isinstance(toc, list):
        toc_updated = toc[0]
        if len(toc) > 1:
            subsections = toc[1:]
            toc_updated["pages"] = subsections
        toc = toc_updated
    app.config["globaltoc"] = toc

    # Update the main toctree file for whatever the first file here is
    app.config["master_doc"] = _no_suffix(toc["file"])


def _content_path_to_yaml(path, root_path, split_char="_"):
    """Return a YAML entry for the TOC from a path."""
    path = path.with_suffix("")
    if path.name == "index":
        title = _filename_to_title(path.resolve().parent.name, split_char=split_char)
    else:
        title = _filename_to_title(path.name, split_char=split_char)

    path_rel_root = path.relative_to(root_path)
    out = {"file": str(path_rel_root.with_suffix("")), "title": title}
    return out


def _find_content_structure(path, root_folder, split_char="_", skip_text=None):
    """Parse a folder and sub-folders for content and return a dict."""
    if skip_text is None:
        skip_text = []
    skip_text.append(".ipynb_checkpoints")

    path = Path(path)

    # First parse all the content files
    content_files = [
        ii for ii in path.iterdir() if ii.suffix in SUPPORTED_FILE_SUFFIXES
    ]

    if len(content_files) == 0:
        return

    # First content page (or file called index) will be the parent
    # Each folder must have at least one content file in it
    # First see if we have an "index" page
    first_content = None
    for ii, ifile in enumerate(content_files):
        if ifile.with_suffix("").name == "index":
            first_content = content_files.pop(ii)
    if not first_content:
        first_content = content_files.pop(0)
    parent = _content_path_to_yaml(first_content, root_folder, split_char=split_char)
    parent["pages"] = []

    # Children become pages of the parent
    for content_file in content_files:
        if any(iskip in str(content_file) for iskip in skip_text):
            continue
        parent["pages"].append(_content_path_to_yaml(content_file, root_folder))

    # Now recursively run this on folders, and add as another sub-page
    folders = [ii for ii in path.iterdir() if ii.is_dir()]
    for folder in folders:
        if any(iskip in str(folder) for iskip in skip_text):
            continue
        folder_out = _find_content_structure(
            folder, root_folder, split_char=split_char, skip_text=skip_text
        )
        if folder_out:
            parent["pages"].append(folder_out)

    if len(parent["pages"]) == 0:
        parent.pop("pages")
    return parent


def build_toc(path, filename_split_char="_", skip_text=None):
    """Auto-generate a Table of Contents from files/folders.

    All file and folder names are ordered alpha-numerically, unless
    a file name is "index", in which case it is treated as the first
    file.

    It uses the following logic:

    * In a given folder, the first content page is the folder parent.
    * All subsequent pages are sections of the parent page
    * For each sub-folder
        * Its first page is appended to sections of the parent page
        * All other sub-folder pages are children of the subfolder's first page 

    Parameters
    ----------
    path : str
        Path to the folder where content exists. The TOC will be generated
        according to the alphanumeric sort of these files/folders.
    filename_split_char : str
        The character used in inferring spaces in page names from filenames.
    skip_text : str | None
        If this text is found in any files or folders, they will be skipped.
    """
    structure = _find_content_structure(
        path, path, split_char=filename_split_char, skip_text=skip_text
    )
    if not structure:
        raise ValueError(f"No content files were found in {path}.")
    yaml_out = yaml.safe_dump(structure, default_flow_style=False, sort_keys=False)
    return yaml_out
