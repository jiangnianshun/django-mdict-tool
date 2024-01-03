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
)

class HelpDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent)

        label1a = QLabel("Kerboard triggered search: Copy search: Ctrl+C, OCR search: Ctrl+Shift+C.")
        label1b = QLabel("键盘触发：复制查词：Ctrl+C；截屏查词：Ctrl+Shift+C。")
        label2a = QLabel("Mouse triggered search: Copy search: select text; OCR search: middle mouse button click.")
        label2b = QLabel("鼠标触发：复制查词：鼠标左键选择文本；截屏查词：鼠标中键单击。")



        main_layout = QVBoxLayout()
        main_layout.addWidget(label1a)
        main_layout.addWidget(label1b)
        main_layout.addWidget(label2a)
        main_layout.addWidget(label2b)

        self.setLayout(main_layout)
        self.setWindowTitle("Help")