 
# https://stackoverflow.com/questions/44060971/pyqt5-swipe-to-check-uncheck-in-qlistwidget

from aqt.qt import *


class CheckableDialog(QDialog):
    def __init__(self, parent=None, values=None, windowtitle=""):
        super().__init__(parent)
        if windowtitle:
            self.setWindowTitle(windowtitle)
        self.setObjectName("CheckableDialog")
        self.parent = parent
        self.values = sorted(values)
        self.initUI()

    def initUI(self):
        vlay = QVBoxLayout()
        self.listWidget = QListWidget()
        self.listWidget.itemEntered.connect(lambda item: item.setCheckState(
            Qt.Checked if item.checkState() == Qt.Unchecked else Qt.Unchecked))
        for i in self.values:
            item = QListWidgetItem(i)
            item.setCheckState(Qt.Unchecked)
            self.listWidget.addItem(item)
        self.buttonbox = QDialogButtonBox(QDialogButtonBox.Ok |
                                          QDialogButtonBox.Cancel)
        vlay.addWidget(self.listWidget)
        vlay.addWidget(self.buttonbox)
        self.buttonbox.accepted.connect(self.onAccept)
        self.buttonbox.rejected.connect(self.onReject)
        self.setLayout(vlay)

    def onAccept(self):
        self.selected = []
        for i in range(self.listWidget.count()):
            if self.listWidget.item(i).checkState():
                self.selected.append(self.values[i])
        self.accept()

    def onReject(self):
        self.reject()
