# noScribeEdit 
# Part of noScribe, the AI-powered Audio Transcription
# Copyright (C) 2025 Kai Dröge
# ported to MAC by Philipp Schneider (gernophil)
# Based on Megasolid Idiom - https://www.pythonguis.com/examples/python-rich-text-editor/

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import qtawesome as qta
from PyQt6 import QtGui
from PyQt6 import QtWidgets
from PyQt6 import QtCore
import platform

import os
import sys
import shlex
import subprocess
from datetime import datetime
from time import sleep
import AdvancedHTMLParser
import html
from tempfile import TemporaryDirectory
import appdirs
import yaml
from search_and_replace_dialog import SearchAndReplaceDialog
import re
import unicodedata

app_dir = os.path.abspath(os.path.dirname(__file__))

icon_color = '#aaaaaa'
highlight_color = '#ff8c00'
default_font = "Arial"
default_font_size = "12pt"

# Helper functions

# config
config_dir = appdirs.user_config_dir('noScribe')
if not os.path.exists(config_dir):
    os.makedirs(config_dir)

config_file = os.path.join(config_dir, 'editor_config.yaml')

try:
    with open(config_file, 'r') as file:
        config = yaml.safe_load(file)
        if not config:
            raise # config file is empty (None)        
except: # seems we run it for the first time and there is no config file
    config = {}
    
def get_config(key: str, default):
    """ Get a config value, set it if it doesn't exist """
    if key not in config:
        config[key] = default
    return config[key]

# recent files

def update_recent_files(filepath):
    recent_files = config.get('recent_files', [])
    
    if filepath in recent_files:
        recent_files.remove(filepath)
    
    recent_files.insert(0, filepath)  # Add to the top of the list
    
    # Keep only the five most recent files
    recent_files = recent_files[:5]
    config['recent_files'] = recent_files
    
# helper for encoding/decoding 

def decode_timestamp(ts):
    # return start, finish
    # example: "ts_1234_4321"
    if not ts:
        raise Exception("No timestamp found")
    ts_list = ts.split('_')
    if (len(ts_list) < 3) or (ts_list[0] != "ts"):
        raise Exception(f"Unable to decode timestamp <{ts}>")
    else:
        return int(ts_list[1]), int(ts_list[2]) 

def ms_to_str(t):
         hh = t//(60*60*1000) # hours
         t = t-hh*(60*60*1000)
         mm = t//(60*1000) # minutes
         t = t-mm*(60*1000)
         ss = t//1000 # seconds
         # sss = t-ss*1000 # milliseconds
         return(f'{hh:02d}:{mm:02d}:{ss:02d}')
    
def timestamp_to_string(start, stop):
    # returns "HH:MM:SS - HH:MM:SS"    
    return ms_to_str(start) + ' - ' + ms_to_str(stop)

# Helper for text only output
        
