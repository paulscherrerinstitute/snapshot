#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import copy
import datetime
import os
import time
import enum

from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QCursor, QGuiApplication
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QMessageBox, QTreeWidget, QTreeWidgetItem, \
    QMenu, QLineEdit, QLabel

from ..ca_core import PvStatus, ActionStatus, SnapshotPv
from ..core import background_workers
from ..parser import get_save_files, parse_from_save_file, save_file_suffix
from .utils import SnapshotKeywordSelectorWidget, SnapshotEditMetadataDialog, \
    DetailedMsgBox, show_snapshot_parse_errors


@enum.unique
class FileSelectorColumns(enum.IntEnum):
    filename = 0
    comment = enum.auto()
    labels = enum.auto()


class SnapshotRestoreWidget(QWidget):
    """
    Restore widget is a widget that enables user to restore saved state of PVs
    listed in request file from one of the saved files.
    Save widget consists of:
        - file selector (tree of all files)
        - restore button
        - search/filter

    Data about current app state (such as request file) must be provided as
    part of the structure "common_settings".
    """
    files_selected = QtCore.pyqtSignal(dict)
    files_updated = QtCore.pyqtSignal(dict)
    restored_callback = QtCore.pyqtSignal(dict, bool)

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QWidget.__init__(self, parent, **kw)

        self.snapshot = snapshot
        self.common_settings = common_settings
        self.filtered_pvs = list()
        # dict of available files to avoid multiple openings of one file when
        # not needed.
        self.file_list = dict()

        # Create main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(layout)

        # Create list with: file names, comment, labels
        self.file_selector = SnapshotRestoreFileSelector(snapshot,
                                                         common_settings, self)

        self.file_selector.files_selected.connect(self.handle_selected_files)

        # Make restore buttons
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.start_refresh)
        self.refresh_button.setToolTip("Refresh .snap files.")
        self.refresh_button.setEnabled(True)

        self.restore_button = QPushButton("Restore Filtered", self)
        self.restore_button.clicked.connect(self.start_restore_filtered)
        self.restore_button.setToolTip("Restores only currently filtered PVs from the selected .snap file.")
        self.restore_button.setEnabled(False)

        self.restore_all_button = QPushButton("Restore All", self)
        self.restore_all_button.clicked.connect(self.start_restore_all)
        self.restore_all_button.setToolTip("Restores all PVs from the selected .snap file.")
        self.restore_all_button.setEnabled(False)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.refresh_button)
        btn_layout.addWidget(self.restore_all_button)
        btn_layout.addWidget(self.restore_button)

        # Link to status widgets
        self.sts_log = self.common_settings["sts_log"]
        self.sts_info = self.common_settings["sts_info"]

        # Add all widgets to main layout
        layout.addWidget(self.file_selector)
        layout.addLayout(btn_layout)

        self.restored_callback.connect(self.restore_done)

    def handle_new_snapshot_instance(self, snapshot, already_parsed_files):
        self.file_selector.handle_new_snapshot_instance(snapshot)
        self.snapshot = snapshot
        self.rebuild_file_list(already_parsed_files)

    def start_refresh(self):
        self.rebuild_file_list()

    def start_restore_all(self):
        self.do_restore()

    def start_restore_filtered(self):
        filtered_n = len(self.filtered_pvs)

        if filtered_n == len(self.snapshot.pvs):  # all pvs selected
            self.do_restore()  # This way functions below skip unnecessary checks
        elif filtered_n:
            self.do_restore(self.filtered_pvs)
            # Do not start a restore if nothing to restore

    def do_restore(self, pvs_list=None):
        num_pvs = len(pvs_list) if pvs_list else "ALL"
        response = QMessageBox.question(self, "Confirm restore",
                                        "Do you wish to restore "
                                        f"{num_pvs} PVs?")
        if response != QMessageBox.Yes:
            return

        # Restore can be done only if specific file is selected
        if len(self.file_selector.selected_files) == 1:
            file_data = self.file_selector.file_list.get(self.file_selector.selected_files[0])

            # Prepare pvs with values to restore
            if file_data:
                # Ignore parsing errors: the user has already seen them when
                # when opening the snapshot.
                pvs_in_file, _, _ = \
                    parse_from_save_file(file_data['file_path'])
                pvs_to_restore = copy.copy(pvs_in_file)  # is actually a dict
                macros = self.snapshot.macros

                if pvs_list is not None:
                    for pvname in pvs_in_file.keys():
                        if SnapshotPv.macros_substitution(pvname, macros) not in pvs_list:
                            pvs_to_restore.pop(pvname, None)  # remove unfiltered pvs

                force = self.common_settings["force"]

                # Try to restore with default force mode.
                # First disable restore button (will be enabled when finished)
                # Then Use one of the preloaded saved files to restore
                self.restore_all_button.setEnabled(False)
                self.restore_button.setEnabled(False)

                # Force updating the GUI and disabling the button before future actions
                QtCore.QCoreApplication.processEvents()
                self.sts_log.log_msgs("Restore started.", time.time())
                self.sts_info.set_status("Restoring ...", 0, "orange")

                status, pvs_status = self.snapshot.restore_pvs(pvs_to_restore, callback=self.restore_done_callback,
                                                               force=force)

                if status == ActionStatus.no_conn:
                    # Ask user if he wants to force restoring
                    msg = "Some PVs are not connected (see details). Do you want to restore anyway?\n"
                    msg_window = DetailedMsgBox(msg, "\n".join(list(pvs_status.keys())), 'Warning', self)
                    reply = msg_window.exec_()

                    if reply != QMessageBox.No:
                        # Force restore
                        status, pvs_status = self.snapshot.restore_pvs(pvs_to_restore,
                                                                       callback=self.restore_done_callback, force=True)

                        # If here restore started successfully. Waiting for callbacks.

                    else:
                        # User rejected restoring with unconnected PVs. Not an error state.
                        self.sts_log.log_msgs("Restore rejected by user.", time.time())
                        self.sts_info.clear_status()
                        self.restore_all_button.setEnabled(True)
                        self.restore_button.setEnabled(True)

                elif status == ActionStatus.no_data:
                    self.sts_log.log_msgs("ERROR: Nothing to restore.", time.time())
                    self.sts_info.set_status("Restore rejected", 3000, "#F06464")
                    self.restore_all_button.setEnabled(True)
                    self.restore_button.setEnabled(True)

                elif status == ActionStatus.busy:
                    self.sts_log.log_msgs("ERROR: Restore rejected. Previous restore not finished.", time.time())
                    self.restore_all_button.setEnabled(True)
                    self.restore_button.setEnabled(True)

                    # else: ActionStatus.ok  --> waiting for callbacks

            else:
                # Problem reading data from file
                warn = "Cannot start a restore. Problem reading data from selected file."
                QMessageBox.warning(self, "Warning", warn,
                                          QMessageBox.Ok,
                                          QMessageBox.NoButton)
                self.restore_all_button.setEnabled(True)
                self.restore_button.setEnabled(True)

        else:
            # Don't start a restore if file not selected
            warn = "Cannot start a restore. File with saved values is not selected."
            QMessageBox.warning(self, "Warning", warn,
                                      QMessageBox.Ok,
                                      QMessageBox.NoButton)
            self.restore_all_button.setEnabled(True)
            self.restore_button.setEnabled(True)

    def restore_done_callback(self, status, forced, **kw):
        # Raise callback to handle GUI specifics in GUI thread
        self.restored_callback.emit(status, forced)

    def restore_done(self, status, forced):
        # When snapshot finishes restore, GUI must be updated with
        # status of the restore action.
        error = False
        msgs = list()
        msg_times = list()
        status_txt = ""
        status_background = ""
        for pvname, sts in status.items():
            if sts == PvStatus.access_err:
                error = not forced  # if here and not in force mode, then this is error state
                msgs.append("WARNING: {}: Not restored (no connection or no write access).".format(pvname))
                msg_times.append(time.time())
                status_txt = "Restore error"
                status_background = "#F06464"

            elif sts == PvStatus.type_err:
                error = True
                msgs.append("WARNING: {}: Not restored (type problem).".format(pvname))
                msg_times.append(time.time())
                status_txt = "Restore error"
                status_background = "#F06464"

        self.sts_log.log_msgs(msgs, msg_times)

        if not error:
            self.sts_log.log_msgs("Restore finished.", time.time())
            status_txt = "Restore done"
            status_background = "#64C864"

        # Enable button when restore is finished
        self.restore_all_button.setEnabled(True)
        self.restore_button.setEnabled(True)

        if status_txt:
            self.sts_info.set_status(status_txt, 3000, status_background)

    def handle_selected_files(self, selected_files):
        """
        Handle sub widgets and emits signal when files are selected.

        :param selected_files: list of selected file names
        :return:
        """
        if len(selected_files) == 1:
            self.restore_all_button.setEnabled(True)
            self.restore_button.setEnabled(True)
        else:
            self.restore_all_button.setEnabled(False)
            self.restore_button.setEnabled(False)

        selected_data = dict()
        for file_name in selected_files:
            file_data = self.file_selector.file_list.get(file_name, None)
            if file_data:
                selected_data[file_name] = file_data

        # First update other GUI components (compare widget) and then pass pvs to compare to the snapshot core
        self.files_selected.emit(selected_data)

    def rebuild_file_list(self, already_parsed_files=None):
        self.files_updated.emit(
            self.file_selector.rebuild_file_list(
                already_parsed_files))


