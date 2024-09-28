import configparser
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".napari-plugin-manager"
DEFAULT_CONFIG_FILE_PATH = DEFAULT_CONFIG_PATH / "napari-plugin-manager.ini"


def get_configuration():
    """
    Get plugin manager configuration.

    Currently only used to store need to show an initial disclaimer message:
        * `['general']['show_disclaimer']` -> bool
    """
    DEFAULT_CONFIG_PATH.mkdir(exist_ok=True)
    config = configparser.ConfigParser()

    if DEFAULT_CONFIG_FILE_PATH.exists():
        config.read(DEFAULT_CONFIG_FILE_PATH)
        # Since the config was stored ensure the disclamer config is now `False`
        # an update save config for the next time
        if config.getboolean("general", "show_disclaimer"):
            config.set("general", "show_disclaimer", "False")
            with open(DEFAULT_CONFIG_FILE_PATH, "w") as configfile:
                config.write(configfile)
    else:
        # Set default config
        config["general"] = {"show_disclaimer": True}

        # Write the configuration to a file
        with open(DEFAULT_CONFIG_FILE_PATH, "w") as configfile:
            config.write(configfile)

    return config
