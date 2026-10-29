import sys


def main():
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import style
    from .mainwindow import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Kurvenwerk")
    app.setWindowIcon(QIcon(str(style.LOGO)))
    style.apply(app)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
