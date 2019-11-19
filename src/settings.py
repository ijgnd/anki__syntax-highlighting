from pygments.lexers import get_all_lexers
from pygments.styles import get_all_styles

import aqt
from aqt.qt import *
from aqt.utils import tooltip, showInfo, askUser

from .forms import syntax_settings
from .forms import deck_default
# from .selector_dialog import FilterDialog
from .fuzzy_panel import FilterDialog
from .checkable import CheckableDialog


LANGUAGES_MAP = {lex[0]: lex[1][0] for lex in get_all_lexers()}


class DefaultForDeckAdd(QDialog):
    def __init__(self, parent):
        self.parent = parent
        QDialog.__init__(self, parent, Qt.Window)
        self.dialog = deck_default.Ui_Dialog()
        self.dialog.setupUi(self)
        self.setWindowTitle("Set Default Lang for Deck")
        self.dialog.pb_lang.clicked.connect(self.onLang)
        self.dialog.pb_lang.setText("select")
        self.dialog.pb_deck.clicked.connect(self.onDeck)
        self.dialog.pb_deck.setText("select")
        self.dialog.ql_deck.setText("")
        self.dialog.ql_lang.setText("")
        self.deck = ""
        self.lang = ""

    def onDeck(self):
        alldecks = aqt.mw.col.decks.allNames()
        d = FilterDialog(parent=self, values=alldecks)
        if d.exec():
            self.dialog.ql_deck.setText(d.selkey)

    def onLang(self):
        d = FilterDialog(parent=self, values=list(LANGUAGES_MAP.keys()))
        if d.exec():
            self.dialog.ql_lang.setText(d.selkey)

    def accept(self):
        self.deck = self.dialog.ql_deck.text()
        self.lang = self.dialog.ql_lang.text()
        QDialog.accept(self)


