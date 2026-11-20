from itunes_tools.common import config


def test_library_files_are_inside_the_itunes_folder():
    assert config.ITUNES_LIBRARY_XML.parent == config.ITUNES_FOLDER
    assert config.ITUNES_LIBRARY_ITL.parent == config.ITUNES_FOLDER


def test_image_cache_is_inside_the_app_folder_inside_the_itunes_folder():
    assert config.APP_FOLDER.parent == config.ITUNES_FOLDER
    assert config.IMAGE_CACHE_FOLDER.parent == config.APP_FOLDER


def test_sorter_folder_is_inside_the_app_folder():
    assert config.SORTER_FOLDER.parent == config.APP_FOLDER
