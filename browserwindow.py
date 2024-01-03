# Copyright (C) 2023 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR BSD-3-Clause

import time
from config_parser import *

from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import (QMainWindow, QFileDialog,
                               QInputDialog, QLineEdit, QMenu, QMessageBox,
                               QProgressBar, QToolBar, QVBoxLayout, QWidget, QApplication, QSystemTrayIcon)
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon, QKeySequence, QClipboard, QScreen, \
    QDesktopServices
from PySide6.QtCore import QUrl, Qt, QThread, Slot, Signal, QRect

from tabwidget import TabWidget

import sys
import ctypes
from ctypes import *
from ctypes.wintypes import DWORD, HHOOK, HINSTANCE, MSG, WPARAM, LPARAM, HMODULE, LPCWSTR
import win32con
import win32api
import win32clipboard

import screen_show
from PIL import ImageGrab, ImageQt
import os
import pytesseract
import re
from manga_ocr import MangaOcr
from tabdialog import TabDialog
from helpDialog import HelpDialog

# from sendInput import Keyboard, Mouse
# import keyboard

# import pyautogui
# from sendKeys import PressKey, ReleaseKey

reg = r'[ _=,.;:!?@%&#~`()\[\]<>{}/\\\$\+\-\*\^\'"\t\n\r，。：；“”（）【】《》？!、·0123456789]'
regp = re.compile(reg)

user32 = CDLL("user32.dll", use_last_error=True)
kernel32 = CDLL("kernel32.dll", use_last_error=True)
# kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
# ctypes.windll.kernel32 is WinDLL("kernel32"). WinDLL inherits CDLL

import struct

kernel32.GetModuleHandleW.restype = HMODULE
# ctypes.ArgumentError: argument 3: <class 'OverflowError'>: int too long to convert
kernel32.GetModuleHandleW.argtypes = [LPCWSTR]
# 设置argtypes，需要传参'kernal32.dll'，不设置的话不需要传参
# TypeError: this function takes at least 1 argument (0 given)


shortcut_img = 'data/imgs/shortcut.png'

root_path = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(root_path, 'data', 'tessdata')
data_path = data_path.replace("\\", "/")


class KBDIN(Structure):
    _fields_ = (("wVk", c_ushort), ("dwFlags", c_ulong), ("dwExtraInfo", c_ulonglong))


class INPUT(Structure):
    _fields_ = (("type", c_ulong), ("ki", KBDIN), ("padding", c_ubyte * 8))


def Press(key_code):
    user32.SendInput(1, byref(INPUT(type=1, ki=KBDIN(wVk=key_code))), 40)


def Release(key_code):
    user32.SendInput(1, byref(INPUT(type=1, ki=KBDIN(wVk=key_code, dwFlags=2))), 40)


def remove_backspace(keys):
    result = keys.copy()
    # Chromium already handles navigate on backspace when appropriate.
    for i, key in enumerate(result):
        if (key[0].key() & Qt.Key_unknown) == Qt.Key_Backspace:
            del result[i]
            break
    return result


