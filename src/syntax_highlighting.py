"""
Add-on for Anki 2.1 "Syntax Highlighting FORK"

Copyright: (c) 2012-2015 Tiago Barroso <https://github.com/tmbb>
           (c) 2015 Tim Rae <https://github.com/timrae>
           (c) 2018 Glutanimate <https://glutanimate.com/>
           (c) 2019 anonymous (creator of "Mini Format Pack Supplementary", https://ankiweb.net/shared/info/476705431)
           (c) 2018 Rene Schallner
           (c) 2019 ijgnd
           (c) 2019 anonymous, https://ankiweb.net/shared/info/476705431

Use this at your own risk.

License: GNU AGPLv3 <https://www.gnu.org/licenses/agpl.html>
"""

import os
import sys
import re
import shutil

addon_path = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(addon_path, "libs"))

from bs4 import BeautifulSoup
from pygments import highlight
from pygments.lexers import get_lexer_by_name, get_all_lexers
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from pygments.styles import get_all_styles

import aqt
from aqt.qt import *
from aqt import mw
from aqt.editor import Editor
from aqt.utils import showWarning, showInfo
from anki.utils import json
from anki.hooks import addHook, wrap

# from .selector_dialog import FilterDialog
from .fuzzy_panel import FilterDialog
from .settings import MyConfigWindow
from .supplementary import wrap_in_tags


def gc(arg, fail=False):
    return mw.addonManager.getConfig(__name__).get(arg, fail)


############################################
########## gui config and auto loading #####

def set_some_paths():
    global addon_path
    global cssfolder
    global mediafolder
    global cssfile
    addon_path = os.path.dirname(__file__)
    cssfolder = os.path.join(addon_path, "css")
    mediafolder = os.path.join(mw.pm.profileFolder(), "collection.media")
    cssfile = os.path.join(mediafolder, "_styles_for_syntax_highlighting.css")
addHook("profileLoaded", set_some_paths)


insertscript = """<script>
function MyInsertHtml(content) {
    var sel, range;
    if (window.getSelection && (sel = window.getSelection()).rangeCount) {
        range = sel.getRangeAt(0);
        range.collapse(true);
        var mydiv = document.createElement("div");
        mydiv.innerHTML = content;
        range.insertNode(mydiv);
        // Move the caret
        range.setStartAfter(mydiv);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
    }
}
</script>
"""

def profileLoaded():
    editor_style = ""
    if os.path.isfile(cssfile):
        with open(cssfile, "r") as css_file:
            css = css_file.read()
            editor_style = "<style>\n{}\n</style>".format(css.replace("%", "%%"))
    aqt.editor._html = editor_style + insertscript + aqt.editor._html
addHook("profileLoaded", profileLoaded)


def update_templates(templatenames):
    for m in mw.col.models.all():
        if m['name'] in templatenames:
            line = """@import url("_styles_for_syntax_highlighting.css");"""
            if line not in m['css']:
                model = mw.col.models.get(m['id'])
                model['css'] = line + "\n\n" + model['css']
                mw.col.models.save(model, templates=True)


def update_cssfile_in_mediafolder(style):
    sourcefile = os.path.join(cssfolder, style + ".css")
    if os.path.isfile(sourcefile):
        shutil.copy(sourcefile, cssfile)


def onMySettings():
    dialog = MyConfigWindow(mw, mw.addonManager.getConfig(__name__))
    if dialog.exec_():
        mw.addonManager.writeConfig(__name__, dialog.config)
        if hasattr(dialog, "templates_to_update"):
            update_templates(dialog.templates_to_update)
        update_cssfile_in_mediafolder(dialog.config["style"])
        showInfo("You need to restart Anki so that all changes take effect.")
mw.addonManager.setConfigAction(__name__, onMySettings)


#######END gui config and auto loading #####
############################################




# This code sets a correspondence between:
#  The "language names": long, descriptive names we want
#                        to show the user AND
#  The "language aliases": short, cryptic names for internal
#                          use by HtmlFormatter
LANG_MAP = {lex[0]: lex[1][0] for lex in get_all_lexers()}

ERR_LEXER = ("<b>Error</b>: Selected language not found.<br>"
             "If you set a custom lang selection please make sure<br>"
             "you typed all list entries correctly.")

ERR_STYLE = ("<b>Error</b>: Selected style not found.<br>"
             "If you set a custom style please make sure<br>"
             "you typed it correctly.")

LASTUSED = ""


def showError(msg, parent):
    showWarning(msg, title="Code Formatter Error", parent=parent)