class SnapshotRestoreFileSelector(QWidget):
    """
    Widget for visual representation (and selection) of existing saved_value
    files.
    """

    files_selected = QtCore.pyqtSignal(list)

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QWidget.__init__(self, parent, **kw)

        self.parent = parent

        self.snapshot = snapshot
        self.selected_files = list()
        self.common_settings = common_settings

        self.file_list = dict()
        self.pvs = dict()

        # Filter handling
        self.file_filter = dict()
        self.file_filter["keys"] = list()
        self.file_filter["comment"] = ""

        self.filter_input = SnapshotFileFilterWidget(
            self.common_settings, self)

        self.filter_input.file_filter_updated.connect(self.filter_file_list_selector)

        # Create list with: file names, comment, labels
        self.file_selector = QTreeWidget(self)
        self.file_selector.setRootIsDecorated(False)
        self.file_selector.setIndentation(0)
        self.file_selector.setColumnCount(len(FileSelectorColumns))
        column_labels = ["File name", "Comment", "Labels"]
        assert(len(column_labels) == len(FileSelectorColumns))
        self.file_selector.setHeaderLabels(column_labels)
        self.file_selector.setAllColumnsShowFocus(True)
        self.file_selector.setSortingEnabled(True)
        # Sort by file name (alphabetical order)
        self.file_selector.sortItems(FileSelectorColumns.filename,
                                     Qt.DescendingOrder)

        self.file_selector.itemSelectionChanged.connect(self.select_files)
        self.file_selector.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_selector.customContextMenuRequested.connect(self.open_menu)

        # Set column sizes
        self.file_selector.resizeColumnToContents(FileSelectorColumns.filename)
        self.file_selector.setColumnWidth(FileSelectorColumns.comment, 350)

        # Applies following behavior for multi select:
        #   click            selects only current file
        #   Ctrl + click     adds current file to selected files
        #   Shift + click    adds all files between last selected and current
        #                    to selected
        self.file_selector.setSelectionMode(QTreeWidget.ExtendedSelection)

        self.filter_file_list_selector()

        # Add to main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter_input)
        layout.addWidget(self.file_selector)

    def handle_new_snapshot_instance(self, snapshot):
        self.clear_file_selector()
        self.filter_input.clear()
        self.snapshot = snapshot

    def rebuild_file_list(self, already_parsed_files=None):
        self.clear_file_selector()
        self.file_selector.setSortingEnabled(False)
        if already_parsed_files:
            save_files, err_to_report = already_parsed_files
        else:
            # Rescans directory and adds new/modified files and removes
            # non-existing ones from the list.
            background_workers.suspend()
            save_dir = self.common_settings["save_dir"]
            req_file_path = self.common_settings["req_file_path"]
            save_files, err_to_report = get_save_files(save_dir, req_file_path)
            background_workers.resume()

        self._update_file_list_selector(save_files)
        self.filter_file_list_selector()

        # Report any errors with snapshot files to the user
        if err_to_report:
            show_snapshot_parse_errors(self, err_to_report)

        self.file_selector.setSortingEnabled(True)
        return save_files

    def _update_file_list_selector(self, file_list):
        new_labels = set()
        for new_file, new_data in file_list.items():
            meta_data = new_data["meta_data"]
            labels = meta_data.get("labels", list())
            comment = meta_data.get("comment", "")

            assert(new_file not in self.file_list)
            row = [new_file, comment, " ".join(labels)]
            assert(len(row) == len(FileSelectorColumns))
            selector_item = QTreeWidgetItem(row)
            self.file_selector.addTopLevelItem(selector_item)
            self.file_list[new_file] = new_data
            self.file_list[new_file]["file_selector"] = selector_item
            new_labels.update(labels)

        self.common_settings["existing_labels"] = new_labels
        self.filter_input.update_labels()

        # Set column sizes
        self.file_selector.resizeColumnToContents(FileSelectorColumns.filename)

    def filter_file_list_selector(self):
        file_filter = self.filter_input.file_filter

        for file_name in self.file_list:
            file_line = self.file_list[file_name]["file_selector"]
            file_to_filter = self.file_list.get(file_name)

            if not file_filter:
                file_line.setHidden(False)
            else:
                keys_filter = file_filter.get("keys")
                comment_filter = file_filter.get("comment")
                name_filter = file_filter.get("name")

                if keys_filter:
                    keys_status = False
                    for key in file_to_filter["meta_data"]["labels"]:
                        # Break when first found
                        if key and (key in keys_filter):
                            keys_status = True
                            break
                else:
                    keys_status = True

                if comment_filter:
                    comment_status = comment_filter in file_to_filter["meta_data"]["comment"]
                else:
                    comment_status = True

                if name_filter:
                    name_status = name_filter in file_name
                else:
                    name_status = True

                # Set visibility if any of the filters conditions met
                file_line.setHidden(
                    not (name_status and keys_status and comment_status))

    def open_menu(self, point):
        item_idx = self.file_selector.indexAt(point)
        if not item_idx.isValid():
            return

        text = item_idx.data()
        field = self.file_selector.model().headerData(item_idx.column(),
                                                      Qt.Horizontal)
        clipboard = QGuiApplication.clipboard()

        menu = QMenu(self)
        menu.addAction(f"Copy {field.lower()}", lambda: clipboard.setText(text))
        menu.addAction("Delete selected files", self.delete_files)
        menu.addAction("Edit file meta-data", self.update_file_metadata)

        menu.exec(QCursor.pos())
        menu.deleteLater()

    def select_files(self):
        # Pre-process selected items, to a list of files
        self.selected_files = list()
        if self.file_selector.selectedItems():
            for item in self.file_selector.selectedItems():
                self.selected_files.append(
                    item.text(FileSelectorColumns.filename))

        self.files_selected.emit(self.selected_files)

    def delete_files(self):
        if self.selected_files:
            msg = "Do you want to delete selected files?"
            reply = QMessageBox.question(self, 'Message', msg, QMessageBox.Yes, QMessageBox.No)
            if reply == QMessageBox.Yes:
                symlink_file = self.common_settings["save_file_prefix"] \
                    + 'latest' + save_file_suffix
                symlink_path = os.path.join(self.common_settings["save_dir"],
                                            symlink_file)
                symlink_target = os.path.realpath(symlink_path)

                files = self.selected_files[:]
                paths = [os.path.join(self.common_settings["save_dir"],
                                      selected_file)
                         for selected_file in self.selected_files]

                if any((path == symlink_target for path in paths)) \
                   and symlink_file not in files:
                    files.append(symlink_file)
                    paths.append(symlink_path)

                for selected_file, file_path in zip(files, paths):
                    try:
                        os.remove(file_path)
                        self.file_list.pop(selected_file)
                        self.pvs = dict()
                        items = self.file_selector.findItems(
                            selected_file, Qt.MatchCaseSensitive,
                            FileSelectorColumns.filename)
                        self.file_selector.takeTopLevelItem(
                            self.file_selector.indexOfTopLevelItem(items[0]))

                    except OSError as e:
                        warn = "Problem deleting file:\n" + str(e)
                        QMessageBox.warning(self, "Warning", warn,
                                                  QMessageBox.Ok,
                                                  QMessageBox.NoButton)

    def update_file_metadata(self):
        if self.selected_files:
            if len(self.selected_files) == 1:
                settings_window = SnapshotEditMetadataDialog(
                    self.file_list.get(self.selected_files[0])["meta_data"],
                    self.common_settings, self)
                settings_window.resize(800, 200)
                # if OK was pressed, update actual file and reflect changes in the list
                if settings_window.exec_():
                    file_data = self.file_list.get(self.selected_files[0])
                    self.snapshot.replace_metadata(file_data['file_path'],
                                                   file_data['meta_data'])
                    self.parent.rebuild_file_list()
            else:
                QMessageBox.information(self, "Information", "Please select one file only",
                                              QMessageBox.Ok,
                                              QMessageBox.NoButton)

    def clear_file_selector(self):
        self.file_selector.clear()  # Clears and "deselects" itmes on file selector
        self.select_files()  # Process new,empty list of selected files
        self.pvs = dict()
        self.file_list = dict()