def html_node_to_text(node: AdvancedHTMLParser.AdvancedTag) -> str:
    """
    Recursively get all text from a html node and its children. 
    """
    # For text nodes, return their value directly
    if AdvancedHTMLParser.isTextNode(node): # node.nodeType == node.TEXT_NODE:
        return html.unescape(node)
    # For element nodes, recursively process their children
    elif AdvancedHTMLParser.isTagNode(node):
        text_parts = []
        for child in node.childBlocks:
            text = html_node_to_text(child)
            if text:
                text_parts.append(text)
        # For block-level elements, prepend and append newlines
        if node.tagName.lower() in ['p', 'div', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br']:
            if node.tagName.lower() == 'br':
                return '\n'
            else:
                return '\n' + ''.join(text_parts).strip() + '\n'
        else:
            return ''.join(text_parts)
    else:
        return ''

def html_to_text(parser: AdvancedHTMLParser.AdvancedHTMLParser) -> str:
    return html_node_to_text(parser.body)

# Helper for WebVTT output

def clean_vtt_voice(value: str) -> str:
    """
    Clean up a string so it can safely be used inside a 'v' field in WebVTT.
    
    Rules applied:
    - Normalize Unicode characters (NFKD).
    - Remove diacritics (accents).
    - Replace spaces with underscores.
    - Strip leading/trailing whitespace.
    - Remove or replace invalid characters (keep only letters, digits, underscore, hyphen).
    - Ensure it doesn’t start with a digit (prefix with 'v_' if so).
    - Preserve case (do NOT force lowercase).
    """
    # Normalize and strip accents
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join([c for c in normalized if not unicodedata.combining(c)])
    
    # Replace spaces with underscores
    cleaned = without_accents.strip().replace(" ", "_")
    
    # Remove invalid characters (only letters, digits, _, -)
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    
    # Ensure it doesn't start with a digit
    if cleaned and cleaned[0].isdigit():
        cleaned = "v_" + cleaned
    
    return cleaned

def vtt_escape(txt: str) -> str:
    txt = html.escape(txt)
    while txt.find('\n\n') > -1:
        txt = txt.replace('\n\n', '\n')
    return txt    

def ms_to_webvtt(milliseconds) -> str:
    """converts milliseconds to the time stamp of WebVTT (HH:MM:SS.mmm)
    """
    # 1 hour = 3600000 milliseconds
    # 1 minute = 60000 milliseconds
    # 1 second = 1000 milliseconds
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return "{:02d}:{:02d}:{:02d}.{:03d}".format(hours, minutes, seconds, milliseconds)

def html_to_webvtt(parser: AdvancedHTMLParser.AdvancedHTMLParser, media_path: str):
    vtt = 'WEBVTT '
    paragraphs = parser.getElementsByTagName('p')
    if len(paragraphs) > 2:
        # The first paragraph contains the title
        vtt += vtt_escape(paragraphs[0].textContent) + '\n\n'
        # Next paragraph contains info about the transcript. Add as a note.
        vtt += vtt_escape('NOTE\n' + html_node_to_text(paragraphs[1])) + '\n\n'
    if media_path != '':
        # Add media source:
        vtt += f'NOTE media: {media_path}\n\n'

    #Add all segments as VTT cues
    segments = parser.getElementsByTagName('a')
    i = 0
    for i in range(len(segments)):
        segment = segments[i]
        name = segment.attributes['name']
        if name is not None:
            name_elems = name.split('_', 4)
            if len(name_elems) > 1 and name_elems[0] == 'ts':
                start = ms_to_webvtt(int(name_elems[1]))
                end = ms_to_webvtt(int(name_elems[2]))
                spkr = name_elems[3]
                txt = vtt_escape(html_node_to_text(segment))
                vtt += f'{i+1}\n{start} --> {end}\n<v {spkr}>{txt.lstrip()}\n\n'
    return vtt

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        
        self.media_player = None
        self.playback_speed = 100
        self.path = None # current file
        self.audio_source = None # corresponding audio file
        self.tmp_audio_file = None
        self.keep_playing = False # Stops the play_along-function when set to False 
        
        # Restore stored window geometry
        geom = get_config('window_geometry', None)
        if geom:
            self.restoreGeometry(QtCore.QByteArray.fromHex(geom.encode('utf-8')))
        
        # GUI
        layout = QtWidgets.QVBoxLayout()
        
        # Editor:        
        self.editor = QtWidgets.QTextEdit()
        palette = self.palette()
        default_background_color = palette.color(palette.ColorRole.Button)
        self.editor.setStyleSheet("QTextEdit {color: #000000; background-color: #ffffff; border: 0px;} QScrollBar::handle {background: " + default_background_color.name() + "}")
        self.editor.setAcceptRichText(True)
        self.editor.setAutoFormatting(QtWidgets.QTextEdit.AutoFormattingFlag.AutoNone)
        self.editor.cursorPositionChanged.connect(self.cursor_changed)
        self.editor.selectionChanged.connect(self.cursor_changed)
        self.editor.installEventFilter(EnterKeyFilter(self.editor))
        editor_zoom = get_config('editor_zoom', '11')
        font = QtGui.QFont(default_font, int(editor_zoom))
        self.editor.setFont(font)
        layout.addWidget(self.editor)
        container = QtWidgets.QWidget()
        container.setStyleSheet("background-color: #ffffff;")
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Status Bar
        self.status = QtWidgets.QStatusBar()
        self.status.setStyleSheet("border: 0px")
        self.timestamp_status = QtWidgets.QLabel('')
        self.timestamp_status.setMinimumWidth(130)
        self.timestamp_status.setStyleSheet("border-left: 2px solid #474747; ")
        self.timestamp_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status.addPermanentWidget(self.timestamp_status)
        self.setStatusBar(self.status)

        # Toolbar
        
        # self.menuBar().setNativeMenuBar(False) # Uncomment to disable native menubar on Mac
        file_toolbar = QtWidgets.QToolBar("File")
        file_toolbar.setMovable(False)
        file_toolbar.setIconSize(QtCore.QSize(24, 24))
        file_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(file_toolbar)
        file_menu = self.menuBar().addMenu("&File")

        open_file_action = QtGui.QAction(qta.icon('mdi.folder-open', color=icon_color), "Open file...", self)
        open_file_action.setStatusTip("Open file")
        open_file_action.setShortcut(QtGui.QKeySequence.Open)
        open_file_action.triggered.connect(self.file_open)
        file_menu.addAction(open_file_action)
        file_toolbar.addAction(open_file_action)
        
        self.recent_files_menu = file_menu.addMenu("Recent Files")
        self.update_recent_files_menu()  # Populate the recent files submenu initially

        save_file_action = QtGui.QAction(qta.icon('mdi.content-save', color=icon_color), "Save", self)
        save_file_action.setStatusTip("Save current file")
        save_file_action.setShortcut(QtGui.QKeySequence.Save)
        save_file_action.triggered.connect(self.file_save)
        file_menu.addAction(save_file_action)
        file_toolbar.addAction(save_file_action)

        saveas_file_action = QtGui.QAction(qta.icon('mdi.content-save-move', color=icon_color), "Save As...", self)
        saveas_file_action.setStatusTip("Save current file to specified file")
        saveas_file_action.triggered.connect(self.file_saveas)
        file_menu.addAction(saveas_file_action)
        #file_toolbar.addAction(saveas_file_action)
        
        file_menu.addSeparator()
        file_toolbar.addSeparator()
        
        audio_source_action = QtGui.QAction(qta.icon('mdi.waveform', color=icon_color), "Audio source...", self)
        audio_source_action.setStatusTip("Locate the audio source file of the current transcript")
        audio_source_action.triggered.connect(self.open_audio_source)
        file_menu.addAction(audio_source_action)


        noScribe_toolbar = QtWidgets.QToolBar("noScribe")
        noScribe_toolbar.setMovable(False)
        noScribe_toolbar.setIconSize(QtCore.QSize(24, 24))
        noScribe_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.addToolBar(noScribe_toolbar)
        # noScribe_menu = self.menuBar().addMenu("no&Scribe")
       
        self.play_along_action = QtGui.QAction(qta.icon('mdi.volume-high', color=highlight_color), "Play/Pause Audio", self)      
        self.play_along_action.setCheckable(True)
        self.play_along_action.setStatusTip("Listen to the audio source of the current text")
        if platform.system() == 'Darwin': # = MAC
            self.play_along_action.setShortcut(QtGui.QKeySequence('Meta+Space'))
        else:
            self.play_along_action.setShortcut(QtGui.QKeySequence('Ctrl+Space'))
        self.play_along_action.toggled.connect(self.play_along)
        # file_menu.addAction(open_file_action)
        noScribe_toolbar.addAction(self.play_along_action)
        
        self.playback_speed = QtWidgets.QComboBox()
        self.playback_speed.addItems(['60%', '80%', '100%', '120%', '135%', '150%', '180%', '200%'])
        self.playback_speed.setCurrentIndex(2) # default 100%
        self.playback_speed.setToolTip("Playback speed")
        self.playback_speed.setStatusTip("Set playback speed")
        noScribe_toolbar.addWidget(self.playback_speed)
            
        edit_toolbar = QtWidgets.QToolBar("Edit")
        edit_toolbar.setMovable(False)
        edit_toolbar.setIconSize(QtCore.QSize(24, 24))
        edit_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.addToolBar(edit_toolbar)
        edit_menu = self.menuBar().addMenu("&Edit")

        edit_menu.addAction(self.play_along_action)
        edit_menu.addSeparator()

        undo_action = QtGui.QAction(qta.icon('mdi.undo', color=icon_color), "Undo", self)
        undo_action.setStatusTip("Undo last change")
        undo_action.setShortcut(QtGui.QKeySequence.Undo)
        undo_action.triggered.connect(self.editor.undo)
        edit_toolbar.addAction(undo_action)
        edit_menu.addAction(undo_action)

        redo_action = QtGui.QAction(qta.icon('mdi.redo', color=icon_color), "Redo", self)
        redo_action.setStatusTip("Redo last change")
        redo_action.setShortcut(QtGui.QKeySequence.Redo)
        redo_action.triggered.connect(self.editor.redo)
        edit_toolbar.addAction(redo_action)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()
        edit_toolbar.addSeparator()

        cut_action = QtGui.QAction(qta.icon('mdi.content-cut', color=icon_color), "Cut", self)
        cut_action.setStatusTip("Cut selected text")
        cut_action.setShortcut(QtGui.QKeySequence.Cut)
        cut_action.triggered.connect(self.editor.cut)
        edit_toolbar.addAction(cut_action)
        edit_menu.addAction(cut_action)

        copy_action = QtGui.QAction(qta.icon('mdi.content-copy', color=icon_color), "Copy", self)
        copy_action.setStatusTip("Copy selected text")
        copy_action.setShortcut(QtGui.QKeySequence.Copy)
        copy_action.triggered.connect(self.editor.copy)
        edit_toolbar.addAction(copy_action)
        edit_menu.addAction(copy_action)

        paste_action = QtGui.QAction(qta.icon('mdi.content-paste', color=icon_color), "Paste", self)
        paste_action.setStatusTip("Paste from clipboard")
        paste_action.setShortcut(QtGui.QKeySequence.Paste)
        paste_action.triggered.connect(self.editor.paste)
        edit_toolbar.addAction(paste_action)
        edit_menu.addAction(paste_action)

        select_action = QtGui.QAction("Select all", self)
        select_action.setStatusTip("Select all text")
        select_action.setShortcut(QtGui.QKeySequence.SelectAll)
        select_action.triggered.connect(self.editor.selectAll)
        edit_menu.addAction(select_action)

        edit_menu.addSeparator()
        edit_toolbar.addSeparator()
        
        find_action = QtGui.QAction(qta.icon('mdi.magnify', color=icon_color), "Find and Replace", self)
        find_action.setStatusTip("Find (and replace) text")
        find_action.setToolTip("Find (and replace) text")
        find_action.setShortcuts([QtGui.QKeySequence.Find, QtGui.QKeySequence.Replace])
        find_action.triggered.connect(self.open_find_replace_dialog)
        edit_toolbar.addAction(find_action)
        edit_menu.addAction(find_action)
                
        edit_menu.addSeparator()
        edit_toolbar.addSeparator()
        
        zoomIn_action = QtGui.QAction(qta.icon('mdi.plus-circle-outline', color=icon_color), "Zoom in", self)
        zoomIn_action.setStatusTip("Zoom in")
        zoomIn_action.setShortcut(QtGui.QKeySequence.ZoomIn)
        zoomIn_action.triggered.connect(self.editor.zoomIn)
        edit_toolbar.addAction(zoomIn_action)
        edit_menu.addAction(zoomIn_action)

        zoomOut_action = QtGui.QAction(qta.icon('mdi.minus-circle-outline', color=icon_color), "Zoom out", self)
        zoomOut_action.setStatusTip("Zoom out")
        zoomOut_action.setShortcut(QtGui.QKeySequence.ZoomOut)
        zoomOut_action.triggered.connect(self.editor.zoomOut)
        edit_toolbar.addAction(zoomOut_action)
        edit_menu.addAction(zoomOut_action)

        format_toolbar = QtWidgets.QToolBar("Format")
        format_toolbar.setMovable(False)
        format_toolbar.setIconSize(QtCore.QSize(24, 24))
        format_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.addToolBar(format_toolbar)
        format_menu = self.menuBar().addMenu("&Format")

        # We need references to these actions/settings to update as selection changes, so attach to self.
        self.bold_action = QtGui.QAction(qta.icon('mdi.format-bold', color=icon_color), "Bold", self)
        self.bold_action.setStatusTip("Bold")
        self.bold_action.setShortcut(QtGui.QKeySequence.Bold)
        self.bold_action.setCheckable(True)
        self.bold_action.toggled.connect(lambda x: self.editor.setFontWeight(QtGui.QFont.Bold if x else QtGui.QFont.Normal))
        format_toolbar.addAction(self.bold_action)
        format_menu.addAction(self.bold_action)

        self.italic_action = QtGui.QAction(qta.icon('mdi.format-italic', color=icon_color), "Italic", self)
        self.italic_action.setStatusTip("Italic")
        self.italic_action.setShortcut(QtGui.QKeySequence.Italic)
        self.italic_action.setCheckable(True)
        self.italic_action.toggled.connect(self.editor.setFontItalic)
        format_toolbar.addAction(self.italic_action)
        format_menu.addAction(self.italic_action)

        self.underline_action = QtGui.QAction(qta.icon('mdi.format-underline', color=icon_color), "Underline", self)
        self.underline_action.setStatusTip("Underline")
        self.underline_action.setShortcut(QtGui.QKeySequence.Underline)
        self.underline_action.setCheckable(True)
        self.underline_action.toggled.connect(self.editor.setFontUnderline)
        format_toolbar.addAction(self.underline_action)
        format_menu.addAction(self.underline_action)

        format_menu.addSeparator()
        format_toolbar.addSeparator()

        self.alignl_action = QtGui.QAction(qta.icon('mdi.format-align-left', color=icon_color), "Align left", self)
        self.alignl_action.setStatusTip("Align text left")
        self.alignl_action.setCheckable(True)
        self.alignl_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignLeft))
        format_toolbar.addAction(self.alignl_action)
        format_menu.addAction(self.alignl_action)

        self.alignc_action = QtGui.QAction(qta.icon('mdi.format-align-center', color=icon_color), "Align center", self)
        self.alignc_action.setStatusTip("Align text center")
        self.alignc_action.setCheckable(True)
        self.alignc_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignCenter))
        format_toolbar.addAction(self.alignc_action)
        format_menu.addAction(self.alignc_action)

        self.alignr_action = QtGui.QAction(qta.icon('mdi.format-align-right', color=icon_color), "Align right", self)
        self.alignr_action.setStatusTip("Align text right")
        self.alignr_action.setCheckable(True)
        self.alignr_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignRight))
        format_toolbar.addAction(self.alignr_action)
        format_menu.addAction(self.alignr_action)

        self.alignj_action = QtGui.QAction(qta.icon('mdi.format-align-justify', color=icon_color), "Justify", self)
        self.alignj_action.setStatusTip("Justify text")
        self.alignj_action.setCheckable(True)
        self.alignj_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignJustify))
        format_toolbar.addAction(self.alignj_action)
        format_menu.addAction(self.alignj_action)

        format_group = QtGui.QActionGroup(self)
        format_group.setExclusive(True)
        format_group.addAction(self.alignl_action)
        format_group.addAction(self.alignc_action)
        format_group.addAction(self.alignr_action)
        format_group.addAction(self.alignj_action)

        format_menu.addSeparator()
        format_toolbar.addSeparator()
        
        # A list of all format-related widgets/actions, so we can disable/enable signals when updating.
        self._format_actions = [
            self.bold_action,
            self.italic_action,
            self.underline_action,
            # We don't need to disable signals for alignment, as they are paragraph-wide.
        ]     
                        
        # Initialize
        self.cursor_changed()
        self.update_title()
        self.setWindowIcon(QtGui.QIcon(os.path.join(app_dir, 'noScribeEditLogo.png')))

        # make the window at least 700 x 900
        if self.height() < 700:
            self.resize(self.width(), 700)
        if self.width() < 900:
            self.resize(900, self.height())
        self.show()
        if len(sys.argv) > 1:
            QtCore.QTimer.singleShot(0, lambda: self._file_open(sys.argv[1])) # show the main window before loading the transcript
        
    def block_signals(self, objects, b):
        for o in objects:
            o.blockSignals(b)

    def cursor_changed(self):
        if not self.keep_playing:
            # show current audio timestamp in status:
            cr = self.editor.textCursor()
            ts = cr.charFormat().anchorHref()
            try:
                start, stop = decode_timestamp(ts)
                self.timestamp_status.setText('♪ ' + timestamp_to_string(start, stop))
            except:
                self.timestamp_status.setText('')
        else:
            self.keep_playing = False # stop playing if user moves the cursor
        
        # Update the font format toolbar/actions when a new text selection is made. This is neccessary to keep
        # toolbars/etc. in sync with the current edit state.
        
        # Disable signals for all format widgets, so changing values here does not trigger further formatting.
        self.block_signals(self._format_actions, True)

        self.italic_action.setChecked(self.editor.fontItalic())
        self.underline_action.setChecked(self.editor.fontUnderline())
        self.bold_action.setChecked(self.editor.fontWeight() == QtGui.QFont.Bold)
        
        self.alignl_action.setChecked(self.editor.alignment() == QtCore.Qt.AlignLeft)
        self.alignc_action.setChecked(self.editor.alignment() == QtCore.Qt.AlignCenter)
        self.alignr_action.setChecked(self.editor.alignment() == QtCore.Qt.AlignRight)
        self.alignj_action.setChecked(self.editor.alignment() == QtCore.Qt.AlignJustify)
        
        self.block_signals(self._format_actions, False)
        
    def init_recent_files_menu(self):
        self.recent_files_menu = self.menuBar().addMenu("Open Recent")
        self.recent_file_actions = []  # Store actions to keep references

        # Load recent files from config
        recent_files = config.get('recent_files', [])

        for filepath in recent_files:
            if os.path.exists(filepath):  # Ensure the file still exists
                action = QtGui.QAction(filepath, self)
                action.triggered.connect(lambda checked, p=filepath: self._file_open(p))
                self.recent_files_menu.addAction(action)
                self.recent_file_actions.append(action)
                
    def update_recent_files_menu(self):
        self.recent_files_menu.clear()
        recent_files = config.get('recent_files', [])

        for filepath in recent_files:
            if os.path.exists(filepath):
                filename = os.path.basename(filepath)
                action = QtGui.QAction(filename, self)
                # Use lambda to pass full path to the handler
                action.triggered.connect(lambda checked, p=filepath: self._file_open(p))
                self.recent_files_menu.addAction(action)   
                 
    def dialog(self, s):
        dlg = QtWidgets.QMessageBox(self)
        dlg.setIcon(QtWidgets.QMessageBox.Information)
        dlg.setText(s)
        dlg.show()

    def dialog_critical(self, s):
        dlg = QtWidgets.QMessageBox(self)
        dlg.setText(s)
        dlg.setIcon(QtWidgets.QMessageBox.Critical)
        dlg.show()

    def _file_open(self, path):
        try:
            try:
                with open(path, 'r', encoding="utf-8") as f:
                    htmlStr = f.read()
            except: # try utf-16 encoding (word writes html-files like this)
                with open(path, 'r', encoding="utf-16") as f:
                    htmlStr = f.read()
                
            self.path = path
            update_recent_files(path)
            self.update_recent_files_menu()  # Refresh recent files menu            

            self.editor.clear()
            self.audio_source = None
            self.tmp_audio_file = None
            self.status.showMessage("Loading... please wait.")
            # avoid that all anchors become formatted as underlined and blue 
            doc = self.editor.document()
            doc.setDefaultStyleSheet("a {color: #000000; text-decoration: none; }")
            # reset the font:
            font_size = self.editor.font().pointSize()
            font = QtGui.QFont(default_font, font_size, QtGui.QFont.Weight.Normal, False)
            self.editor.setCurrentFont(font)
            self.editor.setText("Loading... please wait.")
            QtWidgets.QApplication.processEvents() # update GUI
            
            # QTextEdit does not understand "font-size: 0.8em", only "small":
            htmlStr = htmlStr.replace('font-size: 0.8em', 'font-size: small')
            
            parser = AdvancedHTMLParser.AdvancedHTMLParser()
            parser.parseStr(htmlStr)    
            
            try:       
                # save timestamps from name to href-attribute because QTextEdit does not handle ankers with only the name-attribute well:
                for anker in parser.getElementsByTagName('a'):
                    anker_name = str(anker.name)
                    if (anker_name != None) and (anker_name.startswith('ts_')):
                        anker.href = anker_name
                        anker.removeAttribute('name')

                # get path to audio source from html:
                tags = parser.head.getElementsByName("audio_source")
                if (len(tags) == 0) or (not os.path.exists(tags[0].content)): # audio source moved or missing
                    ret = QtWidgets.QMessageBox.warning(self, "noScribeEdit", 
                                                "Audio source file not found.\n"
                                                "Do you want to search for it?",
                                                QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel, 
                                                QtWidgets.QMessageBox.Ok)
                    if ret == QtWidgets.QMessageBox.Cancel:
                        self.status.clearMessage()
                        return
                    else:
                        if not self.open_audio_source():
                            self.status.clearMessage()
                            return
                else:
                    self.audio_source = tags[0].content
                    if not self._load_audio():
                        self.audio_source = None
                                    
            finally:                
                # load html into the editor (do this even if loadig the audio fails)
                htmlStr = parser.asHTML()
                doc.setHtml(htmlStr)
                # move to the beginning
                cr = self.editor.textCursor()
                cr.setPosition(0)
                self.editor.setTextCursor(cr)
            
                doc.clearUndoRedoStacks()
                doc.setModified(False)
                
                self.update_title()
                self.status.clearMessage()
                    
        except Exception as e:
            self.status.clearMessage()
            self.dialog_critical(str(e))
            
    def _load_audio(self):
            if self.audio_source == '' or not os.path.exists(self.audio_source):
                return
            # create tmp wav-file (allows for more precise seeking compared with many other formats)
            self.tmpdir = TemporaryDirectory('noScribe')
            self.tmp_audio_file = os.path.join(self.tmpdir.name, 'tmp_editaudio.wav')
            res = ''
            try:
                if platform.system() == 'Windows':
                    ffmpeg_abspath = os.path.join(app_dir, 'ffmpeg_win', 'ffmpeg.exe')
                elif platform.system() == 'Darwin': # = MAC
                    ffmpeg_abspath = os.path.join(app_dir, 'ffmpeg_mac', 'ffmpeg')
                elif platform.system() == 'Linux': # = MAC
                    ffmpeg_abspath = os.path.join(app_dir, 'ffmpeg_linux', 'ffmpeg')
                else:
                    raise Exception('Platform not supported yet.')
                if not os.path.exists(ffmpeg_abspath):
                    raise Exception('Ffmpeg not found.')
                
                ffmpeg_cmd = f'{ffmpeg_abspath} -hwaccel auto -loglevel error -i "{self.audio_source}" -vn -sn -y "{self.tmp_audio_file}"'
                print(ffmpeg_cmd)
                
                if platform.system() == 'Windows':
                    # (supresses the terminal, see: https://stackoverflow.com/questions/1813872/running-a-process-in-pythonw-with-popen-without-a-console)
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    ffmpeg = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, encoding='UTF-8',  startupinfo=startupinfo, close_fds=True)
                elif platform.system() in ('Darwin', 'Linux'): # = MAC
                    ffmpeg_cmd = shlex.split(ffmpeg_cmd)
                    ffmpeg = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, encoding='UTF-8', close_fds=True)
                else:
                    raise Exception('Platform not supported yet.')

                while ffmpeg.poll() == None: 
                    sleep(0.1) # wait for ffmpeg to terminate
                (out, err) = ffmpeg.communicate()
                print(out)
                print(err)
                if err != '':
                    raise RuntimeError(f'FFmpeg error: {err}')
                                
                return True
            except Exception as e:
                self.dialog_critical(f'Error creating temporary audio file.\n {e}\n{res}')
                return False

    def file_open(self):
        if self.editor.document().isModified():
            ret = QtWidgets.QMessageBox.warning(self, "noScribeEdit", 
                                                "The document has been modified.\n"
                                                "Do you want to save your changes?",
                                                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard
                                                | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Save)
            if ret == QtWidgets.QMessageBox.Save:
                self.file_save()
            elif ret == QtWidgets.QMessageBox.Cancel:
                return
            
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open file", "", "noScribe Transcripts (*.html)")
        if path == "": # cancled
            return
        else:
            self._file_open(path)


    def _file_save(self, path):
        # Prepare the html:
        htmlStr = self.editor.toHtml()
        parser = AdvancedHTMLParser.AdvancedHTMLParser()
        parser.parseStr(htmlStr)
        
        # save timestamps back into the name attribute:
        for anker in parser.getElementsByTagName('a'):
            anker_href = str(anker.href)
            if (anker_href != None) and (anker_href.startswith('ts_')):
                anker.name = anker_href
                anker.removeAttribute('href')
        
        # add UTF-8 charset attribute
        meta_tag = parser.createElement("meta")
        meta_tag.charset = "UTF-8"
        parser.head.appendChild(meta_tag)

        # add audio file path:
        if self.audio_source:
            audio_tag = parser.createElement("meta")
            audio_tag.name = "audio_source"
            audio_tag.content = self.audio_source
            parser.head.appendChild(audio_tag)

        # add css-styles, especially for MS Word
        meta_tag = parser.createElement("style")
        meta_tag.type = "text/css"
        meta_tag.appendInnerHTML(' a { text-decoration: none; } ')
        meta_tag.appendInnerHTML(' p { font-size: 0.9em; } ')
        meta_tag.appendInnerHTML(' .MsoNormal { font-family: "Arial"; font-weight: 400; font-style: normal; font-size: 0.9em; }')
        meta_tag.appendInnerHTML(' @page WordSection1 {mso-line-numbers-restart: continuous; mso-line-numbers-count-by: 1; mso-line-numbers-start: 1; }')
        meta_tag.appendInnerHTML(' div.WordSection1 {page:WordSection1;} ')
        parser.head.appendChild(meta_tag)
        
        # body_children = parser.body.children
        div_tag = parser.createElement('div')
        div_tag.addClass('WordSection1')
        for child in parser.body.getChildren():
            child.remove()
            div_tag.appendChild(child)
        parser.body.appendChild(div_tag)
 
        # reset zoom (font-size):
        parser.body.setStyle("font-size", "")

        htmlStr = parser.asHTML()
        # replace "small" font size by "0.8em" (for word): 
        htmlStr = htmlStr.replace('font-size: small', 'font-size: 0.8em')
        while htmlStr.find('\n\n') > -1:
            htmlStr = htmlStr.replace('\n\n', '\n')
        
        file_ext = os.path.splitext(path)[1][1:]
        if file_ext == 'html':
            file_txt = htmlStr
        elif file_ext == 'txt':
            d = AdvancedHTMLParser.AdvancedHTMLParser()
            d.parseStr(htmlStr)
            file_txt = html_to_text(d)
        elif file_ext == 'vtt':
            d = AdvancedHTMLParser.AdvancedHTMLParser()
            d.parseStr(htmlStr)
            media_path = self.audio_source if self.audio_source is not None else ''
            file_txt = html_to_webvtt(d, media_path)
        else:
            raise TypeError(f'Invalid file type "{self.file_ext}".')

        with open(path, 'w', encoding="utf-8") as f:
            f.write(file_txt)
        self.editor.document().setModified(False)
            
    def file_save(self):
        if self.path is None:
            # If we do not have a path, we need to use Save As.
            return self.file_saveas()

        try:
            self._file_save(self.path)
        except Exception as e:
            self.dialog_critical(str(e))

    def file_saveas(self):
        filter_string = (
            "noScribe Transcript (*.html);;"
            "Text only (*.txt);;"
            "WebVTT Subtitles (also for EXMARaLDA) (*.vtt)"
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save file", self.path, filter_string, "noScribe Transcript (*.html)"
        )
        if path == "": # canceled
            return
        try:
            self._file_save(path)
        except Exception as e:
            self.dialog_critical(str(e))
        else:
            self.path = path
            self.update_title()
            
    def open_audio_source(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Audio source of the transcript", self.audio_source, "All (*.*)")
        if not path: # dialog is cancelled
            return False
        else:
            if not os.path.exists(path):
                self.dialog_critical("File does not exist: " + path)
                return False    
            self.status.showMessage("Loading... please wait.")
            self.audio_source = path
            ret = self._load_audio()                 
            self.status.clearMessage()
            self.editor.document().setModified(True)            
            return ret

    def select_current_segment(self):
        # Expands the selection so that it includes the whole transcript segment with the current timestamp
        # Returns False if no timestamp is found, True if succesful   
        
        cr = self.editor.textCursor()
        cr.clearSelection()
        ts = cr.charFormat().anchorHref()
        if ts == '':
            return False
        else:
            try:
                decode_timestamp(ts)
            except:
                return False # no valid timestamp
        
        # move to the left until the beginning of the segment is reached 
        chars_left = 0
        while cr.movePosition(QtGui.QTextCursor.MoveOperation.Left, QtGui.QTextCursor.MoveMode.MoveAnchor, 1):
            if cr.charFormat().anchorHref() == ts: 
                chars_left += 1
            else:
                break
                
        # move to the right until the end of the segment is reached 
        cr = self.editor.textCursor()
        cr.clearSelection()
        chars_right = 0
        while cr.movePosition(QtGui.QTextCursor.MoveOperation.Right, QtGui.QTextCursor.MoveMode.MoveAnchor, 1):
            if cr.charFormat().anchorHref() == ts: 
                chars_right += 1
            else:
                break
        
        seg = self.editor.textCursor()
        seg.clearSelection()
        seg.movePosition(QtGui.QTextCursor.MoveOperation.Left, QtGui.QTextCursor.MoveMode.MoveAnchor, chars_left)
        seg.movePosition(QtGui.QTextCursor.MoveOperation.Right, QtGui.QTextCursor.MoveMode.KeepAnchor, chars_left + chars_right)
        self.editor.setTextCursor(seg)
        return True
    
    def find_segment(self, a_time, search_dir="right"):
        # goes through the text in the given direction starting from the current selection  
        # and stops when a timestamp is found that includes a_time. The found segment is selected.
        # If a_time is None, the function looks for the first segment with any valid timestamp. 
        # Returns start, stop if found, -1, -1 otherwise
        cr = self.editor.textCursor()
        cr.clearSelection()
        cf = cr.charFormat()
        ts = cf.anchorHref()
        if ts != '':
            start, stop = decode_timestamp(ts)
        else:
            start = -1 
            stop = -1

        while (a_time == None and start == -1) or (a_time != None and not((a_time >= start) and (a_time <= stop))):
            if search_dir == "right":
                if not cr.movePosition(QtGui.QTextCursor.MoveOperation.Right, QtGui.QTextCursor.MoveMode.MoveAnchor, 1):
                    break # stop when cursor cannot be moved anymore (EOF)
            elif search_dir == "left":
                if not cr.movePosition(QtGui.QTextCursor.MoveOperation.Left, QtGui.QTextCursor.MoveMode.MoveAnchor, 1):
                    break
            cf = cr.charFormat()
            ts = cf.anchorHref()
            if ts != '':
                start, stop = decode_timestamp(ts)
            else:
                start = -1
                stop = -1
        if (a_time == None and start > -1) or (a_time != None and (a_time >= start) and (a_time <= stop)): # found, select the whole segment
            self.editor.setTextCursor(cr)
            if self.select_current_segment():
                return start, stop
            else:
                return -1, -1
        else:
            return -1, -1    
               
    def play_along(self):
        if self.keep_playing: # function already running, stop it
            self.keep_playing = False
            return
        
        try:
            if not self.tmp_audio_file: # audio source moved or missing
                ret = QtWidgets.QMessageBox.warning(self, "noScribeEdit", 
                                            "Audio source file not found.\n"
                                            "Do you want to search for it?",
                                            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel, 
                                            QtWidgets.QMessageBox.Ok)
                if ret == QtWidgets.QMessageBox.Cancel:
                    return
                else:
                    if not self.open_audio_source():
                        return
                        
            cr = self.editor.textCursor()
            cf = cr.charFormat()
            ts = cf.anchorHref()
                
            try:
                start, stop = decode_timestamp(ts)
            except:
                ret = QtWidgets.QMessageBox.warning(self, "noScribeEdit", 
                                    "No audio timestamp found for current selection.\n"
                                    "Do you want to start from the beginning?",
                                    QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel, 
                                    QtWidgets.QMessageBox.Ok)
                if ret == QtWidgets.QMessageBox.Cancel:
                    return
                else:
                    # move to the beginning
                    cr = self.editor.textCursor()
                    cr.setPosition(0)
                    self.editor.setTextCursor(cr)
                    # search first segment
                    start, stop = self.find_segment(None)
                    if start == -1:
                        raise Exception("No audio timestamps found in this document.")

            if not self.select_current_segment():
                raise Exception("No audio timestamps found in current selection.")
            speed = int(self.playback_speed.currentText()[:-1])
                            
            # play audio
            self.playback_start_pos = start
            self.keep_playing = True

            if platform.system() == 'Windows':
                ffplay_abspath = os.path.join(app_dir, 'ffmpeg_win', 'ffplay.exe')
            elif platform.system() == 'Darwin': # = MAC
                ffplay_abspath = os.path.join(app_dir, 'ffmpeg_mac', 'ffplay')
            elif platform.system() == 'Linux': # = MAC
                ffplay_abspath = os.path.join(app_dir, 'ffmpeg_linux', 'ffplay')
            else:
                raise Exception('Platform not supported yet.')
            if not os.path.exists(ffplay_abspath):
                raise Exception('FFPlay not found.')
            
            ffplay_cmd = f'{ffplay_abspath} -loglevel error -vn -sn -ss {start}ms -nodisp -af "atempo={speed/100}" "{self.tmp_audio_file}"'
            print(ffplay_cmd)
            
            if platform.system() == 'Windows':
                # (supresses the terminal, see: https://stackoverflow.com/questions/1813872/running-a-process-in-pythonw-with-popen-without-a-console)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.media_player = subprocess.Popen(ffplay_cmd, stderr=subprocess.PIPE, encoding='UTF-8', startupinfo=startupinfo, close_fds=True)
            elif platform.system() in ('Darwin', 'Linux'): # = MAC
                ffplay_cmd = shlex.split(ffplay_cmd)
                self.media_player = subprocess.Popen(ffplay_cmd, stderr=subprocess.PIPE, encoding='UTF-8', close_fds=True)
            else:
                raise Exception('Platform not supported yet.')
            
            self.playback_start_time = datetime.now()

            self.play_along_action.blockSignals(True) 
            self.play_along_action.setChecked(True)
            self.play_along_action.blockSignals(False)
                    
            while self.keep_playing:
                if self.media_player.poll() != None: # ffplay terminated
                    (out, err) = self.media_player.communicate()
                    if err != '':
                        raise Exception(f'FFPlay error: {err}')
                    else:
                        break
                
                audio_playback_time = round((datetime.now() - self.playback_start_time).total_seconds() * 1000 * (speed / 100)) # im ms
                # audio_playback_time = round((datetime.now() - self.playback_start_time).total_seconds() * 1000) # im ms
                curr_audio_pos = self.playback_start_pos + audio_playback_time
                
                new_speed = int(self.playback_speed.currentText()[:-1])
                if new_speed != speed: # user changed playback speed
                    self.media_player.kill()
                    speed = new_speed
                    ffplay_cmd = f'{ffplay_abspath} -loglevel error -vn -sn -ss {curr_audio_pos}ms -nodisp -af "atempo={speed/100}" "{self.tmp_audio_file}"'
                    if platform.system() in ('Darwin', 'Linux'): # = MAC
                        ffplay_cmd = shlex.split(ffplay_cmd)
                    self.media_player = subprocess.Popen(ffplay_cmd, stderr=subprocess.PIPE, encoding='UTF-8', close_fds=True)                   
                    self.playback_start_pos = curr_audio_pos
                    self.playback_start_time = datetime.now()                       

                if curr_audio_pos > stop: # go to next segment in transcript
                    try:
                        new_start, new_stop = self.find_segment(curr_audio_pos)
                        if new_start > -1: #found
                            start = new_start
                            stop = new_stop
                        else:
                            # no segment found, deselect all
                            cr = self.editor.textCursor()
                            cr.clearSelection()
                            self.editor.setTextCursor(cr) 
                        self.keep_playing = True                            
                    except:
                        self.keep_playing = False # stop playing along  
                sleep(0.01)
                self.play_along_action.blockSignals(True) 
                self.play_along_action.setChecked(self.keep_playing)
                self.play_along_action.blockSignals(False)
                self.timestamp_status.setText('♪ ' + ms_to_str(curr_audio_pos))
                QtWidgets.QApplication.processEvents() # update GUI
        
        except Exception as e:
            self.dialog_critical(str(e))
        
        finally:
            if self.media_player:
                self.media_player.kill()
                self.media_player = None
            self.keep_playing = False
            self.play_along_action.blockSignals(True) 
            self.play_along_action.setChecked(False)
            self.play_along_action.blockSignals(False)
            self.cursor_changed()           

    def closeEvent(self, event):
        self.keep_playing = False
                    
        if self.editor.document().isModified():
            ret = QtWidgets.QMessageBox.warning(self, "noScribeEdit", 
                                                "The document has been modified.\n"
                                                "Do you want to save your changes?",
                                                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard
                                                | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Save)
            if ret == QtWidgets.QMessageBox.Save:
                self.file_save()
            elif ret == QtWidgets.QMessageBox.Cancel:
                event.ignore()
                return
        
        if self.media_player:
            self.media_player.kill()
            self.media_player = None
        
        # Save current zoom level
        font = self.editor.font()
        size = font.pointSize()
        config['editor_zoom'] = str(size)
        
        # Save window geometry
        config['window_geometry'] = self.saveGeometry().toHex().data().decode('utf-8')
        
        with open(config_file, 'w') as file:
            yaml.safe_dump(config, file)

        event.accept()

    def update_title(self):
        self.setWindowTitle("%s - noScribeEdit" % (os.path.basename(self.path) if self.path else "Untitled"))

    def open_find_replace_dialog(self):
        self.search_replace_dialog = SearchAndReplaceDialog(self)
        self.search_replace_dialog.show()
        
    def highlight_matches(self, text, case_sensitive, whole_word):
        selections = []  # List to hold the extra selections

        # Define the highlight format
        highlight_format = QtGui.QTextCharFormat()
        highlight_format.setBackground(QtGui.QBrush(QtGui.QColor("#ffff00")))  # Yellow highlight

        # Set the appropriate search flags
        flags = QtGui.QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QtGui.QTextDocument.FindCaseSensitively
        if whole_word:
            flags |= QtGui.QTextDocument.FindWholeWords

        # Start the search from the beginning of the document
        cursor = self.editor.textCursor()
        cursor.setPosition(0)
        document = self.editor.document()

        # Search for the text and collect selections to highlight
        while not cursor.isNull() and not cursor.atEnd():
            cursor = document.find(text, cursor, flags)
            if cursor.isNull():
                break  # Exit if no more matches found

            # Create an extra selection for each match
            selection = QtWidgets.QTextEdit.ExtraSelection()
            selection.format = highlight_format
            selection.cursor = cursor
            selections.append(selection)

        # Apply all the selections to the editor
        self.editor.setExtraSelections(selections)
        
    def remove_highlight_matches(self):
        # Clear extra selections to remove highlights
        self.editor.setExtraSelections([])
    
    def find_next(self, text, case_sensitive, whole_word):
        if text == '':
            self.dialog_critical('Search text is empty!')
            return
        flags = QtGui.QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QtGui.QTextDocument.FindCaseSensitively
        if whole_word:
            flags |= QtGui.QTextDocument.FindWholeWords

        document = self.editor.document()
        cursor = self.editor.textCursor()
        found_cursor = document.find(text, cursor, flags)

        if found_cursor.isNull():
            # Ask if the user wants to continue searching from the top.
            ret = QtWidgets.QMessageBox.question(
                self, "Find", "Reached the end of the document. Continue from the beginning?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
            )

            if ret == QtWidgets.QMessageBox.Yes:
                # Search from the beginning
                start_cursor = QtGui.QTextCursor(document)
                found_cursor = document.find(text, start_cursor, flags)
                if found_cursor.isNull():
                    QtWidgets.QMessageBox.information(
                        self, "Find", "No more occurrences found."
                    )
                    return
            else:
                return

        self.editor.setTextCursor(found_cursor)
        self.editor.ensureCursorVisible()
        # reposition the dialog if it overlaps the cursor
        self.reposition_dialog_if_necessary()
            
    def replace(self, text, replace_with, case_sensitive, whole_word):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            selected_text = cursor.selectedText()
            if (case_sensitive and selected_text == text) or (not case_sensitive and selected_text.lower() == text.lower()):
                cursor.insertText(replace_with)
                self.editor.setTextCursor(cursor)
        self.find_next(text, case_sensitive, whole_word)
        QtWidgets.QApplication.processEvents()
        
    def replace_in_anchor_hrefs(self, old: str, new: str, case_sensitive: bool) -> int:
        """
        Helper function that replaces `old` with `new` inside every <a> tag's href in a QTextEdit.
        Returns the number of hrefs changed.
        """

        TS_HREF_RX = re.compile(r'^ts_(\d+)_(\d+)_(.+)$')


        def _updated_href(href: str, old: str, new: str, case_sensitive: bool) -> str | None:
            m = TS_HREF_RX.match(href or "")
            if not m:
                return None
            n1, n2, tail = m.groups()

            if case_sensitive:
                # direct replacement
                if old not in tail:
                    return None
                return f"ts_{n1}_{n2}_{tail.replace(old, new)}"
            else:
                # case-insensitive check & replace
                # re.escape ensures we only match the literal string `old`
                pattern = re.compile(re.escape(old), re.IGNORECASE)
                if not pattern.search(tail):
                    return None
                return f"ts_{n1}_{n2}_{pattern.sub(new, tail)}"

        doc = self.editor.document()
        changes = []  # list of (start_pos, end_pos_exclusive, new_href)
 
        # Pass 1: collect contiguous anchor ranges to change
        block = doc.begin()
        while block.isValid():
            # Materialize fragments of this block so we can index/peek ahead.
            frags = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    frags.append((
                        frag.position(),
                        frag.length(),
                        frag.charFormat()
                    ))
                it += 1

            i = 0
            n = len(frags)
            while i < n:
                pos, length, fmt = frags[i]
                if not fmt.isAnchor():
                    i += 1
                    continue

                href = fmt.anchorHref()
                updated = _updated_href(href, old, new, case_sensitive)
                if updated is None or updated == href:
                    i += 1
                    continue

                # Group contiguous fragments that share the same href
                start = pos
                end = pos + length
                j = i + 1
                while j < n:
                    p2, l2, f2 = frags[j]
                    if not f2.isAnchor() or f2.anchorHref() != href:
                        break
                    end = p2 + l2
                    j += 1

                changes.append((start, end, updated))
                i = j  # skip the grouped run

            block = block.next()

        if not changes:
            return 0

        # Pass 2: apply from right to left (safer for positions)
        changed_count = 0
        for start, end, new_href in sorted(changes, key=lambda t: t[0], reverse=True):
            cursor = QtGui.QTextCursor(doc)
            cursor.setPosition(start)
            cursor.setPosition(end, QtGui.QTextCursor.MoveMode.KeepAnchor)

            fmt: QtGui.QTextCharFormat = cursor.charFormat()
            # If selection spans multiple formats, mergeCharFormat will apply to all.
            # Make sure it's an anchor and only update the href field.
            if not fmt.isAnchor():
                # Defensive: if mixed selection, force anchor flag on to preserve href
                fmt.setAnchor(True)
            fmt.setAnchorHref(new_href)
            cursor.mergeCharFormat(fmt)
            changed_count += 1

        return changed_count

    def replace_all(self, text: str, replace_with: str, case_sensitive: bool, whole_word: bool):
        if text == '':
            self.dialog_critical('Search text is empty!')
            return
        flags = QtGui.QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QtGui.QTextDocument.FindCaseSensitively
        if whole_word:
            flags |= QtGui.QTextDocument.FindWholeWords

        start_cursor = QtGui.QTextCursor(self.editor.document())
        found_cursor = self.editor.document().find(text, start_cursor, flags)
        while not found_cursor.isNull():            
            found_cursor.insertText(replace_with)
            found_cursor = self.editor.document().find(text, found_cursor, flags)
            
        # search & replace text also in html speaker markers
        spkr_text = text.strip().rstrip(':') # ignore whitespace and trailing colon in search and replace text
        spkr_replace_with = clean_vtt_voice(replace_with.strip().rstrip(':'))
        self.replace_in_anchor_hrefs(spkr_text, spkr_replace_with, case_sensitive)
                
    def reposition_dialog_if_necessary(self):
        if not self.search_replace_dialog.isVisible():
            return

        # Get the cursor rectangle and map it to global coordinates
        cursor_rect = self.editor.cursorRect()
        cursor_global_top_left = self.editor.mapToGlobal(cursor_rect.topLeft())
        cursor_global_bottom_right = self.editor.mapToGlobal(cursor_rect.bottomRight())
        cursor_global_rect = QtCore.QRect(cursor_global_top_left, cursor_global_bottom_right)

        # Get the dialog and screen geometry
        dialog_rect = self.search_replace_dialog.geometry()

        screen_geometry = QtWidgets.QApplication.instance().primaryScreen().geometry()

        # Check if the dialog overlaps the cursor
        if dialog_rect.intersects(cursor_global_rect):
            # Calculate new position to move the dialog out of the way
            new_x = dialog_rect.x()
            new_y = dialog_rect.y()

            # Move the dialog horizontally or vertically depending on space
            if cursor_global_rect.right() + dialog_rect.width() < screen_geometry.width():
                # Move dialog to the right of the text cursor
                new_x = cursor_global_rect.right() + 10
            elif cursor_global_rect.left() - dialog_rect.width() > 0:
                # Move dialog to the left of the text cursor
                new_x = cursor_global_rect.left() - dialog_rect.width() - 10

            if cursor_global_rect.bottom() + dialog_rect.height() < screen_geometry.height():
                # Move dialog below the text cursor
                new_y = cursor_global_rect.bottom() + 10
            elif cursor_global_rect.top() - dialog_rect.height() > 0:
                # Move dialog above the text cursor
                new_y = cursor_global_rect.top() - dialog_rect.height() - 10

            # Ensure the dialog remains within screen bounds
            new_x = max(min(new_x, screen_geometry.width() - dialog_rect.width()), 0)
            new_y = max(min(new_y, screen_geometry.height() - dialog_rect.height()), 0)

            self.search_replace_dialog.move(new_x, new_y)
            
class EnterKeyFilter(QtCore.QObject):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_Return:
            cursor = self.editor.textCursor()

            # Get the current block text and the position
            start_pos = cursor.position()
            cursor.select(QtGui.QTextCursor.SelectionType.BlockUnderCursor)
            current_block_text = cursor.selectedText()
            cursor.setPosition(start_pos)

            # Retrieve the speaker label from the previous block
            speaker_label = ''
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.StartOfBlock)
            if cursor.movePosition(QtGui.QTextCursor.MoveOperation.PreviousBlock):
                previous_block_text = cursor.block().text()
                if ':' in previous_block_text:
                    # Find the speaker label in the previous block
                    speaker_label = previous_block_text.split(':')[0]
                    if len(speaker_label) > 30: # too long, unlikely to be a speaker name
                        speaker_label = ''
                
            # Go back to the original cursor position, insert line break and speaker
            cursor.setPosition(start_pos)
                
            if speaker_label != '':
                cursor.insertText(f"\n{speaker_label}: ")
            else: 
                cursor.insertText('\n')
            
            # Update the cursor position after modifications
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.Right, 
                                QtGui.QTextCursor.MoveMode.KeepAnchor, 
                                len(speaker_label))
            self.editor.setTextCursor(cursor)

            return True  # Event is handled

        # Pass the event on to the parent class if it's not an Enter key press
        return QtCore.QObject.eventFilter(self, watched, event)           

        
if __name__ == '__main__':

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("noScribeEdit")
    app.setStyle("Fusion")
    window = MainWindow()
    
    app.exec_()
