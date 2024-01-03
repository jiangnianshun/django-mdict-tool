# Copyright (C) 2022 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR BSD-3-Clause

"""PySide6 port of the widgets/dialogs/tabdialog example from Qt v6.x"""

import sys
from config_parser import *

from PySide6.QtCore import QFileInfo
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QCheckBox,
    QApplication,
    QDialog,
    QTabWidget,
    QLineEdit,
    QDialogButtonBox,
    QFrame,
    QListWidget,
    QGroupBox,
    QFormLayout
)

from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression


class TabDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.app = parent

        # file_info = QFileInfo(file_name)

        self.general_tab = GeneralTab(self)

        tab_widget = QTabWidget()

        tab_widget.addTab(self.general_tab, "General")

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        self.accepted.connect(self.accept_event)
        self.rejected.connect(self.reject_event)

        main_layout = QVBoxLayout()
        main_layout.addWidget(tab_widget)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)
        self.setWindowTitle("Configuration")

    def accept_event(self):
        self.app.set_search_url(self.general_tab.base_url, self.general_tab.search_url)

    def reject_event(self):
        print('reject')
        pass


class GeneralTab(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)

        self.config = get_config()

        vld_reg = QRegularExpression('[a-z]+')
        vld = QRegularExpressionValidator(vld_reg)
        self.protocol_label = QLabel("Potocol")
        self.protocol_edit = QLineEdit(self.config['GENERAL']['PROTOCOL'])
        self.protocol_edit.setValidator(vld)

        self.host_label = QLabel("Host")
        self.host_edit = QLineEdit(self.config['GENERAL']['HOST'])

        vld_reg = QRegularExpression('[0-9]+')
        vld = QRegularExpressionValidator(vld_reg)
        self.port_label = QLabel("Port")
        self.port_edit = QLineEdit(self.config['GENERAL']['PORT'])
        self.port_edit.setValidator(vld)

        self.path_label = QLabel("Path")
        self.path_edit = QLineEdit(self.config['GENERAL']['PATH'])

        self.base_url, self.search_url = self.combine_url()

        self.url_label = QLabel("Url")
        self.url_label2 = QLabel(self.search_url)

        self.protocol_edit.editingFinished.connect(self.reset_url)
        self.host_edit.editingFinished.connect(self.reset_url)
        self.port_edit.editingFinished.connect(self.reset_url)
        self.path_edit.editingFinished.connect(self.reset_url)

        main_layout = QFormLayout()
        main_layout.addRow(self.protocol_label, self.protocol_edit)
        main_layout.addRow(self.host_label, self.host_edit)
        main_layout.addRow(self.port_label, self.port_edit)
        main_layout.addRow(self.path_label, self.path_edit)
        main_layout.addRow(self.url_label, self.url_label2)

        self.setLayout(main_layout)

    def combine_url(self):
        protocol = self.protocol_edit.text()
        host = self.host_edit.text()
        port = self.port_edit.text()
        path = self.path_edit.text()
        if path[-1] == '\\' or path[-1] == '/':
            path = path[:-1]
        if path[0] == '\\' or path[0] == '/':
            path = path[1:]
        base_url = f'{protocol}://{host}:{port}/{path}'
        search_url = f'{base_url}/?query=%WORD%'
        item = {'PROTOCOL':protocol, 'HOST': host, 'PORT': port, 'PATH': path}
        set_config('GENERAL', item)
        return base_url, search_url

    def reset_url(self):
        self.base_url, self.search_url = self.combine_url()
        self.url_label2.setText(self.search_url)
