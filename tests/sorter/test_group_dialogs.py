import pytest
from PySide6.QtWidgets import QDialog

from itunes_tools.sorter.group_dialogs import GroupPickerDialog, SeasonGroupsDialog

pytestmark = pytest.mark.usefixtures("qt_application")

NAMES = ["Winter 2017", "Spring 2017", "Summer 2017", "Fall 2017", "Ballads"]


def test_picker_shows_all_names_without_search_text():
    dialog = GroupPickerDialog(NAMES)

    assert dialog.shown_names() == NAMES


def test_picker_search_is_case_insensitive_and_matches_anywhere_in_the_name():
    dialog = GroupPickerDialog(NAMES)

    dialog.set_search_text("ALL")

    assert dialog.shown_names() == ["Fall 2017", "Ballads"]


def test_picker_chooses_the_first_shown_name_when_none_is_selected():
    dialog = GroupPickerDialog(NAMES)

    dialog.set_search_text("summer")
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.chosen_name() == "Summer 2017"


def test_picker_stays_open_when_the_search_hides_every_name():
    dialog = GroupPickerDialog(NAMES)

    dialog.set_search_text("autumn")
    dialog.accept()

    assert dialog.chosen_name() is None
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_season_dialog_returns_the_chosen_years():
    dialog = SeasonGroupsDialog()

    dialog.set_years(2015, 2018)

    assert dialog.years() == (2015, 2018)


def test_season_dialog_to_year_cannot_be_before_from_year():
    dialog = SeasonGroupsDialog()
    dialog.set_years(2015, 2016)

    dialog.set_years(2020, 2016)

    assert dialog.years() == (2020, 2020)
