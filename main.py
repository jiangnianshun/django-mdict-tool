# Copyright (C) 2023 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR BSD-3-Clause

"""PySide6 port of the Qt WebEngineWidgets Simple Browser example from Qt v6.x"""

import sys
from argparse import ArgumentParser, RawTextHelpFormatter

from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtCore import QCoreApplication, QLoggingCategory, QUrl, Qt

from browser import Browser, MySplashScreen

import data.rc_simplebrowser

if __name__ == "__main__":
    parser = ArgumentParser(description="Django Mdict",
                            formatter_class=RawTextHelpFormatter)
    parser.add_argument("url", type=str, nargs="?", help="URL")
    args = parser.parse_args()

    app = QApplication(sys.argv + ['--webEngineArgs', '--remote-debugging-port=19000'])  # 启用网页调试
    # app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # 打开的最后一个窗口关闭时会关闭整个应用，不包括托盘，导致截屏后应用直接退出。
    app.setWindowIcon(QIcon("data/imgs/shortcut.png"))
    QLoggingCategory.setFilterRules("qt.webenginecontext.debug=true")

    splash = MySplashScreen()
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    splash.setPixmap(QPixmap('data/imgs/splash.png'))
    font = splash.font()
    font.setPixelSize(16)
    font.setWeight(QFont.Bold)
    splash.setFont(font)
    splash.showMessage('Django Mdict Tool is loading...', alignment=Qt.AlignCenter, color='white')
    splash.show()

    QCoreApplication.setOrganizationName("QtExamples")

    s = QWebEngineProfile.defaultProfile().settings()
    s.setAttribute(QWebEngineSettings.PluginsEnabled, True)
    s.setAttribute(QWebEngineSettings.DnsPrefetchEnabled, True)

    browser = Browser()
    window = browser.create_hidden_window()

    splash.finish(window)  # 隐藏启动界面
    splash.deleteLater()
    sys.exit(app.exec())