class MyConfigWindow(QDialog):
    def __init__(self, parent, config):
        self.parent = parent
        self.config = config
        QDialog.__init__(self, parent, Qt.Window)
        self.dialog = syntax_settings.Ui_Dialog()
        self.dialog.setupUi(self)
        self.setWindowTitle("Syntax Highlighting for Code options")
        self.applyconfig()
        self.setbuttons()
        self.favorites = self.config['favorites']
        decklist = []
        if self.config['deckdefaultlang']:
            for k, v in self.config['deckdefaultlang'].items():
                decklist.append(k + '   (' + v + ')')
        self.decklist = sorted(decklist)
        self.settable(self.dialog.lw_deckdefaults, self.decklist)
        self.settable(self.dialog.lw_favs, self.favorites)
        self.templates_to_update = []

    def setbuttons(self):
        self.dialog.pb_setFont.clicked.connect(self.onSelectFont)
        self.dialog.pb_setstyle.clicked.connect(self.onSelectStyle)
        self.dialog.pb_up.clicked.connect(self.onListUp)
        self.dialog.pb_down.clicked.connect(self.onListDown)
        self.dialog.pb_add.clicked.connect(self.onListAdd)
        self.dialog.pb_delete.clicked.connect(self.onListDelete)
        self.dialog.pb_deck_def_add.clicked.connect(self.add_default_for_deck)
        self.dialog.pb_deck_def_del.clicked.connect(self.del_default_for_deck)
        self.dialog.pb_setDefLang.clicked.connect(self.on_select_default_lang)
        self.dialog.cb_usecss.stateChanged.connect(self.oncsschange)
        self.dialog.cb_defaultlangperdeck.stateChanged.connect(self.ondeckdefaultchange)
        self.dialog.pb_updateTemplates.clicked.connect(self.onupdatetemplates)

    def onupdatetemplates(self):
        msg = ("If you want to use CSS for syntax highlighting you need about 50-100 lines"
               "of css. Copying these into every note type styling is time consuming, "
               "especially if you ever decide to change something. I prefer to put all the "
               "css into one file in the media folder and load it into my Anki notes.\n\n"
               "For this you need the line '@import url(\"_styles_for_syntax_highlighting.css\");'"
               "at the top of the styling of each note type.\n\n"
               "Instead of copying this line into every template this add-on writes "
               "this line of code at the top of each note type that you select in the following "
               "dialog.\n\n"
               "Continue?")
        if askUser(msg):
            notetypes = aqt.mw.col.models.allNames()
            title = "Select note types whose styling section should be updated"
            d = CheckableDialog(parent=None, values=list(notetypes), windowtitle=title)
            if d.exec():
                self.templates_to_update = d.selected

    def oncsschange(self):
        if self.dialog.cb_usecss.isChecked():
            self.dialog.wid_css.setVisible(True)
        else:
            self.dialog.wid_css.setVisible(False)

    def ondeckdefaultchange(self):
        if self.dialog.cb_defaultlangperdeck.isChecked():
            self.dialog.wid_deckdefaults.setVisible(True)
        else:
            self.dialog.wid_deckdefaults.setVisible(False)

    def applyconfig(self):
        self.dialog.le_shortcut.setText(self.config['hotkey'])
        self.dialog.cb_center.setChecked(self.config['centerfragments'])
        self.dialog.cb_showPreCode.setChecked(self.config['show pre/code'])
        self.oncsschange()
        self.dialog.cb_usecss.setChecked(self.config['cssclasses'])
        self.dialog.cb_linenum.setChecked(self.config['linenos'])
        self.dialog.cb_defaultlangperdeck.setChecked(self.config['defaultlangperdeck'])
        self.ondeckdefaultchange()
        if self.config['font']:
            self.dialog.lab_Font_selected.setText(self.config['font'])
        self.dialog.lab_style_selected.setText(self.config['style'])
        self.dialog.ql_deflang.setText(self.config['defaultlang'])

    def settable(self, listwidget, _list):
        listwidget.clear()
        listwidget.addItems(_list)
        listwidget.repaint()

    def onSelectFont(self):
        prelim = QFontDatabase().families()
        # remove foundry names that Qt adds
        f = [x.split(" [")[0] for x in prelim]
        f = list(set(f))  # remove duplicates
        f.append('default - unset')
        d = FilterDialog(parent=None, values=sorted(f))
        if d.exec():
            self.dialog.lab_Font_selected.setText(d.selkey)

    def onSelectStyle(self):
        d = FilterDialog(parent=None, values=list(get_all_styles()))
        if d.exec():
            self.dialog.lab_style_selected.setText(d.selkey)

    def onListUp(self):
        self.moveInList(-1)

    def onListDown(self):
        self.moveInList(1)

    def moveInList(self, arg):
        lw = self.dialog.lw_favs
        row = lw.currentRow()
        thisitem = lw.takeItem(row)
        lw.insertItem(row + arg, thisitem)
        lw.setCurrentRow(row + arg)

    def onListAdd(self):
        d = FilterDialog(parent=None, values=LANGUAGES_MAP)
        if d.exec():
            self.dialog.lw_favs.addItem(d.selkey)

    def onListDelete(self):
        lw = self.dialog.lw_favs
        lw.takeItem(lw.currentRow())

    def on_select_default_lang(self):
        d = FilterDialog(parent=self, values=list(LANGUAGES_MAP.keys()))
        if d.exec():
            self.dialog.ql_deflang.setText(d.selkey)

    def add_default_for_deck(self):
        d = DefaultForDeckAdd(self)
        if d.exec():
            if d.deck and d.lang:
                text = d.deck + '   (' + d.lang + ')'
                self.decklist.append(text)
                self.decklist.sort()
                self.settable(self.dialog.lw_deckdefaults, self.decklist)

    def del_default_for_deck(self):
        row = self.dialog.lw_deckdefaults.currentRow()
        if row > -1:  # 'if row' doesn't work because the first index is 0.
            del self.decklist[row]
            self.settable(self.dialog.lw_deckdefaults, self.decklist)

    def reject(self):
        QDialog.reject(self)

    def accept(self):
        # https://stackoverflow.com/questions/4629584/pyqt4-how-do-you-iterate-all-items-in-a-qlistwidget
        favs = [str(self.dialog.lw_favs.item(i).text()) for i in range(self.dialog.lw_favs.count())]
        if len(favs) < 1:
            showInfo('select as least one favorite language. Returning to config ...')
            return
        try:
            shortcut = self.dialog.le_shortcut.text()
        except:
            showInfo('You must set a shortcut. Returning to config ...')
            return
        # convert default deck list to dict
        defaultdict = {}
        for i in range(self.dialog.lw_deckdefaults.count()):
            text = str(self.dialog.lw_deckdefaults.item(i).text())
            deck, _, lang = text.rpartition('   (')
            defaultdict[deck] = lang[:-1]  # -1 because I attach ')'
        if self.dialog.lab_Font_selected.text() == "default - unset":
            myfont = ""
        else:
            myfont = self.dialog.lab_Font_selected.text()
        self.config = {
            "show pre/code": self.dialog.cb_showPreCode.isChecked(),
            "centerfragments": self.dialog.cb_center.isChecked(),
            "cssclasses": self.dialog.cb_usecss.isChecked(),
            "defaultlangperdeck": self.dialog.cb_defaultlangperdeck.isChecked(),
            "deckdefaultlang": defaultdict,
            "defaultlang": self.dialog.ql_deflang.text(),
            "favorites": favs,
            "hotkey": shortcut,
            "linenos": self.dialog.cb_linenum.isChecked(),
            "style": self.dialog.lab_style_selected.text(),
            "font": myfont,
        }
        QDialog.accept(self)
