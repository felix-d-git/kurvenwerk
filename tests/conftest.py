def pytest_sessionfinish(session, exitstatus):
    # Qt-Objekte vor dem Interpreter-Ende geordnet abbauen; sonst sporadischer Absturz beim
    # Entladen der Qt-DLLs NACH grünen Tests (Abort/Access Violation → Exit != 0).
    # Kein close(): das Hauptfenster würde nach ungespeicherten Änderungen fragen (hängt).
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    import shiboken6

    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    shiboken6.delete(app)
