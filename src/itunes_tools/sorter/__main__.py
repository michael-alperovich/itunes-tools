import sys

from PySide6.QtWidgets import QApplication

from itunes_tools.sorter.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)  # exactly one per process, created before any widget
    window = MainWindow()
    window.show()  # widgets start hidden
    sys.exit(app.exec())  # run the event loop until the last window closes
