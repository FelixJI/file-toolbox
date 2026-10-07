"""GUI 合同测试的小型事件循环等待与模型读取。"""

from PySide6.QtCore import QEventLoop, Qt, QTimer


def wait_page(page):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(5)
    timeout = QTimer()
    timeout.setSingleShot(True)
    expired = []

    def done():
        preview = getattr(page, "_preview_timer", None)
        if not page._task.busy and (preview is None or not preview.isActive()):
            loop.quit()

    timer.timeout.connect(done)
    timeout.timeout.connect(lambda: (expired.append(True), loop.quit()))
    timer.start()
    timeout.start(5000)
    loop.exec()
    assert not expired, "页面任务未在测试期限内真实结束"


def cell(view, row, column, role=Qt.ItemDataRole.DisplayRole):
    model = view.model()
    return model.data(model.index(row, column), role)


def header(view, column):
    return view.model().headerData(column, Qt.Orientation.Horizontal)


def color(view, row, column):
    value = cell(view, row, column, Qt.ItemDataRole.BackgroundRole)
    return value.name().lower() if value is not None else ""
