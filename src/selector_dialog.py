import aqt
from aqt.qt import *

from .forms import filter_dialog


class FilterDialog(QDialog):
    # takes a list or dict
    # shows the listitems or dictkeys in a QListWidget that you can filter
    # returns select listitem or dictkey/dictvalue
    def __init__(self, parent=None, values=None, windowtitle=""):
        self.parent = parent
        if isinstance(values, dict):
            self._dict = values
            self.keys = sorted(self._dict.keys())
        else:
            self.keys = values
            self._dict = False
        self.keys_shown = self.keys[:]
        if windowtitle:
            self.setWindowTitle(windowtitle)
        QDialog.__init__(self, parent, Qt.Window)
        self.dialog = filter_dialog.Ui_Dialog()
        self.dialog.setupUi(self)
        self.dialog.listWidget.itemDoubleClicked.connect(self.accept)
        self.dialog.filterbar.setPlaceholderText('type here to filter')
        self.dialog.filterbar.textChanged.connect(self.maybe_update_table)
        # workaround for the fact that when you type at the bottom the arrow keys
        # are applied to the lineedit
        self.dialog.filterbar.installEventFilter(self)
        self.terms = []
        self.selected = False
        self.setlist()
        self.dialog.listWidget.setCurrentRow(0)

    def setlist(self):
        self.dialog.listWidget.clear()
        self.dialog.listWidget.addItems(self.keys_shown)
        if self.selected:
            try:
                i = self.keys_shown.index(self.selected)
            except:
                pass
            else:
                self.dialog.listWidget.setCurrentRow(i)

    def eventFilter(self, source, event):
        if (event.type() == QEvent.KeyPress and source is self.dialog.filterbar):
            lw = self.dialog.listWidget
            row = lw.currentRow()
            if event.key() == Qt.Key_Up:
                lw.setCurrentRow(row-1)
                return True
            elif event.key() == Qt.Key_Down:
                lw.setCurrentRow(row+1)
                return True
        return False

    def maybe_update_table(self, text):
        terms = text.lower().split()
        # only update if necessary / ignore space
        if terms == self.terms:
            return
        else:
            self.terms = terms
        currow = self.dialog.listWidget.currentRow()
        if currow:
            try:
                self.selected = self.keys_shown[currow]
            except:
                self.selected = None
        else:
            self.selected = None
        self.keys_shown = []
        for l in self.keys:
            for i in self.terms:
                if i not in l.lower():
                    break
            else:
                self.keys_shown.append(l)
        self.setlist()

    def reject(self):
        QDialog.reject(self)

    def accept(self):
        currow = self.dialog.listWidget.currentRow()
        self.selkey = self.keys_shown[currow]
        if self._dict:
            self.selvalue = self._dict[self.selkey]
        QDialog.accept(self)
