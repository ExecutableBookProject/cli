"""A small sphinx extension to let you configure a site with YAML metadata."""
from pathlib import Path
from yaml import safe_load


# Transform a "Jupyter Book" YAML configuration file into a Sphinx configuration file.
# This is so that we can choose more user-friendly words for things than Sphinx uses.
# e.g., 'logo' instead of 'html_logo'.
# Note that this should only be used for **top level** keys.
PATH_YAML_DEFAULT = Path(__file__).parent.joinpath("default_config.yml")


def add_yaml_config(app, config):
    """Load all of the key/vals in a config file into the Sphinx config"""
    # First load the default YAML config
    yaml_config = safe_load(PATH_YAML_DEFAULT.read_text())

    # Update the default config with a provided one, if it exists
    path_yaml = app.config["yaml_config_path"]
    if len(path_yaml) > 0:
        path_yaml = Path(path_yaml)
        if not path_yaml.exists():
            raise ValueError(
                f"Path to a _config.yml file was given, but not found: {path_yaml}"
            )

        # Load the YAML and update its values to translate it into Sphinx keys
        yaml_update = safe_load(path_yaml.read_text())
        yaml_config.update(yaml_update)

    # Now update our Sphinx build configuration
    new_config = yaml_to_sphinx(yaml_config, config)
    for key, val in new_config.items():
        config[key] = val


def yaml_to_sphinx(yaml, config):
    """Convert a Jupyter Book style config structure into a Sphinx docs structure."""
    out = {
        "html_theme_options": {},
        "exclude_patterns": [
            "_build",
            "Thumbs.db",
            ".DS_Store",
            "**.ipynb_checkpoints",
        ],
    }

    # Theme configuration updates
    theme_options = out.get("html_theme_options", {})

    # Launch button configuration
    theme_launch_buttons_config = theme_options.get("launch_buttons", {})
    launch_buttons_config = yaml.get("launch_buttons", {})
    repository_config = yaml.get("repository", {})

    theme_launch_buttons_config.update(launch_buttons_config)
    theme_options["launch_buttons"] = theme_launch_buttons_config

    theme_options["path_to_docs"] = repository_config.get("path_to_book")
    theme_options["repository_url"] = repository_config.get("url")
    out["html_theme_options"] = theme_options

    html = yaml.get("html")
    if html:
        out["html_favicon"] = html.get("favicon")
        out["html_theme_options"]["sidebar_footer_text"] = html.get(
            "sidebar_footer_text"
        )
        out["google_analytics_id"] = html.get("google_analytics_id")
    latex = yaml.get("latex")
    if latex:
        out["latex_engine"] = latex.get("latex_engine")

    # Files that we wish to skip
    out["exclude_patterns"].extend(yaml.get("exclude_patterns", []))

    # Now do simple top-level translations
    YAML_TRANSLATIONS = {
        "logo": "html_logo",
        "title": "html_title",
        "execute_notebooks": "jupyter_execute_notebooks",
    }
    for key, newkey in YAML_TRANSLATIONS.items():
        if key in yaml:
            out[newkey] = yaml.pop(key)
    return out
