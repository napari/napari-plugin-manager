from unittest.mock import patch

from napari_plugin_manager import config


def test_config_file(tmp_path):
    TMP_DEFAULT_CONFIG_PATH = tmp_path / ".napari-plugin-manager"
    TMP_DEFAULT_CONFIG_FILE_PATH = (
        TMP_DEFAULT_CONFIG_PATH / "napari-plugin-manager.ini"
    )

    assert not TMP_DEFAULT_CONFIG_PATH.exists()
    assert not TMP_DEFAULT_CONFIG_FILE_PATH.exists()

    with (
        patch.object(config, "DEFAULT_CONFIG_PATH", TMP_DEFAULT_CONFIG_PATH),
        patch.object(
            config, "DEFAULT_CONFIG_FILE_PATH", TMP_DEFAULT_CONFIG_FILE_PATH
        ),
    ):
        initial_config = config.get_configuration()
        assert TMP_DEFAULT_CONFIG_PATH.exists()
        assert TMP_DEFAULT_CONFIG_FILE_PATH.exists()
        assert initial_config.getboolean("general", "show_disclaimer")
        second_config = config.get_configuration()
        assert TMP_DEFAULT_CONFIG_PATH.exists()
        assert TMP_DEFAULT_CONFIG_FILE_PATH.exists()
        assert not second_config.getboolean("general", "show_disclaimer")
