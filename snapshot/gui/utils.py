# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import copy
import os

from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from snapshot.parser import MacroError

from ..ca_core import parse_macros


def parse_dict_macros_to_text(macros):
    """
    Converting dict() separated macros string to comma separated.

    :param macros: dict of macros, substitutions

    :return: macro string
    """

    macros_str = "".join(
        macro + "=" + subs + "," for macro, subs in macros.items()
    )

    if macros_str:
        # Clear last comma
        macros_str = macros_str[0:-1]

    return macros_str


class SnapshotConfigureDialog(QDialog):
    """ Dialog window to select and apply file. """
    accepted = QtCore.pyqtSignal(str, dict)

    def __init__(self, parent=None, init_path=None, init_macros=None, **kw):
        QDialog.__init__(self, parent, **kw)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(layout)

        # This Dialog consists of file selector and buttons to apply
        # or cancel the file selection
        macros_layout = QHBoxLayout()
        macros_label = QLabel("Macros:", self)
        macros_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        self.macros_input = QLineEdit(self)
        self.macros_input.setPlaceholderText("MACRO1=M1,MACRO2=M2,...")
        self.file_selector = SnapshotFileSelector(
            self, label_width=macros_label.sizeHint().width(), init_path=init_path)

        macros_layout.addWidget(macros_label)
        macros_layout.addWidget(self.macros_input)
        macros_layout.setSpacing(10)

        if not init_macros:
            self.macros_input.setText('')

        elif isinstance(init_macros, dict):
            self.macros_input.setText(parse_dict_macros_to_text(init_macros))

        else:  # string
            self.macros_input.setText(init_macros)

        self.setMinimumSize(600, 50)

        layout.addWidget(self.file_selector)
        layout.addLayout(macros_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        button_box.accepted.connect(self._config_accepted)
        button_box.rejected.connect(self._config_rejected)

    def _config_accepted(self):
        # Save to file path to local variable and emit signal
        if not self.file_selector.file_path:
            file_path = ""
        else:
            file_path = self.file_selector.file_path

        if os.path.isfile(file_path):
            try:
                self.accepted.emit(
                    file_path, parse_macros(
                        self.macros_input.text()))
                self.done(QDialog.Accepted)
            except MacroError as e:
                QMessageBox.warning(self, "Warning", str(e),
                                          QMessageBox.Ok,
                                          QMessageBox.NoButton)

        else:
            warn = "File {} does not exist!".format(file_path)
            QMessageBox.warning(
                self,
                "Warning",
                warn,
                QMessageBox.Ok,
                QMessageBox.NoButton)

    def _config_rejected(self):
        self.reject()
        self.done(QDialog.Rejected)

    def focusInEvent(self, event):
        self.file_selector.setFocus()


class SnapshotFileSelector(QWidget):
    """ Widget to select file with dialog box. """

    path_changed = QtCore.pyqtSignal()

    def __init__(self, parent=None, label_text="File:", button_text="...", label_width=None,
                 init_path=None, show_files=True, **kw):
        QWidget.__init__(self, parent, **kw)
        self.file_path = init_path

        self.show_files = show_files
        # Create main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # This widget has 3 parts:
        #   label
        #   input field (when value of input is changed, it is stored locally)
        #   icon button to open file dialog
        label = QLabel(label_text, self)
        label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        if label_width is not None:
            label.setMinimumWidth(label_width)
        file_path_button = QToolButton(self)
        file_path_button.setText(button_text)

        file_path_button.clicked.connect(self.open_selector)
        file_path_button.setFixedSize(27, 27)
        self.file_path_input = QLineEdit(self)
        self.file_path_input.textChanged.connect(self.change_file_path)
        if label.text():
            layout.addWidget(label)
        layout.addWidget(self.file_path_input)
        layout.addWidget(file_path_button)

        self.initial_file_path = self.text()
        if init_path:
            self.initial_file_path = os.path.abspath(init_path)
            self.setText(self.initial_file_path)

    def open_selector(self):
        dialog = QFileDialog(self)
        dialog.fileSelected.connect(self.handle_selected)
        dialog.setDirectory(self.initial_file_path)

        if not self.show_files:
            dialog.setFileMode(QFileDialog.Directory)
            dialog.setOption(QFileDialog.ShowDirsOnly, True)
        dialog.exec_()

    def handle_selected(self, candidate_path):
        if candidate_path:
            self.setText(candidate_path)

    def change_file_path(self):
        self.file_path = self.file_path_input.text()
        self.path_changed.emit()

    def text(self):
        return self.file_path_input.text()

    def setText(self, text):
        self.file_path_input.setText(text)

    def focusInEvent(self, event):
        self.file_path_input.setFocus()


class SnapshotKeywordSelectorWidget(QComboBox):
    """
    Widget for defining keywords (labels). Existing keywords are read from
    the common_settings data structure and are suggested to the user in
    drop down menu. Keywords that are selected are returned as list.
    """
    keywords_changed = QtCore.pyqtSignal()

    def __init__(self, common_settings, defaults_only=False, parent=None):
        QComboBox.__init__(self, parent)

        self.defaults_only = defaults_only
        self.common_settings = common_settings

        # data holders
        self.selectedKeywords = []
        self.keywordWidgets = {}

        # Main layout
        # [selected widgets][input][drop down arrow (part of QComboBox)]
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(5, 0, 35, 0)
        self.layout.setSpacing(2)

        if not defaults_only:
            self.setEditable(True)
            # Extra styling
            self.lineEdit().setStyleSheet("background-color: white")

            self.input = SnapshotKeywordSelectorInput(self.input_handler, self)
            self.layout.addWidget(self.input)
        else:
            self.layout.addStretch()

        self.setCurrentIndex(0)
        self.currentIndexChanged[str].connect(self.add_to_selected)

        self.update_suggested_keywords()

    def get_keywords(self):
        # Return list of currently selected keywords
        return self.selectedKeywords

    def input_handler(self, event):
        # Is called in self.input widget, every time when important events
        # happen (key events, focus events). self.input just passes the
        # events to this method, where are handled.
        if event.type() == QtCore.QEvent.FocusOut:
            self.focus_out(event)
        else:
            self.key_press_event(event)

    def focus_out(self, event):
        # When focused out of the input (clicking away, tab pressed, ...)
        # current string in the input is added to the selected keywords
        self.add_to_selected(self.input.text())

    def key_press_event(self, event):
        # Handles keyboard events in following way:
        #     if: space, enter or tab, then add current string to the selected
        #     if backspace, then delete last character, or last keyword
        if event.key() in [Qt.Key_Tab, Qt.Key_Enter,
                           Qt.Key_Return, Qt.Key_Space]:
            if self.input.text().endswith(" "):
                key_to_add = self.input.text().split(" ")[-2]
            else:
                key_to_add = self.input.text()
            self.add_to_selected(key_to_add)

        elif event.key() == Qt.Key_Backspace and len(self.selectedKeywords):
            self.remove_keyword(self.selectedKeywords[-1])

    def focusInEvent(self, event):
        # Focus should always be on the self.input
        if not self.defaults_only:
            self.input.setFocus()

    def add_to_selected(self, keyword, force=False):
        # When called, keyword is added to list of selected keywords and
        # new graphical representation is added left to the input field
        self.setCurrentIndex(0)
        if not self.defaults_only:
            self.input.setText("")

        default_labels = self.common_settings["default_labels"]
        keyword = keyword.strip()

        # Skip if already selected or not in predefined labels if defaults_only
        # (force=True overrides defaults_only)
        if keyword and (keyword not in self.selectedKeywords) and (
                not self.defaults_only or force or self.defaults_only and keyword in default_labels):
            key_widget = SnapshotKeywordWidget(keyword, self)
            key_widget.delete.connect(self.remove_keyword)
            self.keywordWidgets[keyword] = key_widget
            self.selectedKeywords.append(keyword)
            self.layout.insertWidget(
                len(self.selectedKeywords) - 1, key_widget)
            self.keywords_changed.emit()
            self.setItemText(0, "")

    def remove_keyword(self, keyword):
        # Remove keyword from list of selected and delete graphical element
        keyword = keyword.strip()
        if keyword in self.selectedKeywords:
            self.selectedKeywords.remove(keyword)
            key_widget = self.keywordWidgets.get(keyword)
            self.layout.removeWidget(key_widget)
            key_widget.deleteLater()
            self.keywords_changed.emit()
            if not self.selectedKeywords:
                self.setItemText(0, "Select labels ...")

    def setPlaceholderText(self, text):
        # Placeholder tefirst_itemxt is always in the input field
        if not self.defaults_only:
            self.input.setPlaceholderText(text)

    def update_suggested_keywords(self):
        # Method to be called when global list of existing labels (keywords)
        # is changed and widget must be updated.
        self.clear()
        labels = self.common_settings['default_labels'][:]
        if not self.defaults_only:
            labels += [l for l in self.common_settings['existing_labels']
                       if l not in labels]
            self.addItem("")
        else:
            self.addItem("Select labels ...")

        labels.sort()
        self.addItems(labels)

        # resize the qcombobox dropdown to show more items
        self.setMaxVisibleItems(len(labels)+1 if len(labels) < 30 else 30)

    def clear_keywords(self):
        keywords_to_remove = copy.copy(self.get_keywords())
        for keyword in keywords_to_remove:
            self.remove_keyword(keyword)


class SnapshotKeywordSelectorInput(QLineEdit):
    """
    Subclass of QLineEdit, which handles keyboard events in a keyword
    selector specific way (defines keys for applying new keyword to selected,
    and removing it from the list). Events that takes actions on the main
    widget are passed to the specified function, other are handled natively.
    """

    def __init__(self, callback, parent=None):
        QLineEdit.__init__(self, parent)
        self.callback = callback
        self.setFrame(False)
        self.setTextMargins(0, 0, 0, 0)

    def keyPressEvent(self, event):
        # Pass special key events to the main widget, handle others.
        if event.key() in [Qt.Key_Tab, Qt.Key_Enter, Qt.Key_Return, Qt.Key_Space, Qt.Key_Escape] or \
                (not self.text().strip() and event.key() == Qt.Key_Backspace):
            self.callback(event)
        else:
            QLineEdit.keyPressEvent(self, event)

    def focusOutEvent(self, event):
        # Pass the event to the main widget which will add current string to
        # the selected keywords, and then remove the focus
        self.callback(event)
        QLineEdit.focusOutEvent(self, event)


class SnapshotKeywordWidget(QFrame):
    """
    Graphical representation of the selected widget. A Frame with remove
    button.
    """
    delete = QtCore.pyqtSignal(str)

    def __init__(self, text=None, parent=None):
        QFrame.__init__(self, parent)
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(3, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setMaximumHeight(parent.size().height() - 4)
        self.setLayout(self.layout)

        self.keyword = text

        label = QLabel(text, self)
        delete_button = QToolButton(self)
        icon_path = os.path.dirname(os.path.realpath(__file__))
        icon_path = os.path.join(icon_path, "images/remove.png")
        delete_button.setIcon(QIcon(icon_path))
        delete_button.setStyleSheet(
            "border: 0px; background-color: transparent; margin: 0px")
        delete_button.clicked.connect(self.delete_pressed)

        self.layout.addWidget(label)
        self.layout.addWidget(delete_button)

        self.setStyleSheet(
            "background-color:#CCCCCC;color:#000000; border-radius: 2px;")

    def delete_pressed(self):
        # Emit delete signal with information about removed keyword.
        # main widget will take care of removing it from the list.
        self.delete.emit(self.keyword)


class SnapshotEditMetadataDialog(QDialog):
    def __init__(self, metadata, common_settings, parent=None):
        self.common_settings = common_settings
        self.metadata = metadata

        QDialog.__init__(self, parent)
        group_box = QGroupBox("Meta-data", self)
        group_box.setFlat(False)
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # Make a field to enable user adding a comment
        self.comment_input = QLineEdit(self)
        self.comment_input.setText(metadata["comment"])
        form_layout.addRow("Comment:", self.comment_input)

        # Make field for labels
        # If default labels are defined, then force default labels
        self.labels_input = SnapshotKeywordSelectorWidget(common_settings,
                                                          defaults_only=self.common_settings['force_default_labels'],
                                                          parent=self)
        for label in metadata["labels"]:
            self.labels_input.add_to_selected(label, force=True)
        form_layout.addRow("Labels:", self.labels_input)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel, parent=self)

        self.ok_button = self.button_box.button(QDialogButtonBox.Ok)
        self.cancel_button = self.button_box.button(QDialogButtonBox.Cancel)

        self.button_box.clicked.connect(self.handle_click)
        group_box.setLayout(form_layout)
        layout.addWidget(group_box)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

        # Widget as window
        self.setWindowTitle("Edit meta-data")
        self.setWindowFlags(Qt.Window | Qt.Tool)
        self.setEnabled(True)

    def handle_click(self, button):
        if button == self.ok_button:
            self.apply_config()
            self.close()
        elif button == self.cancel_button:
            self.close()

    def apply_config(self):
        self.metadata["comment"] = self.comment_input.text()
        self.metadata["labels"].clear()
        self.metadata["labels"] = self.labels_input.get_keywords()
        self.accept()


class DetailedMsgBox(QMessageBox):
    def __init__(self, msg='', details='', title='', parent=None,
                 std_buttons=QMessageBox.Yes | QMessageBox.No):
        super().__init__(parent=parent)
        self.setText(msg)
        self.setDetailedText(details)
        self.setWindowTitle(title)
        self.setStandardButtons(std_buttons)
        self.setSizeGripEnabled(True)

    def resizeEvent(self, e):
        result = QMessageBox.resizeEvent(self, e)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        textEdit = self.findChild(QTextEdit)
        if textEdit is not None:
            textEdit.setMinimumHeight(0)
            textEdit.setMaximumHeight(16777215)
            textEdit.setMinimumWidth(0)
            textEdit.setMaximumWidth(16777215)
            textEdit.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Expanding)

        return result


def show_snapshot_parse_errors(parent, file_and_error_list):
    err_details = ""
    for item in file_and_error_list:
        if item[1]:  # list of errors

            err_details += '- - - ' + item[0] + \
                ' - - -\n * '  # file name
            err_details += '\n * '.join(item[1])
            err_details += '\n\n'

    err_details = err_details[:-2]  # Remove last two new lines

    if err_details:
        msg = str(len(file_and_error_list)) + \
            " of the snapshot saved files (.snap) were loaded with errors " \
            "(see details)."
        msg_window = DetailedMsgBox(
            msg, err_details, 'Warning', parent, QMessageBox.Ok)
        msg_window.exec_()


def make_separator(parent, direction='vertical'):
    "Makes a separator line"
    sep = QFrame(parent)
    sep.setFrameShape(QFrame.VLine if direction == 'vertical'
                      else QFrame.HLine)
    return sep
