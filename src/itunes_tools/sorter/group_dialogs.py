"""Small dialogs for groups (UC-7): picking a group by searching its name, and choosing years for season groups."""

from datetime import date

from PySide6.QtCore import QSortFilterProxyModel, QStringListModel, Qt, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QListView,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

FIRST_SEASON_YEAR = 1900
LAST_SEASON_YEAR = 2100


class GroupPickerDialog(QDialog):
    """Lets the user pick a group: typing in the search box filters the group names.

    Enter (or OK) takes the selected name, or the first one shown when none is selected;
    double-clicking a name takes it at once.
    """

    def __init__(self, group_names: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Move to group")

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search groups")
        self._search_box.setClearButtonEnabled(True)

        # The view shows the names through a proxy model that hides names not matching the search text.
        self._names_model = QStringListModel(group_names, self)
        self._filter_model = QSortFilterProxyModel(self)
        self._filter_model.setSourceModel(self._names_model)
        self._filter_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._names_view = QListView()
        self._names_view.setModel(self._filter_model)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_box)
        layout.addWidget(self._names_view)
        layout.addWidget(buttons)

        self._search_box.textChanged.connect(self._filter_model.setFilterFixedString)
        self._names_view.doubleClicked.connect(self.accept)
        self._search_box.setFocus()

    def set_search_text(self, text: str) -> None:
        """Type ``text`` into the search box, as the user would."""
        self._search_box.setText(text)

    def shown_names(self) -> list[str]:
        """Return the names the list shows for the current search text."""
        return [self._filter_model.index(row, 0).data() for row in range(self._filter_model.rowCount())]

    def chosen_name(self) -> str | None:
        """Return the selected name, else the first name shown, or ``None`` when no name is shown."""
        current = self._names_view.currentIndex()
        if current.isValid():
            return current.data()
        shown = self.shown_names()
        return shown[0] if shown else None

    @Slot()
    def accept(self) -> None:
        # Nothing to take while the search hides every name; keep the dialog open.
        if self.chosen_name() is not None:
            super().accept()


def ask_group(parent: QWidget | None, group_names: list[str]) -> str | None:
    """Show a ``GroupPickerDialog``; return the picked group name, or ``None`` if the user cancelled."""
    dialog = GroupPickerDialog(group_names, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.chosen_name()


class SeasonGroupsDialog(QDialog):
    """Asks for the first and last year of the season groups to create. *To* cannot be before *From*."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add season groups")
        this_year = date.today().year

        self._from_year = QSpinBox()
        self._from_year.setRange(FIRST_SEASON_YEAR, LAST_SEASON_YEAR)
        self._from_year.setValue(this_year)
        self._to_year = QSpinBox()
        self._to_year.setRange(this_year, LAST_SEASON_YEAR)
        self._to_year.setValue(this_year)
        # Raising From past To raises To with it.
        self._from_year.valueChanged.connect(self._to_year.setMinimum)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow("From year:", self._from_year)
        layout.addRow("To year:", self._to_year)
        layout.addRow(buttons)

    def set_years(self, first_year: int, last_year: int) -> None:
        """Set both years, as the user would (From first)."""
        self._from_year.setValue(first_year)
        self._to_year.setValue(last_year)

    def years(self) -> tuple[int, int]:
        """Return the chosen ``(first year, last year)``."""
        return self._from_year.value(), self._to_year.value()


def ask_year_range(parent: QWidget | None) -> tuple[int, int] | None:
    """Show a ``SeasonGroupsDialog``; return ``(first year, last year)``, or ``None`` if the user cancelled."""
    dialog = SeasonGroupsDialog(parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.years()