class BrowserWindow(QMainWindow):
    about_to_close = Signal()

    def __init__(self, browser, profile, forDevTools):
        super().__init__()

        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        self.ocr_engine = 'manga-ocr'

        self.lang_con = 'eng+jpn+chi_sim'
        # pytesseract设置：'eng', 'chi_sim': '中文简体', 'chi_tra': '中文繁体', 'jpn': '日文'

        self.max_word_length = 50

        self.copy_pos_x = None
        self.copy_pos_y = None

        self.pause = False

        self.search_mode = 0
        # 0,keyboard,1,mouse

        self.close_flag = False

        self.key_ctrl_pressed = False
        self.key_ctrl_c_pressed = False
        self.key_alt_pressed = False
        self.key_ctrl_alt_c_pressed = False
        self.mouse_lbtn_trigger = False
        self.timer = None

        self.grab_window = None

        self.copy_flag = False
        self.trigger_flag = False

        self.init_flag = False

        self.screen_index = 0
        self.screen_toggle_num = 0
        self.screen_toggle_flag = False

        self.word_list = []

        self.view_width = 450
        self.view_height = 600
        self.resize(self.view_width, self.view_height)

        self.mocr = None
        self.word = ''

        self.config = get_config()
        protocol = config['GENERAL']['PROTOCOL']
        host = config['GENERAL']['HOST']
        port = config['GENERAL']['PORT']
        path = config['GENERAL']['PATH']

        if path[-1] == '\\' or path[-1] == '/':
            path = path[:-1]
        if path[0] == '\\' or path[0] == '/':
            path = path[1:]
        base_url = f'{protocol}://{host}:{port}/{path}'
        search_url = f'{base_url}/?query=%WORD%'

        self.base_url = base_url
        self.search_url = search_url
        self.search_url_changed = False

        self.copy_thread = self.Worker()
        self.copy_thread.sinOut.connect(self.copy_search_word)

        self.grab_thread = self.Worker()
        self.grab_thread.sinOut.connect(self.grab_word)

        HOOKPROC = WINFUNCTYPE(c_int, c_int, c_int, POINTER(DWORD))
        self.pointer = HOOKPROC(self.hookProc)
        self.keyboard_hook = None
        self.mouse_hook = None

        self.clipboard = QApplication.clipboard()
        self.clipboard.changed.connect(self.search_trigger)

        self.create_screens()

        self.create_tray()

        self._progress_bar = None
        self._history_back_action = None
        self._history_forward_action = None
        self._stop_action = None
        self._reload_action = None
        self._stop_reload_action = None
        self._url_line_edit = None
        self._fav_action = None
        self._last_search = ""
        self._toolbar = None

        self._browser = browser
        self._profile = profile
        self._tab_widget = TabWidget(profile, self)

        self._stop_icon = QIcon(":process-stop.png")
        self._reload_icon = QIcon(":view-refresh.png")

        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.ClickFocus)

        if not forDevTools:
            self._progress_bar = QProgressBar(self)

            self._toolbar = self.create_tool_bar()
            self.addToolBar(self._toolbar)
            mb = self.menuBar()
            mb.addMenu(self.create_file_menu(self._tab_widget))
            mb.addMenu(self.create_edit_menu())
            mb.addMenu(self.create_view_menu())
            mb.addMenu(self.create_window_menu(self._tab_widget))
            mb.addMenu(self.create_help_menu())

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        if not forDevTools:
            self.addToolBarBreak()

            self._progress_bar.setMaximumHeight(1)
            self._progress_bar.setTextVisible(False)
            s = "QProgressBar {border: 0px} QProgressBar.chunk {background-color: #da4453}"
            self._progress_bar.setStyleSheet(s)

            layout.addWidget(self._progress_bar)

        layout.addWidget(self._tab_widget)
        self.setCentralWidget(central_widget)

        self._tab_widget.title_changed.connect(self.handle_web_view_title_changed)
        if not forDevTools:
            self._tab_widget.link_hovered.connect(self._show_status_message)
            self._tab_widget.load_progress.connect(self.handle_web_view_load_progress)
            self._tab_widget.web_action_enabled_changed.connect(self.handle_web_action_enabled_changed)
            self._tab_widget.url_changed.connect(self._url_changed)
            self._tab_widget.fav_icon_changed.connect(self._fav_action.setIcon)
            self._tab_widget.dev_tools_requested.connect(self.handle_dev_tools_requested)
            self._url_line_edit.returnPressed.connect(self._address_return_pressed)
            self._tab_widget.find_text_finished.connect(self.handle_find_text_finished)

            focus_url_line_edit_action = QAction(self)
            self.addAction(focus_url_line_edit_action)
            focus_url_line_edit_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_L))
            focus_url_line_edit_action.triggered.connect(self._focus_url_lineEdit)

        self.menuBar().hide()
        self.statusBar().hide()
        self._toolbar.close()

        self.handle_web_view_title_changed("")
        self._tab_widget.create_tab()
        self.get_last_tab()
        self.tab_widget().set_url(QUrl(self.base_url))

        self.help_dialog = HelpDialog(self)
        self.config_view = TabDialog(self)

        self.load_manga_ocr()

        self.set_hook()

    @Slot(str)
    def _show_status_message(self, m):
        self.statusBar().showMessage(m)

    @Slot(QUrl)
    def _url_changed(self, url):
        self._url_line_edit.setText(url.toDisplayString())

    @Slot()
    def _address_return_pressed(self):
        url = QUrl.fromUserInput(self._url_line_edit.text())
        self._tab_widget.set_url(url)

    @Slot()
    def _focus_url_lineEdit(self):
        self._url_line_edit.setFocus(Qt.ShortcutFocusReason)

    @Slot()
    def _new_tab(self):
        self._tab_widget.create_tab()
        self._url_line_edit.setFocus()

    @Slot()
    def _close_current_tab(self):
        self._tab_widget.close_tab(self._tab_widget.currentIndex())

    @Slot()
    def _update_close_action_text(self):
        last_win = len(self._browser.windows()) == 1
        self._close_action.setText("Quit" if last_win else "Close Window")

    def sizeHint(self):
        desktop_rect = QGuiApplication.primaryScreen().geometry()
        return desktop_rect.size() * 0.9

    def create_file_menu(self, tabWidget):
        file_menu = QMenu("File")
        file_menu.addAction("&New Window", QKeySequence.New,
                            self.handle_new_window_triggered)
        file_menu.addAction("New &Incognito Window",
                            self.handle_new_incognito_window_triggered)

        new_tab_action = QAction("New Tab", self)
        new_tab_action.setShortcuts(QKeySequence.AddTab)
        new_tab_action.triggered.connect(self._new_tab)
        file_menu.addAction(new_tab_action)

        file_menu.addAction("&Open File...", QKeySequence.Open,
                            self.handle_file_open_triggered)
        file_menu.addSeparator()

        close_tab_action = QAction("Close Tab", self)
        close_tab_action.setShortcuts(QKeySequence.Close)
        close_tab_action.triggered.connect(self._close_current_tab)
        file_menu.addAction(close_tab_action)

        self._close_action = QAction("Quit", self)
        self._close_action.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_Q))
        self._close_action.triggered.connect(self.close)
        file_menu.addAction(self._close_action)

        file_menu.aboutToShow.connect(self._update_close_action_text)
        return file_menu

    @Slot()
    def _find_next(self):
        tab = self.current_tab()
        if tab and self._last_search:
            tab.findText(self._last_search)

    @Slot()
    def _find_previous(self):
        tab = self.current_tab()
        if tab and self._last_search:
            tab.findText(self._last_search, QWebEnginePage.FindBackward)

    def create_edit_menu(self):
        edit_menu = QMenu("Edit")
        find_action = edit_menu.addAction("Find")
        find_action.setShortcuts(QKeySequence.Find)
        find_action.triggered.connect(self.handle_find_action_triggered)

        find_next_action = edit_menu.addAction("Find Next")
        find_next_action.setShortcut(QKeySequence.FindNext)
        find_next_action.triggered.connect(self._find_next)

        find_previous_action = edit_menu.addAction("Find Previous")
        find_previous_action.setShortcut(QKeySequence.FindPrevious)
        find_previous_action.triggered.connect(self._find_previous)
        return edit_menu

    @Slot()
    def _stop(self):
        self._tab_widget.trigger_web_page_action(QWebEnginePage.Stop)

    @Slot()
    def _reload(self):
        self._tab_widget.trigger_web_page_action(QWebEnginePage.Reload)

    @Slot()
    def _zoom_in(self):
        tab = self.current_tab()
        if tab:
            tab.setZoomFactor(tab.zoomFactor() + 0.1)

    @Slot()
    def _zoom_out(self):
        tab = self.current_tab()
        if tab:
            tab.setZoomFactor(tab.zoomFactor() - 0.1)

    @Slot()
    def _reset_zoom(self):
        tab = self.current_tab()
        if tab:
            tab.setZoomFactor(1)

    @Slot()
    def _toggle_toolbar(self):
        if self._toolbar.isVisible():
            self._view_toolbar_action.setText("Show Toolbar")
            self._toolbar.close()
        else:
            self._view_toolbar_action.setText("Hide Toolbar")
            self._toolbar.show()

    @Slot()
    def _toggle_statusbar(self):
        sb = self.statusBar()
        if sb.isVisible():
            self._view_statusbar_action.setText("Show Status Bar")
            sb.close()
        else:
            self._view_statusbar_action.setText("Hide Status Bar")
            sb.show()

    def create_view_menu(self):
        view_menu = QMenu("View")
        self._stop_action = view_menu.addAction("Stop")
        shortcuts = []
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_Period))
        shortcuts.append(QKeySequence(Qt.Key_Escape))
        self._stop_action.setShortcuts(shortcuts)
        self._stop_action.triggered.connect(self._stop)

        self._reload_action = view_menu.addAction("Reload Page")
        self._reload_action.setShortcuts(QKeySequence.Refresh)
        self._reload_action.triggered.connect(self._reload)

        zoom_in = view_menu.addAction("Zoom In")
        zoom_in.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_Plus))
        zoom_in.triggered.connect(self._zoom_in)

        zoom_out = view_menu.addAction("Zoom Out")
        zoom_out.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_Minus))
        zoom_out.triggered.connect(self._zoom_out)

        reset_zoom = view_menu.addAction("Reset Zoom")
        reset_zoom.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_0))
        reset_zoom.triggered.connect(self._reset_zoom)

        view_menu.addSeparator()
        self._view_toolbar_action = QAction("Hide Toolbar", self)
        self._view_toolbar_action.setShortcut("Ctrl+|")
        self._view_toolbar_action.triggered.connect(self._toggle_toolbar)
        view_menu.addAction(self._view_toolbar_action)

        self._view_statusbar_action = QAction("Hide Status Bar", self)
        self._view_statusbar_action.setShortcut("Ctrl+/")
        self._view_statusbar_action.triggered.connect(self._toggle_statusbar)
        view_menu.addAction(self._view_statusbar_action)
        return view_menu

    @Slot()
    def _emit_dev_tools_requested(self):
        tab = self.current_tab()
        if tab:
            tab.dev_tools_requested.emit(tab.page())

    def create_window_menu(self, tabWidget):
        menu = QMenu("Window")
        self._next_tab_action = QAction("Show Next Tab", self)
        shortcuts = []
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_BraceRight))
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_PageDown))
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_BracketRight))
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_Less))
        self._next_tab_action.setShortcuts(shortcuts)
        self._next_tab_action.triggered.connect(tabWidget.next_tab)

        self._previous_tab_action = QAction("Show Previous Tab", self)
        shortcuts.clear()
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_BraceLeft))
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_PageUp))
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_BracketLeft))
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.Key_Greater))
        self._previous_tab_action.setShortcuts(shortcuts)
        self._previous_tab_action.triggered.connect(tabWidget.previous_tab)

        self._inspector_action = QAction("Open inspector in window", self)
        shortcuts.clear()
        shortcuts.append(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_I))
        self._inspector_action.setShortcuts(shortcuts)
        self._inspector_action.triggered.connect(self._emit_dev_tools_requested)
        self._window_menu = menu
        menu.aboutToShow.connect(self._populate_window_menu)
        return menu

    def _populate_window_menu(self):
        menu = self._window_menu
        menu.clear()
        menu.addAction(self._next_tab_action)
        menu.addAction(self._previous_tab_action)
        menu.addSeparator()
        menu.addAction(self._inspector_action)
        menu.addSeparator()
        windows = self._browser.windows()
        index = 0
        title = self.window().windowTitle()
        for window in windows:
            action = menu.addAction(title, self.handle_show_window_triggered)
            action.setData(index)
            action.setCheckable(True)
            if window == self:
                action.setChecked(True)
            index += 1

    def create_help_menu(self):
        help_menu = QMenu("Help")
        help_menu.addAction("About Qt", qApp.aboutQt)
        return help_menu

    @Slot()
    def _back(self):
        self._tab_widget.trigger_web_page_action(QWebEnginePage.Back)

    @Slot()
    def _forward(self):
        self._tab_widget.trigger_web_page_action(QWebEnginePage.Forward)

    @Slot()
    def _stop_reload(self):
        a = self._stop_reload_action.data()
        self._tab_widget.trigger_web_page_action(QWebEnginePage.WebAction(a))

    def create_tool_bar(self):
        navigation_bar = QToolBar("Navigation")
        navigation_bar.setMovable(False)
        navigation_bar.toggleViewAction().setEnabled(False)

        self._history_back_action = QAction(self)
        back_shortcuts = remove_backspace(QKeySequence.keyBindings(QKeySequence.Back))

        # For some reason Qt doesn't bind the dedicated Back key to Back.
        back_shortcuts.append(QKeySequence(Qt.Key_Back))
        self._history_back_action.setShortcuts(back_shortcuts)
        self._history_back_action.setIconVisibleInMenu(False)
        self._history_back_action.setIcon(QIcon(":go-previous.png"))
        self._history_back_action.setToolTip("Go back in history")
        self._history_back_action.triggered.connect(self._back)
        navigation_bar.addAction(self._history_back_action)

        self._history_forward_action = QAction(self)
        fwd_shortcuts = remove_backspace(QKeySequence.keyBindings(QKeySequence.Forward))
        fwd_shortcuts.append(QKeySequence(Qt.Key_Forward))
        self._history_forward_action.setShortcuts(fwd_shortcuts)
        self._history_forward_action.setIconVisibleInMenu(False)
        self._history_forward_action.setIcon(QIcon(":go-next.png"))
        self._history_forward_action.setToolTip("Go forward in history")
        self._history_forward_action.triggered.connect(self._forward)
        navigation_bar.addAction(self._history_forward_action)

        self._stop_reload_action = QAction(self)
        self._stop_reload_action.triggered.connect(self._stop_reload)
        navigation_bar.addAction(self._stop_reload_action)

        self._url_line_edit = QLineEdit(self)
        self._fav_action = QAction(self)
        self._url_line_edit.addAction(self._fav_action, QLineEdit.LeadingPosition)
        self._url_line_edit.setClearButtonEnabled(True)
        navigation_bar.addWidget(self._url_line_edit)

        downloads_action = QAction(self)
        downloads_action.setIcon(QIcon(":go-bottom.png"))
        downloads_action.setToolTip("Show downloads")
        navigation_bar.addAction(downloads_action)
        dw = self._browser.download_manager_widget()
        downloads_action.triggered.connect(dw.show)

        return navigation_bar

    def handle_web_action_enabled_changed(self, action, enabled):
        if action == QWebEnginePage.Back:
            self._history_back_action.setEnabled(enabled)
        elif action == QWebEnginePage.Forward:
            self._history_forward_action.setEnabled(enabled)
        elif action == QWebEnginePage.Reload:
            self._reload_action.setEnabled(enabled)
        elif action == QWebEnginePage.Stop:
            self._stop_action.setEnabled(enabled)
        else:
            print("Unhandled webActionChanged signal", file=sys.stderr)

    def handle_web_view_title_changed(self, title):
        off_the_record = self._profile.isOffTheRecord()
        suffix = ("Django Mdict Tool(Incognito)" if off_the_record
                  else "Django Mdict Tool")
        if title:
            self.setWindowTitle(f"{title} - {suffix}")
        else:
            self.setWindowTitle(suffix)

    def handle_new_window_triggered(self):
        window = self._browser.create_window()
        window._url_line_edit.setFocus()

    def handle_new_incognito_window_triggered(self):
        window = self._browser.create_window(True)
        window._url_line_edit.setFocus()

    def handle_file_open_triggered(self):
        filter = "Web Resources (*.html *.htm *.svg *.png *.gif *.svgz);;All files (*.*)"
        url, _ = QFileDialog.getOpenFileUrl(self, "Open Web Resource", "", filter)
        if url:
            self.current_tab().setUrl(url)

    def handle_find_action_triggered(self):
        if not self.current_tab():
            return
        search, ok = QInputDialog.getText(self, "Find", "Find:",
                                          QLineEdit.Normal, self._last_search)
        if ok and search:
            self._last_search = search
            self.current_tab().findText(self._last_search)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def tab_widget(self):
        return self._tab_widget

    def current_tab(self):
        return self._tab_widget.current_web_view()

    def handle_web_view_load_progress(self, progress):
        if 0 < progress < 100:
            self._stop_reload_action.setData(QWebEnginePage.Stop)
            self._stop_reload_action.setIcon(self._stop_icon)
            self._stop_reload_action.setToolTip("Stop loading the current page")
            self._progress_bar.setValue(progress)
        else:
            self._stop_reload_action.setData(QWebEnginePage.Reload)
            self._stop_reload_action.setIcon(self._reload_icon)
            self._stop_reload_action.setToolTip("Reload the current page")
            self._progress_bar.setValue(0)

    def handle_show_window_triggered(self):
        action = self.sender()
        if action:
            offset = action.data()
            window = self._browser.windows()[offset]
            window.activateWindow()
            window.current_tab().setFocus()

    def handle_dev_tools_requested(self, source):
        page = self._browser.create_dev_tools_window().current_tab().page()
        source.setDevToolsPage(page)
        source.triggerAction(QWebEnginePage.InspectElement)

    def handle_find_text_finished(self, result):
        sb = self.statusBar()
        if result.numberOfMatches() == 0:
            sb.showMessage(f'"{self._lastSearch}" not found.')
        else:
            active = result.activeMatch()
            number = result.numberOfMatches()
            sb.showMessage(f'"{self._last_search}" found: {active}/{number}')

    def browser(self):
        return self._browser

    # -----------------------------------------------------------------------------------------------------------------

    def load_manga_ocr(self):
        self.mocr = MangaOcr(pretrained_model_name_or_path='data/manga-ocr-base/')

    def get_last_tab(self):
        self.search_view = self._tab_widget.current_web_view()

    def show_config_view(self):
        self.config_view.show()

    def search_trigger(self):
        if self.copy_flag:
            self.copy_thread.start()
            self.copy_flag = False

    def create_app(self):
        # self.app = QApplication(sys.argv + ['--no-sandbox'])
        self.app = QApplication(sys.argv + ['--webEngineArgs', '--remote-debugging-port=19000'])

        self.app.setApplicationName('Django Mdict Tool')
        self.app.setQuitOnLastWindowClosed(False)

    def handle_double_click(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            # 双击事件处理逻辑
            self.show_search_view()

    def create_tray(self):
        self.icon = QIcon(shortcut_img)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self.icon)
        self.tray.setToolTip('Django Mdict Tool')
        self.tray.activated.connect(self.handle_double_click)
        self.tray.setVisible(True)

        self.menu = QMenu()

        self.action_open = QAction("Open")
        self.action_open.setToolTip('open window')
        self.icon_open = QIcon('data/imgs/baseline_menu_book_black_48dp.png')
        self.action_open.setIcon(self.icon_open)
        self.action_open.triggered.connect(self.show_search_view)
        self.menu.addAction(self.action_open)

        self.action_pause = QAction("Running")
        self.action_pause.setToolTip('start/pause hook')
        self.icon_running = QIcon('data/imgs/baseline_not_started_green_48dp.png')
        self.icon_paused = QIcon('data/imgs/baseline_pause_orange_48dp.png')
        self.action_pause.setIcon(self.icon_running)
        self.action_pause.triggered.connect(self.pause_view)
        self.menu.addAction(self.action_pause)

        self.action_mode = QAction("KeyBoard")
        self.action_mode.setToolTip('kerboard/mouse trigger')
        self.icon_keyboard = QIcon('data/imgs/baseline_keyboard_blue_48dp.png')
        self.icon_mouse = QIcon('data/imgs/baseline_mouse_pink_48dp.png')
        self.action_mode.setIcon(self.icon_keyboard)
        self.action_mode.triggered.connect(self.mode_view)
        self.menu.addAction(self.action_mode)

        self.menu_ocr = QMenu('OCR')
        self.menu_ocr.setToolTip('OCR engine selection')
        self.icon_ocr = QIcon('data/imgs/baseline_zoom_out_black_48dp.png')
        self.menu_ocr.setIcon(self.icon_ocr)
        self.action_engine1 = QAction('manga-ocr')
        self.action_engine1.triggered.connect(self.set_ocr_engine)
        self.action_engine2 = QAction('pytesseract')
        self.action_engine2.triggered.connect(self.set_ocr_engine)
        self.action_engine1.setCheckable(True)
        self.action_engine1.setChecked(True)
        self.action_engine2.setCheckable(True)
        self.menu_ocr.addAction(self.action_engine1)
        self.menu_ocr.addAction(self.action_engine2)

        self.action_group_engines = QActionGroup(self.menu_ocr)
        self.action_group_engines.setExclusive(True)
        self.action_group_engines.addAction(self.action_engine1)
        self.action_group_engines.addAction(self.action_engine2)

        self.menu.addMenu(self.menu_ocr)

        self.menu.addSeparator()

        self.title_bar_flag = True
        self.action_title_bar = QAction("TitleBar")
        self.action_title_bar.setToolTip('show/hide title bar')
        self.icon_title_bar_show = QIcon('data/imgs/baseline_visibility_green_48dp.png')
        self.icon_title_bar_hide = QIcon('data/imgs/baseline_visibility_off_orange_48dp.png')
        self.action_title_bar.setIcon(self.icon_title_bar_show)
        self.action_title_bar.triggered.connect(self.action_title_bar_toggle)
        self.menu.addAction(self.action_title_bar)

        self.menu_bar_flag = False
        self.action_menu_bar = QAction("MenuBar")
        self.action_menu_bar.setToolTip('show/hide menu bar & status bar')
        self.icon_menu_bar_show = QIcon('data/imgs/baseline_visibility_green_48dp.png')
        self.icon_menu_bar_hide = QIcon('data/imgs/baseline_visibility_off_orange_48dp.png')
        self.action_menu_bar.setIcon(self.icon_menu_bar_hide)
        self.action_menu_bar.triggered.connect(self.action_menu_bar_toggle)
        self.menu.addAction(self.action_menu_bar)

        self.menu.addSeparator()

        self.action_open_in_browser = QAction("Browser")
        self.action_open_in_browser.setToolTip('open in browser')
        self.icon_open_in_browser = QIcon('data/imgs/baseline_open_in_browser_black_48dp.png')
        self.action_open_in_browser.setIcon(self.icon_open_in_browser)
        self.action_open_in_browser.triggered.connect(self.open_in_browser)
        self.menu.addAction(self.action_open_in_browser)

        self.history = QMenu('History')
        self.history.setToolTip('search history')
        self.icon_history = QIcon('data/imgs/baseline_history_black_48dp.png')
        self.history.setIcon(self.icon_history)
        self.action_item0 = QAction('no word')
        self.history.addAction(self.action_item0)
        self.menu.addMenu(self.history)

        self.action_config = QAction("Config")
        self.action_config.setToolTip('configuration')
        self.icon_config = QIcon('data/imgs/baseline_settings_black_48dp')
        self.action_config.setIcon(self.icon_config)
        self.action_config.triggered.connect(self.show_config_view)
        self.menu.addAction(self.action_config)

        self.action_help = QAction("Help")
        self.action_help.setToolTip('help')
        self.icon_help = QIcon('data/imgs/baseline_help_outline_black_48dp.png')
        self.action_help.setIcon(self.icon_help)
        self.action_help.triggered.connect(self.show_help_view)
        self.menu.addAction(self.action_help)

        self.action_quit = QAction("Quit")
        self.action_quit.setToolTip('quit program')
        self.icon_quit = QIcon('data/imgs/baseline_settings_power_red_48dp.png')
        self.action_quit.setIcon(self.icon_quit)
        self.action_quit.triggered.connect(self.quit)
        self.menu.addAction(self.action_quit)

        self.tray.setContextMenu(self.menu)

    def show_help_view(self):
        self.help_dialog.show()

    def pause_view(self):
        self.pause = not self.pause
        if self.pause:
            self.action_pause.setText('Paused')
            self.action_pause.setIcon(self.icon_paused)
            print('hook paused...')
            self.tray.showMessage('Hook started', 'Hook started...', self.icon)
        else:
            self.action_pause.setText('Running')
            self.action_pause.setIcon(self.icon_running)
            print('hook started...')
            self.tray.showMessage('Hook paused', 'Hook paused', self.icon)

    def mode_view(self):
        if self.search_mode == 0:
            self.search_mode = 1
            self.action_mode.setText('Mouse')
            self.action_mode.setIcon(self.icon_mouse)
            self.tray.showMessage('Trigger mode is Mouse now.', 'Trigger mode is Mouse now.')
        elif self.search_mode == 1:
            self.search_mode = 0
            self.action_mode.setText('KeyBoard')
            self.action_mode.setIcon(self.icon_keyboard)
            self.tray.showMessage('Trigger mode is KeyBoard now.', 'Trigger mode is KeyBoard now.')
        else:
            print('mode error')
            self.search_mode = 0
            self.action_mode.setText('KeyBoard')
            self.action_mode.setIcon(self.icon_keyboard)

    def open_in_browser(self):
        QDesktopServices.openUrl(QUrl(self.current_tab().url()))

    def action_menu_bar_toggle(self):
        if self.menu_bar_flag:
            self.menu_bar_flag = False
            self.action_menu_bar.setIcon(self.icon_menu_bar_hide)
            self.menuBar().hide()
            self._toggle_statusbar()
            self._toggle_toolbar()
        else:
            self.menu_bar_flag = True
            self.action_menu_bar.setIcon(self.icon_menu_bar_show)
            self.menuBar().show()
            self._toggle_statusbar()
            self._toggle_toolbar()

    def action_title_bar_toggle(self):
        if self.title_bar_flag:
            self.title_bar_flag = False
            self.action_title_bar.setIcon(self.icon_title_bar_hide)
            self.setWindowFlags(Qt.FramelessWindowHint)
        else:
            self.title_bar_flag = True
            self.action_title_bar.setIcon(self.icon_title_bar_show)
            self.setWindowFlag(Qt.FramelessWindowHint, False)

    def set_ocr_engine(self):
        if self.action_engine1.isChecked():
            self.ocr_engine = 'manga-ocr'
        elif self.action_engine2.isChecked():
            self.ocr_engine = 'pytesseract'
        else:
            print('ocr engine error')
            self.ocr_engine = 'manga-ocr'

    def create_screens(self):
        self.available_screens = []

        for screen in QApplication.screens():
            # sc = QScreen.availableGeometry(screen)
            sc = QScreen.geometry(screen)
            sx = sc.x()
            sy = sc.y()
            sw = sc.width()
            sh = sc.height()
            sc = QScreen.devicePixelRatio(screen)

            self.available_screens.append((sx, sy, sw, sh, sc))

    def show_search_view(self):
        if self.isMinimized():
            if self.search_url_changed:
                if self.is_search_view_valid() and self.word == '':
                    self.search_view.load(QUrl(self.base_url))
                else:
                    self.search_view.load(QUrl(self.search_url))
            self.showNormal()

        else:
            if self.search_url_changed:
                if self.is_search_view_valid() and self.word == '':
                    self.search_view.load(QUrl(self.base_url))
                else:
                    self.search_view.load(QUrl(self.search_url))
            self.show()

    def minize_search_view(self):
        self.showMinimized()

    def is_search_view_valid(self):
        search_view_url = self.search_view.url().toString()
        if search_view_url == '':
            return False
        else:
            return True

    def grab_image(self):
        mouse_x, mouse_y = self.get_mouse_pos()
        screen_index = self.check_screen_id(mouse_x)
        self.create_screens()
        sx, sy, sw, sh, sc = self.available_screens[screen_index]

        img = ImageGrab.grab(all_screens=True)
        # img.save('test.png')
        # 主屏幕的左上角是屏幕的坐标原点，x轴向右，y轴向下
        # 截图的时候需要将屏幕的原点移动到截图的原点
        f_sx = 0
        f_sy = 0

        for tsx, tsy, tsw, tsh, tsc in self.available_screens:
            if tsx < f_sx:
                f_sx = tsx
            if tsy < f_sy:
                f_sy = tsy
        crop_left, crop_top, crop_right, crop_bottom = sx + abs(f_sx), sy + abs(f_sy), sx + abs(
            f_sx) + sw * sc, sy + abs(f_sy) + sh * sc
        img = img.crop((crop_left, crop_top, crop_right, crop_bottom))

        return img, sx, sy, sw, sh, sc

    def append_word(self):
        if self.word in self.word_list:
            del self.word_list[self.word_list.index(self.word)]
        self.word_list.append(self.word)
        if len(self.word_list) > 10:
            self.word_list = self.word_list[-11:]

    def grab_word(self):
        try:
            img, sx, sy, sw, sh, sc = self.grab_image()
            self.grab_window = screen_show.Ui_MainWindow(self, img, sx, sy, sw, sh, sc)
            self.grab_window.show()
        except Exception as e:
            self.grab_window = None
            print('grab error')

    def set_search_url(self, new_base_url, new_search_url):
        self.base_url = new_base_url
        self.search_url = new_search_url
        self.search_url_changed = True

    def trigger_search(self, text):
        text = text.replace('\r', '').replace('\n', '')
        self.word = text
        self.append_word()
        self.get_last_tab()
        print('word:', self.word)

        url = self.search_url.replace('%WORD%', self.word)

        if not self.is_search_view_valid() or self.search_url_changed:
            self.move_view()
            self.search_view.load(QUrl(url))
            self.show_search_view()
            self.search_url_changed = False
        else:
            if self.search_view.isVisible():
                if self.isMinimized():
                    self.send_word()
                    self.showNormal()
                else:
                    self.send_word()
            else:
                # webengine在隐藏时（discard state），无法运行runJavaScript
                self.move_view()
                self.search_view.setUrl(url)
                self.show_search_view()

    def copy_search_word(self):
        clip_text = QClipboard.text(self.clipboard)
        if clip_text == '':
            t1 = time.perf_counter()
            while True:
                clip_text = QClipboard.text(self.clipboard)
                if clip_text != '':
                    break
                elif time.perf_counter() - t1 > 5:
                    break
        clip_text = clip_text.strip()
        if clip_text != '' and 0 < len(clip_text) < self.max_word_length:
            self.trigger_search(clip_text)

    def grab_search_word(self, img):
        self.reset_view()
        if self.ocr_engine == 'manga-ocr' and self.mocr is not None:
            text = self.mocr(img)
            text = regp.sub('', text)
            text = text.strip()
            if 0 < len(text) < self.max_word_length:
                self.trigger_search(text)
        elif self.ocr_engine == 'pytesseract':
            tess_cmd = '--psm 6 --oem 1 -c lstm_choice_iterations=0 -c page_separator=""'
            if data_path != '':
                tess_cmd = f'{tess_cmd} --tessdata-dir {data_path}'

            data = pytesseract.image_to_data(img, lang=self.lang_con, config=tess_cmd)
            data_list = [line.split('\t') for line in data.split('\n')]
            text = ''
            for di in range(1, len(data_list)):
                # 去重
                data = data_list[di]
                if data[0] == '5' and len(data) == 12:
                    if data[4] == '1':
                        if di + 2 < len(data_list):
                            edata = data_list[di + 2]
                            if len(edata) == 12 and data[4] != edata[4]:
                                text += data[-1][0]
                            else:
                                text += data[-1]
                        else:
                            text += data[-1]
                    else:
                        if data[4] != data_list[di - 2][4]:
                            if data[5] == '1':
                                text += data[-1][0]

            # psm设置布局，小段文本6或7比较好，6可用于横向和竖向文字，7只能用于横向文字，文字方向转90度的用5。
            # tesseract会在末尾加form feed分页符，unicode码000c。
            # -c page_separator=""设置分页符为空
            text = regp.sub('', text)
            text = text.strip()

            if 0 < len(text) < self.max_word_length:
                self.show_search_view()
                self.trigger_search(text)
        else:
            raise Exception('ocr engine error')

    def send_word(self):
        js_string = f'$("#mdict-modal-anki").modal("hide");$("#query").val(html_unescape("{self.word}"));$("#mdict-query").trigger("click");'
        self.search_view.page().runJavaScript(js_string)

    def quit(self):
        self.close_flag = True
        self.uninstallHookProc(self.keyboard_hook)
        self.uninstallHookProc(self.mouse_hook)
        print('Hook uninstalled')
        self.about_to_close.emit()
        self.deleteLater()
        # self.quit()

    def uninstallHookProc(self, hooked):
        if hooked is not None:
            user32.UnhookWindowsHookEx(hooked)
            hooked = None

    def hookProc(self, nCode, wParam, lParam):
        if self.pause or self.close_flag:
            return user32.CallNextHookEx(self.keyboard_hook, nCode, wParam, lParam)

        if nCode < 0:
            return user32.CallNextHookEx(self.keyboard_hook, nCode, wParam, lParam)
        else:
            if self.search_mode == 0:
                # 键盘触发
                if wParam == win32con.WM_KEYDOWN:
                    if lParam.contents.value in [win32con.VK_RCONTROL, win32con.VK_LCONTROL, win32con.VK_RMENU,
                                                 win32con.VK_LMENU, 67]:
                        if lParam.contents.value == win32con.VK_RCONTROL or lParam.contents.value == win32con.VK_LCONTROL:
                            self.timer = time.perf_counter()
                            self.key_ctrl_pressed = True
                            self.key_ctrl_c_pressed = False
                            self.key_ctrl_alt_c_pressed = False
                        elif lParam.contents.value == win32con.VK_LMENU or lParam.contents.value == win32con.VK_RMENU:
                            self.timer = time.perf_counter()
                            self.key_ctrl_c_pressed = False
                            self.key_alt_pressed = True
                            self.key_ctrl_alt_c_pressed = False
                        elif self.key_ctrl_pressed and not self.key_alt_pressed and lParam.contents.value == 67:
                            if self.timer is not None and time.perf_counter() - self.timer < 0.5:
                                self.key_ctrl_c_pressed = True
                                self.key_ctrl_alt_c_pressed = False
                                self.timer = None
                            else:
                                self.timer = None
                        elif self.key_ctrl_pressed and self.key_alt_pressed and lParam.contents.value == 67:
                            if self.timer is not None and time.perf_counter() - self.timer < 0.5:
                                self.key_ctrl_c_pressed = False
                                self.key_ctrl_alt_c_pressed = True
                                self.timer = None
                            else:
                                self.timer = None
                        else:
                            self.timer = None
                            self.key_ctrl_pressed = False
                            self.key_ctrl_c_pressed = False
                            self.key_alt_pressed = False
                            self.key_ctrl_alt_c_pressed = False

                        if self.key_ctrl_c_pressed:
                            print('ctrl+c, copy...')
                            self.copy_flag = True
                            self.key_ctrl_pressed = False
                            self.key_ctrl_c_pressed = False
                            self.key_alt_pressed = False
                            self.key_ctrl_alt_c_pressed = False
                        if self.key_ctrl_alt_c_pressed:
                            print('ctrl+shift+c, grab...')
                            self.key_ctrl_pressed = False
                            self.key_ctrl_c_pressed = False
                            self.key_alt_pressed = False
                            self.key_ctrl_alt_c_pressed = False
                            self.grab_thread.start()
                    else:
                        self.copy_flag = False
                        self.key_ctrl_pressed = False
                        self.key_ctrl_c_pressed = False
                        self.key_alt_pressed = False
                        self.key_ctrl_alt_c_pressed = False
            elif self.search_mode == 1:
                # 鼠标触发
                if wParam == win32con.WM_MBUTTONDOWN:
                    if self.grab_window is None or not self.grab_window.isVisible():
                        self.grab_thread.start()
                elif wParam == win32con.WM_LBUTTONDOWN:
                    self.copy_flag = False
                    self.copy_pos_x, self.copy_pos_y = self.get_mouse_pos()
                elif wParam == win32con.WM_LBUTTONUP:
                    cur_mouse_pos_x, cur_mouse_pos_y = self.get_mouse_pos()
                    if self.copy_pos_x is not None and self.copy_pos_y is not None:
                        if abs(cur_mouse_pos_x - self.copy_pos_x) > 5 or abs(cur_mouse_pos_y - self.copy_pos_y) > 5:

                            win32api.keybd_event(win32con.VK_LCONTROL,
                                                 win32api.MapVirtualKey(win32con.VK_LCONTROL, 0), 0, 0)
                            win32api.keybd_event(67, win32api.MapVirtualKey(67, 0), 0, 0)
                            win32api.keybd_event(win32con.VK_LCONTROL,
                                                 win32api.MapVirtualKey(win32con.VK_LCONTROL, 0),
                                                 win32con.KEYEVENTF_KEYUP, 0)
                            win32api.keybd_event(67, win32api.MapVirtualKey(67, 0), win32con.KEYEVENTF_KEYUP, 0)

                            self.copy_flag = True
                            self.copy_pos_x = None
                            self.copy_pos_y = None
            else:
                raise Exception('search mode error')

            if wParam == win32con.WM_RBUTTONDOWN or wParam == win32con.WM_MBUTTONDOWN:
                # 中键或右键单击消失
                if self.grab_window is not None and self.grab_window.isVisible():
                    self.grab_window.close()
                else:
                    mouse_x, mouse_y = self.get_mouse_pos()
                    tx1 = self.x()
                    tx2 = tx1 + self.width()
                    ty1 = self.y()
                    ty2 = ty1 + self.height()

                    if tx1 <= mouse_x <= tx2 and ty1 <= mouse_y <= ty2:
                        # 在窗口内
                        pass
                    else:
                        # 在窗口外
                        self.minize_search_view()

        return user32.CallNextHookEx(self.keyboard_hook, nCode, wParam, lParam)

    def installKeyboardHookProc(self, keyboard_hooked, pointer, handle):
        keyboard_hooked = user32.SetWindowsHookExA(
            win32con.WH_KEYBOARD_LL,
            pointer,
            handle,
            0
        )
        if not keyboard_hooked:
            return False
        return True

    def installMouseHookProc(self, mouse_hooked, pointer, handle):
        mouse_hooked = user32.SetWindowsHookExA(
            win32con.WH_MOUSE_LL,
            pointer,
            handle,
            0
        )
        if not mouse_hooked:
            return False
        return True

    def set_hook(self):
        self.handle = kernel32.GetModuleHandleW('kernal32.dll')
        if self.installKeyboardHookProc(self.keyboard_hook, self.pointer, self.handle):
            print("Keyboard Hook installed")
            try:
                msg = MSG()
                user32.GetMessageA(byref(msg), 0, 0, 0)
            except KeyboardInterrupt as kerror:
                self.uninstallHookProc(self.keyboard_hook)
                print("Keyboard Hook uninstall...")
        else:
            print("Keyboard Hook installed error")

        if self.installMouseHookProc(self.mouse_hook, self.pointer, self.handle):
            print("Mouse Hook installed")
            try:
                msg = MSG()
                user32.GetMessageA(byref(msg), 0, 0, 0)
            except KeyboardInterrupt as kerror:
                self.uninstallHookProc(self.mouse_hook)
                print("Mouse Hook uninstall...")
        else:
            print("Mouse Hook installed error")

    class Worker(QThread):
        sinOut = Signal(str)

        def __init__(self):
            super().__init__()

        def run(self):
            self.sinOut.emit('')

    def adjust_view_pos(self, x, y, w, h):
        index = self.check_screen_id(x)

        sx, sy, sw, sh, sc = self.available_screens[index]

        if x <= sx + 1:
            x = 5
        if y <= sy + 1:
            y = 5
        if x + w >= sx + sw:
            x = sx + sw - w
        if y + h >= sy + sh:
            y = sy + sh - h

        return x, y

    def adjust_view_rect(self, x, y, w, h):
        index = self.check_screen_id(x)
        if self.screen_index != index:
            self.screen_toggle_flag = True

        if self.screen_toggle_flag:
            w = self.view_width
            h = self.view_height
            if self.screen_toggle_num > 2:
                self.screen_index = index
                self.screen_toggle_num = 0
            self.screen_toggle_num += 1

        sx, sy, sw, sh, sc = self.available_screens[index]

        if x <= sx + 1:
            x = 5
        if y <= sy + 1:
            y = 5
        if x + w >= sx + sw:
            x = sx + sw - w
        if y + h >= sy + sh:
            y = sy + sh - h

        return QRect(x, y, w, h)

    def check_screen_id(self, x):
        for index, ava_screen in enumerate(self.available_screens):
            if ava_screen[0] <= x <= ava_screen[0] + ava_screen[2]:
                return index
        return 0

    def get_mouse_pos(self):
        mouse_pos = self.cursor().pos()
        return mouse_pos.x(), mouse_pos.y()

    def move_view(self):
        mouse_pos_x, mouse_pos_y = self.get_mouse_pos()
        view_width = self.width()
        view_height = self.height()
        new_x, new_y = self.adjust_view_pos(mouse_pos_x, mouse_pos_y, view_width, view_height)
        self.move(new_x, new_y)

    def reset_view(self):
        mouse_pos_x, mouse_pos_y = self.get_mouse_pos()
        if not self.init_flag:
            view_width = self.view_width
            view_height = self.view_height
            self.init_flag = True
        else:
            view_width = self.width()
            view_height = self.height()

        rect = self.adjust_view_rect(mouse_pos_x, mouse_pos_y, view_width, view_height)

        self.setGeometry(rect)