class SnapshotFileFilterWidget(QWidget):
    """
        Is a widget with 3 filter options:
            - by time (removed)
            - by comment
            - by labels
            - by name

        Emits signal: filter_changed when any of the filter changed.
    """
    file_filter_updated = QtCore.pyqtSignal()

    def __init__(self, common_settings, parent=None, **kw):
        QWidget.__init__(self, parent, **kw)

        self.common_settings = common_settings
        # Create main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Create filter selectors (with readbacks)
        # - text input to filter by name
        # - text input to filter comment
        # - labels selector

        # Init filters
        self.file_filter = dict()
        self.file_filter["keys"] = list()
        self.file_filter["comment"] = ""
        self.file_filter["name"] = ""

        # Labels filter
        key_layout = QHBoxLayout()
        key_label = QLabel("Labels:", self)
        self.keys_input = SnapshotKeywordSelectorWidget(self.common_settings, parent=self)  # No need to force defaults
        self.keys_input.setPlaceholderText("label_1 label_2 ...")
        self.keys_input.keywords_changed.connect(self.update_filter)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.keys_input)

        # Comment filter
        comment_layout = QHBoxLayout()
        comment_label = QLabel("Comment:", self)
        self.comment_input = QLineEdit(self)
        self.comment_input.setPlaceholderText("Filter by comment")
        self.comment_input.textChanged.connect(self.update_filter)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # File name filter
        name_layout = QHBoxLayout()
        name_label = QLabel("Name:", self)
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Filter by name")
        self.name_input.textChanged.connect(self.update_filter)
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)

        layout.addLayout(name_layout)
        layout.addLayout(comment_layout)
        layout.addLayout(key_layout)

    def update_filter(self):
        if self.keys_input.get_keywords():
            self.file_filter["keys"] = self.keys_input.get_keywords()
        else:
            self.file_filter["keys"] = list()
        self.file_filter["comment"] = self.comment_input.text().strip('')
        self.file_filter["name"] = self.name_input.text().strip('')

        self.file_filter_updated.emit()

    def update_labels(self):
        self.keys_input.update_suggested_keywords()

    def clear(self):
        self.keys_input.clear_keywords()
        self.name_input.setText('')
        self.comment_input.setText('')
        self.update_filter()