def get_deck_name(editor):
    if isinstance(editor.parentWindow, aqt.addcards.AddCards):
        return editor.parentWindow.deckChooser.deckName()
    elif isinstance(editor.parentWindow, (aqt.browser.Browser, aqt.editcurrent.EditCurrent)):
        return mw.col.decks.name(editor.card.did)
    else:
        return None  # Error


def get_default_lang(editor):
    lang = gc('defaultlang')
    if gc('defaultlangperdeck'):
        deck_name = get_deck_name(editor)
        if deck_name and deck_name in gc('deckdefaultlang'):
            lang = gc('deckdefaultlang')[deck_name]
    return lang


def process_html(html):
    html = re.sub(r"{{", "{<!---->{", html)
    html = re.sub(r"}}", "}<!---->}", html)
    return html


def hilcd(ed, code, langAlias):
    global LASTUSED
    linenos = gc('linenos')
    centerfragments = gc('centerfragments')
    noclasses = not gc('cssclasses')
    if (ed.mw.app.keyboardModifiers() & Qt.ShiftModifier):
        linenos ^= True
    if (ed.mw.app.keyboardModifiers() & Qt.ControlModifier):
        centerfragments ^= True
    mystyle = gc("style")
    if (ed.mw.app.keyboardModifiers() & Qt.AltModifier):
        d = FilterDialog(parent=None, values=list(get_all_styles()))
        if d.exec():
            mystyle = d.selkey
        noclasses = True
    inline = False
    if (ed.mw.app.keyboardModifiers() & Qt.MetaModifier):
        inline = True
    if inline:
        linenos = False

    try:
        my_lexer = get_lexer_by_name(langAlias, stripall=True)
    except ClassNotFound as e:
        print(e)
        showError(ERR_LEXER, parent=ed.parentWindow)
        return False

    try:
        # http://pygments.org/docs/formatters/#HtmlFormatter
        my_formatter = HtmlFormatter(
            linenos=linenos, noclasses=noclasses,
            font_size=16, style=mystyle, lineseparator="<br>", wrapcode=True)
    except ClassNotFound as e:
        print(e)
        showError(ERR_STYLE, parent=ed.parentWindow)
        return False

    if inline:
        pretty_code = "".join([highlight(code, my_lexer, my_formatter), "<br>"])
        replacements = {
            '<div class="highlight"': '<span class="highlight"',
            "<pre": "<code",
            "</pre></div>": "</code></span>",
            "<br>": "",
            "</br>": "",
            "</ br>": "",
            "<br />": "",
            'style="line-height: 125%"': 'style="line-height: 100%"',
        }
        for k, v in replacements.items():
            pretty_code = pretty_code.replace(k, v)
    else:
        if linenos:
            pretty_code = "".join([highlight(code, my_lexer, my_formatter), "<br>"])
        # to show line numbers pygments uses a table. The background color for the code
        # highlighting is limited to this table
        # If pygments doesn't use linenumbers it doesn't use a table. This means
        # that the background color covers the whole width of the card.
        # I don't like this. I didn't find an easier way than reusing the existing
        # solution.
        # Glutanimate removed the table in the commit
        # https://github.com/glutanimate/syntax-highlighting/commit/afbf5b3792611ecd2207b9975309d05de3610d45
        # which hasn't been published on Ankiweb in 2019-10-02.
        else:
            pretty_code = "".join(["<table><tbody><tr><td>",
                                    highlight(code, my_lexer, my_formatter),
                                    "</td></tr></tbody></table><br>"])
        soup = BeautifulSoup(pretty_code, 'html.parser')
        tablestyling = ""
        if centerfragments:
            tablestyling += "margin: 0 auto;"
        if noclasses:
            tablestyling += "text-align: left;"
        for t in soup.findAll("table"):
            if tablestyling:
                if t.has_attr('style'):
                    t['style'] = tablestyling + t['style']
                else:
                    t['style'] = tablestyling
            if noclasses:
                if t.has_attr('class'):
                    del t["class"]   # class tablehighlight
        if noclasses:
            for d in soup.find_all(attrs={'class': 'highlight'}):
                # thestyle = d['style']
                del d["class"]
            for d in soup.find_all(attrs={'class': 'linenodiv'}):
                # even for dark styles pygments uses a bright background color for the line numbers
                # In Night mode you then have unreadable white text on white background
                d['style'] = """background-color: transparent;"""
                del d["class"]
        pretty_code = str(soup)
    out = "`" + json.dumps(pretty_code)[1:-1] + "`"
    ed.web.eval("MyInsertHtml(%s);" % out)
    LASTUSED = langAlias


