# noScribe Editor 
# Part of noScribe, the AI-powered Audio Transcription
# Copyright (C) 2023 Kai Dröge
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

import qdarkstyle
import qtawesome as qta
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5 import QtCore
import platform
if platform.system() == 'Windows':
    import pywinstyles

import os
import sys
from ffpyplayer.player import MediaPlayer
from datetime import datetime
from time import sleep
import AdvancedHTMLParser

icon_color = '#aaaaaa'
icon_color_active = '#1f6aa5'
highlight_color = '#ff8c00'
default_font = "Arial"
default_font_size = "12pt"

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True) # enable highdpi scaling
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True) # use highdpi icons

# Helper functions

def decode_timestamp(ts):
    # return start, finish
    # example: "ts_1234_4321"
    if not ts:
        raise Exception("No timestamp found")
    ts_list = ts.split('_')
    if (len(ts_list) != 3) or (ts_list[0] != "ts"):
        raise Exception(f"Unable to decode timestamp <{ts}>")
    else:
        return int(ts_list[1]), int(ts_list[2]) 

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        
        self.media_player = None
        self.playback_speed = 150
        self.path = None # current file
        self.audio_source = None # corresponding audio file
        self.keep_playing = False # Stops the play_along-function when set to False 
        self.playing_error = None
        
        # GUI
        
        layout = QtWidgets.QVBoxLayout()
        
        # Editor:        
        self.editor = QtWidgets.QTextEdit()
        self.editor.setStyleSheet("QTextEdit {color: #000000; background-color: #ffffff; border: 0px;} QScrollBar::handle {background: #1f6aa5;}")
        self.editor.setAcceptRichText(True)
        self.editor.setAutoFormatting(QtWidgets.QTextEdit.AutoNone)
        self.editor.cursorPositionChanged.connect(self.cursor_changed)
        font = QtGui.QFont(default_font, 11)
        self.editor.setFont(font)
        layout.addWidget(self.editor)
        container = QtWidgets.QWidget()
        container.setStyleSheet("background-color: #ffffff; border-top: 1px solid #474747; border-bottom: 1px solid #474747")
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Status Bar
        self.status = QtWidgets.QStatusBar()
        self.status.setStyleSheet("background-color: #2b2b2b; border: 0px solid #474747")
        self.setStatusBar(self.status)

        # Toolbar
        
        # self.menuBar().setNativeMenuBar(False) # Uncomment to disable native menubar on Mac
        toolbar_stylesheet = "QToolBar {background-color: #2b2b2b; border-bottom: 0px  solid #474747; margin: 4px; } QToolButton:hover {background-color: #1f6aa5} QToolButton:checked {background-color: #474747}"

        file_toolbar = QtWidgets.QToolBar("File")
        file_toolbar.setMovable(False)
        file_toolbar.setIconSize(QtCore.QSize(24, 24))
        file_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        file_toolbar.setStyleSheet(toolbar_stylesheet)
        self.addToolBar(file_toolbar)
        file_menu = self.menuBar().addMenu("&File")

        open_file_action = QtWidgets.QAction(qta.icon('fa5s.folder-open', color=icon_color), "Open file...", self)
        open_file_action.setStatusTip("Open file")
        open_file_action.setShortcut(QtGui.QKeySequence.Open)
        open_file_action.triggered.connect(self.file_open)
        file_menu.addAction(open_file_action)
        file_toolbar.addAction(open_file_action)

        save_file_action = QtWidgets.QAction(qta.icon('fa5s.save', color=icon_color), "Save", self)
        save_file_action.setStatusTip("Save current file")
        save_file_action.setShortcut(QtGui.QKeySequence.Save)
        save_file_action.triggered.connect(self.file_save)
        file_menu.addAction(save_file_action)
        file_toolbar.addAction(save_file_action)

        saveas_file_action = QtWidgets.QAction(qta.icon('fa5.save', color=icon_color), "Save As...", self)
        saveas_file_action.setStatusTip("Save current file to specified file")
        saveas_file_action.triggered.connect(self.file_saveas)
        file_menu.addAction(saveas_file_action)
        #file_toolbar.addAction(saveas_file_action)
        
        file_menu.addSeparator()
        
        audio_source_action = QtWidgets.QAction(qta.icon('fa5s.file-audio', color=icon_color), "Audio source...", self)
        audio_source_action.setStatusTip("Locate the audio source file of the current transcript")
        audio_source_action.triggered.connect(self.open_audio_source)
        file_menu.addAction(audio_source_action)


        noScribe_toolbar = QtWidgets.QToolBar("noScribe")
        noScribe_toolbar.setMovable(False)
        noScribe_toolbar.setIconSize(QtCore.QSize(24, 24))
        noScribe_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        noScribe_toolbar.setStyleSheet(toolbar_stylesheet)
        self.addToolBar(noScribe_toolbar)
        # noScribe_menu = self.menuBar().addMenu("no&Scribe")
       
        self.play_along_action = QtWidgets.QAction(qta.icon('fa5s.volume-down', color=highlight_color), "Play Audio", self)      
        self.play_along_action.setCheckable(True)
        self.play_along_action.setStatusTip("Listen to the audio source of the current text")
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
        edit_toolbar.setStyleSheet(toolbar_stylesheet)
        self.addToolBar(edit_toolbar)
        edit_menu = self.menuBar().addMenu("&Edit")

        edit_menu.addAction(self.play_along_action)
        edit_menu.addSeparator()

        undo_action = QtWidgets.QAction(qta.icon('fa5s.undo', color=icon_color), "Undo", self)
        undo_action.setStatusTip("Undo last change")
        undo_action.setShortcut(QtGui.QKeySequence.Undo)
        undo_action.triggered.connect(self.editor.undo)
        edit_toolbar.addAction(undo_action)
        edit_menu.addAction(undo_action)

        redo_action = QtWidgets.QAction(qta.icon('fa5s.redo', color=icon_color), "Redo", self)
        redo_action.setStatusTip("Redo last change")
        redo_action.setShortcut(QtGui.QKeySequence.Redo)
        redo_action.triggered.connect(self.editor.redo)
        edit_toolbar.addAction(redo_action)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QtWidgets.QAction(qta.icon('fa5s.cut', color=icon_color), "Cut", self)
        cut_action.setStatusTip("Cut selected text")
        cut_action.setShortcut(QtGui.QKeySequence.Cut)
        cut_action.triggered.connect(self.editor.cut)
        edit_toolbar.addAction(cut_action)
        edit_menu.addAction(cut_action)

        copy_action = QtWidgets.QAction(qta.icon('fa5s.copy', color=icon_color), "Copy", self)
        copy_action.setStatusTip("Copy selected text")
        copy_action.setShortcut(QtGui.QKeySequence.Copy)
        copy_action.triggered.connect(self.editor.copy)
        edit_toolbar.addAction(copy_action)
        edit_menu.addAction(copy_action)

        paste_action = QtWidgets.QAction(qta.icon('fa5s.paste', color=icon_color), "Paste", self)
        paste_action.setStatusTip("Paste from clipboard")
        paste_action.setShortcut(QtGui.QKeySequence.Paste)
        paste_action.triggered.connect(self.editor.paste)
        edit_toolbar.addAction(paste_action)
        edit_menu.addAction(paste_action)

        select_action = QtWidgets.QAction("Select all", self)
        select_action.setStatusTip("Select all text")
        select_action.setShortcut(QtGui.QKeySequence.SelectAll)
        select_action.triggered.connect(self.editor.selectAll)
        edit_menu.addAction(select_action)

        edit_menu.addSeparator()
        
        zoomIn_action = QtWidgets.QAction(qta.icon('fa5s.search-plus', color=icon_color), "Zoom in", self)
        zoomIn_action.setStatusTip("Zoom in")
        zoomIn_action.setShortcut(QtGui.QKeySequence.ZoomIn)
        zoomIn_action.triggered.connect(self.editor.zoomIn)
        edit_toolbar.addAction(zoomIn_action)
        edit_menu.addAction(zoomIn_action)

        zoomOut_action = QtWidgets.QAction(qta.icon('fa5s.search-minus', color=icon_color), "Zoom out", self)
        zoomOut_action.setStatusTip("Zoom out")
        zoomOut_action.setShortcut(QtGui.QKeySequence.ZoomOut)
        zoomOut_action.triggered.connect(self.editor.zoomOut)
        edit_toolbar.addAction(zoomOut_action)
        edit_menu.addAction(zoomOut_action)


        format_toolbar = QtWidgets.QToolBar("Format")
        format_toolbar.setMovable(False)
        format_toolbar.setIconSize(QtCore.QSize(24, 24))
        format_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        format_toolbar.setStyleSheet(toolbar_stylesheet)
        self.addToolBar(format_toolbar)
        format_menu = self.menuBar().addMenu("&Format")

        # We need references to these actions/settings to update as selection changes, so attach to self.
        self.bold_action = QtWidgets.QAction(qta.icon('fa5s.bold', color=icon_color), "Bold", self)
        self.bold_action.setStatusTip("Bold")
        self.bold_action.setShortcut(QtGui.QKeySequence.Bold)
        self.bold_action.setCheckable(True)
        self.bold_action.toggled.connect(lambda x: self.editor.setFontWeight(QtGui.QFont.Bold if x else QtGui.QFont.Normal))
        format_toolbar.addAction(self.bold_action)
        format_menu.addAction(self.bold_action)

        self.italic_action = QtWidgets.QAction(qta.icon('fa5s.italic', color=icon_color), "Italic", self)
        self.italic_action.setStatusTip("Italic")
        self.italic_action.setShortcut(QtGui.QKeySequence.Italic)
        self.italic_action.setCheckable(True)
        self.italic_action.toggled.connect(self.editor.setFontItalic)
        format_toolbar.addAction(self.italic_action)
        format_menu.addAction(self.italic_action)

        self.underline_action = QtWidgets.QAction(qta.icon('fa5s.underline', color=icon_color), "Underline", self)
        self.underline_action.setStatusTip("Underline")
        self.underline_action.setShortcut(QtGui.QKeySequence.Underline)
        self.underline_action.setCheckable(True)
        self.underline_action.toggled.connect(self.editor.setFontUnderline)
        format_toolbar.addAction(self.underline_action)
        format_menu.addAction(self.underline_action)

        format_menu.addSeparator()

        self.alignl_action = QtWidgets.QAction(qta.icon('fa5s.align-left', color=icon_color), "Align left", self)
        self.alignl_action.setStatusTip("Align text left")
        self.alignl_action.setCheckable(True)
        self.alignl_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignLeft))
        format_toolbar.addAction(self.alignl_action)
        format_menu.addAction(self.alignl_action)

        self.alignc_action = QtWidgets.QAction(qta.icon('fa5s.align-center', color=icon_color), "Align center", self)
        self.alignc_action.setStatusTip("Align text center")
        self.alignc_action.setCheckable(True)
        self.alignc_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignCenter))
        format_toolbar.addAction(self.alignc_action)
        format_menu.addAction(self.alignc_action)

        self.alignr_action = QtWidgets.QAction(qta.icon('fa5s.align-right', color=icon_color), "Align right", self)
        self.alignr_action.setStatusTip("Align text right")
        self.alignr_action.setCheckable(True)
        self.alignr_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignRight))
        format_toolbar.addAction(self.alignr_action)
        format_menu.addAction(self.alignr_action)

        self.alignj_action = QtWidgets.QAction(qta.icon('fa5s.align-justify', color=icon_color), "Justify", self)
        self.alignj_action.setStatusTip("Justify text")
        self.alignj_action.setCheckable(True)
        self.alignj_action.triggered.connect(lambda: self.editor.setAlignment(QtCore.Qt.AlignJustify))
        format_toolbar.addAction(self.alignj_action)
        format_menu.addAction(self.alignj_action)

        format_group = QtWidgets.QActionGroup(self)
        format_group.setExclusive(True)
        format_group.addAction(self.alignl_action)
        format_group.addAction(self.alignc_action)
        format_group.addAction(self.alignr_action)
        format_group.addAction(self.alignj_action)

        format_menu.addSeparator()
        
        # A list of all format-related widgets/actions, so we can disable/enable signals when updating.
        self._format_actions = [
            self.bold_action,
            self.italic_action,
            self.underline_action,
            # We don't need to disable signals for alignment, as they are paragraph-wide.
        ]        
        
        # Initialize.
        self.cursor_changed()
        self.update_title()
        self.setWindowIcon(QtGui.QIcon('noScribeLogo.ico'))
        self.setStyleSheet("* {background-color: #2b2b2b;} QPushButton {background-color: #474747; }")

        if self.height() < 500:
            self.resize(self.width(), 500) # make it at least 500 pixel high
        self.show()
        if len(sys.argv) > 1:
            self._file_open(sys.argv[1])
        
    def block_signals(self, objects, b):
        for o in objects:
            o.blockSignals(b)

    def cursor_changed(self):
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
            
            self.editor.clear()
            self.audio_source = None
            self.status.showMessage("Loading... please wait.")
            # avoid that all anchors become formatted as underlined and blue 
            doc = self.editor.document()
            doc.setDefaultStyleSheet("a {color: #000000; text-decoration: none; }")
            # reset the font size/zoom:
            font = QtGui.QFont(default_font, 11)
            self.editor.setFont(font)
            QtWidgets.QApplication.processEvents() # update GUI

            # get path to audio source from html:
            parser = AdvancedHTMLParser.AdvancedHTMLParser()
            parser.parseStr(htmlStr)           
            tags = parser.head.getElementsByName("audio_source")
            if len(tags) > 0: 
                self.audio_source = tags[0].content                

            # load html into the editor
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
            self.dialog_critical(str(e))

    def file_open(self):
        if self.editor.document().isModified():
            ret = QtWidgets.QMessageBox.warning(self, "noScribe Editor", 
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
        with open(path, 'w', encoding="utf-8") as f:
            f.write(htmlStr)
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
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save file", "", "noScribe Transcripts (*.html)")
        if path == "": # cancled
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
            self.status.clearMessage()
            self.editor.document().setModified(True)
            return True

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
        
    def ffplay_callback(self, selector, value):
        if selector in ['audio:error', 'video:error', 'subtitle:error', 'read:error']:
            self.playing_error = "Error playing audio file\n" + value
            self.keep_playing = False

        elif selector == 'eof':
            self.keep_playing = False
            
    def play_along(self):
        if self.keep_playing: # function already running, stop it
            self.keep_playing = False
            return
        
        try:
            if (not self.audio_source) or (not os.path.exists(self.audio_source)): # audio source moved or missing
                ret = QtWidgets.QMessageBox.warning(self, "noScribe Editor", 
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
                ret = QtWidgets.QMessageBox.warning(self, "noScribe Editor", 
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
            self.playing_error = None
            self.keep_playing = True
            
            ff_opts = {'ss': start / 1000, 'af':'atempo=' + str(speed / 100), 'vn':True}
            self.media_player = MediaPlayer(self.audio_source, ff_opts=ff_opts, callback=self.ffplay_callback)
            
            self.playback_start_time = datetime.now()

            self.play_along_action.blockSignals(True) 
            self.play_along_action.setChecked(True)
            self.play_along_action.blockSignals(False)
                    
            while self.keep_playing:                    
                audio_playback_time = round((datetime.now() - self.playback_start_time).total_seconds() * 1000 * (speed / 100)) # im ms
                curr_audio_pos = self.playback_start_pos + audio_playback_time
                # curr_audio_pos = self.media_player.get_pts() => crashes silently
                new_speed = int(self.playback_speed.currentText()[:-1])
                if new_speed != speed: # user changed playback speed
                    speed = new_speed
                    ff_opts = {'ss': curr_audio_pos / 1000, 'af':'atempo=' + str(speed / 100), 'vn':True}
                    self.media_player.close_player()
                    self.media_player = MediaPlayer(self.audio_source, ff_opts=ff_opts, callback=self.ffplay_callback) 
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
                sleep(0.1)
                self.play_along_action.blockSignals(True) 
                self.play_along_action.setChecked(self.keep_playing)
                self.play_along_action.blockSignals(False)
                QtWidgets.QApplication.processEvents() # update GUI
        
        except Exception as e:
            self.dialog_critical(str(e))
        
        finally:
            if self.media_player:
                self.media_player.close_player()
                self.media_player = None
            self.keep_playing = False
            self.play_along_action.blockSignals(True) 
            self.play_along_action.setChecked(False)
            self.play_along_action.blockSignals(False)
            if self.playing_error:
                self.dialog_critical(self.playing_error)
                self.playing_error = None
            
    def closeEvent(self, event):
        self.keep_playing = False
        # self.stop_audio()
                    
        if self.editor.document().isModified():
            ret = QtWidgets.QMessageBox.warning(self, "noScribe Editor", 
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
            self.media_player.close_player()
            self.media_player = None
        
        event.accept()

    def update_title(self):
        self.setWindowTitle("%s - noScribe Editor" % (os.path.basename(self.path) if self.path else "Untitled"))

if __name__ == '__main__':

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("noScribe Editor")
    # setup stylesheet
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

    window = MainWindow()
    if platform.system() == 'Windows':
        pywinstyles.apply_style(window, 'mica')  
    
    app.exec_()