basic_stylesheet = """
QMenu::item {
    padding-top: 16px;
    padding-bottom: 16px;
    padding-right: 75px;
    padding-left: 20px;
    font-size: 15px;
}
QMenu::item:selected {
    background-color: #fd4332;
}
"""


class keyFilter(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Space:
                self.parent.alternative_keys(self.parent, Qt.Key_Return)
                return True
            elif event.key() == Qt.Key_T:
                self.parent.alternative_keys(self.parent, Qt.Key_Left)
                return True
            elif event.key() == Qt.Key_B:
                self.parent.alternative_keys(self.parent, Qt.Key_Down)
                return True
            elif event.key() == Qt.Key_G:
                self.parent.alternative_keys(self.parent, Qt.Key_Up)
                return True
            # elif event.key() == :
            #     self.parent.alternative_keys(self.parent, Qt.Key_Right)
            #     return True
        return False


def alternative_keys(self, key):
    # https://stackoverflow.com/questions/56014149/mimic-a-returnpressed-signal-on-qlineedit
    keyEvent = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
    QCoreApplication.postEvent(self, keyEvent)


def onAll(editor, code):
    d = FilterDialog(editor.parentWindow, LANG_MAP)
    if d.exec():
        hilcd(editor, code, d.selvalue)


def openHelperMenu(editor):
    global LASTUSED

    selected_text = editor.web.selectedText()
    if selected_text:
        #  Sometimes, self.web.selectedText() contains the unicode character
        # '\u00A0' (non-breaking space). This character messes with the
        # formatter for highlighted code.
        code = selected_text.replace('\u00A0', ' ')
    else:
        clipboard = QApplication.clipboard()
        code = clipboard.text()

    menu = QMenu(editor.widget)
    menu.setStyleSheet(basic_stylesheet)
    # add small info if pasting
    label = QLabel("selection" if selected_text else "paste")
    action = QWidgetAction(editor.widget)
    action.setDefaultWidget(label)
    menu.addAction(action)

    menu.alternative_keys = alternative_keys
    kfilter = keyFilter(menu)
    menu.installEventFilter(kfilter)

    if gc("show pre/code", False):
        u = menu.addAction("&unformatted (<pre>)")
        u.triggered.connect(lambda _, a=editor, c=code: wrap_in_tags(a, c, "pre"))
        c = menu.addAction("unformatted (<&code>)")
        c.triggered.connect(lambda _, a=editor, c=code: wrap_in_tags(a, c, "code"))

    d = menu.addAction("&default (%s)" % get_default_lang(editor))
    d.triggered.connect(lambda _, a=editor, c=code: hilcd(a, c, LANG_MAP[get_default_lang(editor)]))
    if LASTUSED:
        l = menu.addAction("l&ast used")
        l.triggered.connect(lambda _, a=editor, c=code: hilcd(a, c, LASTUSED))

    favmenu = menu.addMenu('&favorites')
    favfilter = keyFilter(favmenu)
    favmenu.installEventFilter(favfilter)
    favmenu.alternative_keys = alternative_keys

    a = menu.addAction("&select from all")
    a.triggered.connect(lambda _, a=editor, c=code: onAll(a, c))
    for e in gc("favorites"):
        a = favmenu.addAction(e)
        a.triggered.connect(lambda _, a=editor, c=code, l=LANG_MAP[e]: hilcd(a, c, l))
    menu.setActiveAction(d)
    menu.exec_(QCursor.pos())


def editorContextMenu(ewv, menu):
    e = ewv.editor
    a = menu.addAction("Syntax Highlighting")
    a.triggered.connect(lambda _, ed=e: openHelperMenu(ed))
addHook('EditorWebView.contextMenuEvent', editorContextMenu)


# def SetupShortcuts(cuts, editor):
#     cuts.append((gc("hotkey"), lambda e=editor: openHelperMenu(e)))
# addHook("setupEditorShortcuts", SetupShortcuts)


def keystr(k):
    key = QKeySequence(k)
    return key.toString(QKeySequence.NativeText)


def setupEditorButtonsFilter(buttons, editor):
    b = editor.addButton(
        os.path.join(addon_path, "icons", "button.png"),
        "syhl_linkbutton",
        openHelperMenu,
        tip="Syntax Highlighting for code ({})".format(keystr(gc("hotkey", ""))),
        keys=gc("hotkey", "")
        )
    buttons.append(b)
    return buttons
addHook("setupEditorButtons", setupEditorButtonsFilter)
