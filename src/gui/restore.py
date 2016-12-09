#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import copy
import datetime
import os
import time

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from ..ca_core import PvStatus, ActionStatus, SnapshotPv
from .utils import SnapshotKeywordSelectorWidget, SnapshotEditMetadataDialog, DetailedMsgBox


class SnapshotRestoreWidget(QtGui.QWidget):
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
        QtGui.QWidget.__init__(self, parent, **kw)

        self.snapshot = snapshot
        self.common_settings = common_settings
        self.filtered_pvs = list()
        # dict of available files to avoid multiple openings of one file when
        # not needed.
        self.file_list = dict()

        # Create main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Create list with: file names, comment, labels
        self.file_selector = SnapshotRestoreFileSelector(snapshot,
                                                         common_settings, self)

        self.file_selector.files_selected.connect(self.handle_selected_files)

        # Make restore buttons
        self.restore_button = QtGui.QPushButton("Restore Filtered", self)
        self.restore_button.clicked.connect(self.start_restore_filtered)
        self.restore_button.setToolTip("Restores only currently filtered PVs from the selected .snap file.")

        self.restore_all_button = QtGui.QPushButton("Restore All", self)
        self.restore_all_button.clicked.connect(self.start_restore_all)
        self.restore_all_button.setToolTip("Restores all PVs from the selected .snap file.")

        btn_layout = QtGui.QHBoxLayout()
        btn_layout.addWidget(self.restore_all_button)
        btn_layout.addWidget(self.restore_button)

        # Link to status widgets
        self.sts_log = self.common_settings["sts_log"]
        self.sts_info = self.common_settings["sts_info"]

        # Add all widgets to main layout
        layout.addWidget(self.file_selector)
        layout.addLayout(btn_layout)

        self.restored_callback.connect(self.restore_done)

    def handle_new_snapshot_instance(self, snapshot):
        self.file_selector.handle_new_snapshot_instance(snapshot)
        self.snapshot = snapshot
        self.clear_update_files()

    def start_restore_all(self):
        self.do_restore()

    def start_restore_filtered(self):
        filtered_n = len(self.filtered_pvs)

        if filtered_n == len(self.snapshot.pvs):  # all pvs selected
            self.do_restore()  # This way functions below skip unnecessary checks
        elif filtered_n:
            self.do_restore(filtered_only=True)
            # Do not start a restore if nothing to restore

    def do_restore(self, filtered_only=False):
        # Check if restore can be done (values loaded to snapshot).
        if filtered_only:
            filtered = self.filtered_pvs
        else:
            filtered = None

        # Restore can be done only if specific file is selected
        if len(self.file_selector.selected_files) == 1:
            file_data = self.file_selector.file_list.get(self.file_selector.selected_files[0])

            # Prepare pvs with values to restore
            if file_data:
                pvs_in_file = file_data.get("pvs_list", None)  # is actually a dict
                pvs_to_restore = copy.copy(file_data.get("pvs_list", None))  # is actually a dict
                macros = self.snapshot.macros

                if filtered is not None:
                    for pvname in pvs_in_file.keys():
                        if SnapshotPv.macros_substitution(pvname, macros) not in filtered:
                            pvs_to_restore.pop(pvname, None)  # remove unfiltered pvs

            # Check if all pvs connected or in force mode)
            force = self.common_settings["force"]
            not_connected_pvs = self.snapshot.get_disconnected_pvs_names(filtered)
            do_restore = True
            if not force and not_connected_pvs:
                msg = "Some PVs are not connected (see details). Do you want to restore anyway?\n"
                msg_window = DetailedMsgBox(msg, "\n".join(not_connected_pvs), 'Warning', self)
                reply = msg_window.exec_()

                if reply == QtGui.QMessageBox.No:
                    force = False
                    do_restore = False
                else:
                    force = True

            if do_restore:
                # First disable restore button (will be enabled when finished)
                # Then Use one of the preloaded saved files to restore
                self.restore_all_button.setEnabled(False)
                self.restore_button.setEnabled(False)

                # Force updating the GUI and disabling the button before future actions
                QtCore.QCoreApplication.processEvents()
                self.sts_log.log_msgs("Restore started.", time.time())
                self.sts_info.set_status("Restoring ...", 0, "orange")

                status = self.snapshot.restore_pvs(pvs_to_restore, callback=self.restore_done_callback,
                                                   force=force)
                if status == ActionStatus.no_data:
                    # Because of checking "restore_values_loaded" before
                    # starting a restore, this case should not happen.
                    self.sts_log.log_msgs("ERROR: Nothing to restore.", time.time())
                    self.sts_info.set_status("Restore rejected", 3000, "#F06464")
                    self.restore_all_button.setEnabled(True)
                    self.restore_button.setEnabled(True)
                elif status == ActionStatus.no_conn:
                    self.sts_log.log_msgs("ERROR: Restore rejected. One or more PVs not connected.", time.time())
                    self.sts_info.set_status("Restore rejected", 3000, "#F06464")
                    self.restore_all_button.setEnabled(True)
                    self.restore_button.setEnabled(True)
                elif status == ActionStatus.busy:
                    self.sts_log.log_msgs("ERROR: Restore rejected. Previous restore not finished.", time.time())
        else:
            # Don't start a restore if file not selected
            warn = "Cannot start a restore. File with saved values is not selected."
            QtGui.QMessageBox.warning(self, "Warning", warn,
                                      QtGui.QMessageBox.Ok,
                                      QtGui.QMessageBox.NoButton)

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
                error = not forced  #if here and not in force mode, then this is error state
                msgs.append("WARNING: {}: Not restored (no connection or no read access)".format(pvname))
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

        # Prepare for restore if one specific file is selected, or clear
        # restore data if none specific file is selected.
        selected_data = dict()
        for file_name in selected_files:
            file_data = self.file_selector.file_list.get(file_name, None)
            if file_data:
                selected_data[file_name] = file_data

        # First update other GUI components (compare widget) and then pass pvs to compare to the snapshot core
        self.files_selected.emit(selected_data)

    def update_files(self):
        self.files_updated.emit(self.file_selector.start_file_list_update())

    def clear_update_files(self):
        self.file_selector.clear_file_selector()
        self.update_files()


class SnapshotRestoreFileSelector(QtGui.QWidget):
    """
    Widget for visual representation (and selection) of existing saved_value
    files.
    """

    files_selected = QtCore.pyqtSignal(list)

    def __init__(self, snapshot, common_settings, parent=None, save_file_sufix=".snap", **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.parent = parent

        self.snapshot = snapshot
        self.selected_files = list()
        self.common_settings = common_settings
        self.save_file_sufix = save_file_sufix

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
        self.file_selector = QtGui.QTreeWidget(self)
        self.file_selector.setRootIsDecorated(False)
        self.file_selector.setIndentation(0)
        self.file_selector.setColumnCount(4)
        self.file_selector.setHeaderLabels(["", "File", "Comment", "Labels"])
        self.file_selector.headerItem().setIcon(0, QtGui.QIcon(
            os.path.join(os.path.dirname(os.path.realpath(__file__)), "images/clock.png")))
        self.file_selector.setAllColumnsShowFocus(True)
        self.file_selector.setSortingEnabled(True)
        # Sort by file name (alphabetical order)
        self.file_selector.sortItems(1, Qt.AscendingOrder)

        self.file_selector.itemSelectionChanged.connect(self.select_files)
        self.file_selector.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_selector.customContextMenuRequested.connect(self.open_menu)

        # Set column sizes
        self.file_selector.resizeColumnToContents(1)
        self.file_selector.setColumnWidth(0, 60)
        self.file_selector.setColumnWidth(2, 350)

        # Applies following behavior for multi select:
        #   click            selects only current file
        #   Ctrl + click     adds current file to selected files
        #   Shift + click    adds all files between last selected and current
        #                    to selected
        self.file_selector.setSelectionMode(QtGui.QTreeWidget.ExtendedSelection)

        self.filter_file_list_selector()

        # Add to main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(0)
        layout.addWidget(self.filter_input)
        layout.addWidget(self.file_selector)

        # Context menu
        self.menu = QtGui.QMenu(self)
        self.menu.addAction("Delete selected files", self.delete_files)
        self.menu.addAction("Edit file meta-data", self.update_file_metadata)

    def handle_new_snapshot_instance(self, snapshot):
        self.clear_file_selector()
        self.filter_input.clear()
        self.snapshot = snapshot

    def start_file_list_update(self):
        self.file_selector.setSortingEnabled(False)
        # Rescans directory and adds new/modified files and removes none
        # existing ones from the list.
        save_files, err_to_report = self.get_save_files(self.common_settings["save_dir"], self.file_list)

        updated_files = self.update_file_list_selector(save_files)

        self.filter_file_list_selector()
        # Report any errors with snapshot files to the user
        err_details = ""
        if err_to_report:
            for item in err_to_report:
                if item[1]:  # list of errors

                    err_details += '- - - ' + item[0] + \
                                   ' - - -\n * '  # file name
                    err_details += '\n * '.join(item[1])
                    err_details += '\n\n'

            err_details = err_details[:-2]  # Remove last two new lines

        if err_details:
            msg = str(len(err_to_report)) + " of the snapshot saved files (.snap) were loaded with errors " \
                                            "(see details)."
            msg_window = DetailedMsgBox(msg, err_details, 'Warning', self, QtGui.QMessageBox.Ok)
            msg_window.exec_()

        self.file_selector.setSortingEnabled(True)
        return updated_files

    def get_save_files(self, save_dir, current_files):
        # Parses all new or modified files. Parsed files are returned as a
        # dictionary.
        parsed_save_files = dict()
        err_to_report = list()
        req_file_name = os.path.basename(self.common_settings["req_file_path"])
        # Check if any file added or modified (time of modification)
        for file_name in os.listdir(save_dir):
            file_path = os.path.join(save_dir, file_name)
            if os.path.isfile(file_path) and file_name.endswith(self.save_file_sufix):
                if (file_name not in current_files) or \
                        (current_files[file_name]["modif_time"] != os.path.getmtime(file_path)):

                    pvs_list, meta_data, err = self.snapshot.parse_from_save_file(
                        file_path)

                    # check if we have req_file metadata. This is used to determine which
                    # request file the save file belongs to.
                    # If there is no metadata (or no req_file specified in the metadata)
                    # we search using a prefix of the request file.
                    # The latter is less robust, but is backwards compatible.
                    if ("req_file_name" in meta_data and meta_data["req_file_name"] == req_file_name) \
                            or file_name.startswith(req_file_name.split(".")[0] + "_"):
                        # we really should have basic meta data
                        # (or filters and some other stuff will silently fail)
                        if "comment" not in meta_data:
                            meta_data["comment"] = ""
                        if "labels" not in meta_data:
                            meta_data["labels"] = []

                        # save data (no need to open file again later))
                        parsed_save_files[file_name] = dict()
                        parsed_save_files[file_name]["pvs_list"] = pvs_list
                        parsed_save_files[file_name]["meta_data"] = meta_data
                        parsed_save_files[file_name]["modif_time"] = os.path.getmtime(file_path)

                        if err:  # report errors only for matching saved files
                            err_to_report.append((file_name, err))

        return parsed_save_files, err_to_report

    def update_file_list_selector(self, modif_file_list):

        existing_labels = self.common_settings["existing_labels"]

        for modified_file, modified_data in modif_file_list.items():
            meta_data = modified_data["meta_data"]
            labels = meta_data.get("labels", list())
            comment = meta_data.get("comment", "")
            time = datetime.datetime.fromtimestamp(modified_data.get("modif_time", 0)).strftime('%Y/%m/%d %H:%M:%S')

            # check if already on list (was just modified) and modify file
            # selector
            if modified_file not in self.file_list:
                selector_item = QtGui.QTreeWidgetItem([time, modified_file, comment, " ".join(labels)])
                self.file_selector.addTopLevelItem(selector_item)
                self.file_list[modified_file] = modified_data
                self.file_list[modified_file]["file_selector"] = selector_item
                existing_labels += list(set(labels) - set(existing_labels))

            else:
                # If everything ok only one file should exist in list. Update
                # its data
                modified_file_ref = self.file_list[modified_file]
                old_meta_data = modified_file_ref["meta_data"]

                # Before following actions, update the list of labels from
                # which might change in the modified file. Remove unused labels
                # and add new.
                old_labels = old_meta_data["labels"]
                labels_to_add = list(set(labels) - set(old_labels))
                labels_to_remove = list(set(old_labels) - set(labels))

                existing_labels += labels_to_add

                # Update the global data meta_data info, before checking if
                # labels_to_remove are used in any of the files.
                self.file_list[modified_file]["meta_data"] = meta_data
                self.file_list[modified_file]["pvs_list"] = modified_data["pvs_list"]

                # Check if can be removed (no other file has the same label)
                if labels_to_remove:
                    # Check all loaded files if label is in use
                    in_use = [False] * len(labels_to_remove)
                    for laoded_file in self.file_list.keys():
                        loaded_file_labels = self.file_list[
                            laoded_file]["meta_data"]["labels"]
                        i = 0
                        for label in labels_to_remove:
                            in_use[i] = in_use[i] or label in loaded_file_labels
                            i += 1
                    i = 0
                    for label in labels_to_remove:
                        if not in_use[i]:
                            existing_labels.remove(label)
                        i += 1

                # Modify visual representation
                item_to_modify = modified_file_ref["file_selector"]
                item_to_modify.setText(0, time)
                item_to_modify.setText(2, comment)
                item_to_modify.setText(3, " ".join(labels))
        self.filter_input.update_labels()

        # Set column sizes
        self.file_selector.resizeColumnToContents(1)
        return modif_file_list

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
        self.menu.show()
        pos = self.file_selector.mapToGlobal(point)
        pos += QtCore.QPoint(0, self.menu.sizeHint().height())
        self.menu.move(pos)

    def select_files(self):
        # Pre-process selected items, to a list of files
        self.selected_files = list()
        if self.file_selector.selectedItems():
            for item in self.file_selector.selectedItems():
                self.selected_files.append(item.text(1))

        self.files_selected.emit(self.selected_files)

    def delete_files(self):
        if self.selected_files:
            msg = "Do you want to delete selected files?"
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)
            if reply == QtGui.QMessageBox.Yes:
                for selected_file in self.selected_files:
                    try:
                        file_path = os.path.join(self.common_settings["save_dir"],
                                                 selected_file)
                        os.remove(file_path)
                        self.file_list.pop(selected_file)
                        self.pvs = dict()
                        self.file_selector.takeTopLevelItem(
                            self.file_selector.indexOfTopLevelItem(self.file_selector.findItems(
                                selected_file, Qt.MatchCaseSensitive, 1)[0]))

                    except OSError as e:
                        warn = "Problem deleting file:\n" + str(e)
                        QtGui.QMessageBox.warning(self, "Warning", warn,
                                                  QtGui.QMessageBox.Ok,
                                                  QtGui.QMessageBox.NoButton)

    def update_file_metadata(self):
        if self.selected_files:
            if len(self.selected_files) == 1:
                settings_window = SnapshotEditMetadataDialog(
                    self.file_list.get(self.selected_files[0])["meta_data"],
                    self.common_settings, self)
                settings_window.resize(800, 200)
                # if OK was pressed, update actual file and reflect changes in the list
                if settings_window.exec_():
                    self.snapshot.replace_metadata(self.selected_files[0],
                                                   self.file_list.get(self.selected_files[0])["meta_data"])
                    self.parent.clear_update_files()
            else:
                QtGui.QMessageBox.information(self, "Information", "Please select one file only",
                                              QtGui.QMessageBox.Ok,
                                              QtGui.QMessageBox.NoButton)

    def clear_file_selector(self):
        self.file_selector.clear()  # Clears and "deselects" itmes on file selector
        self.select_files()  # Process new,empty list of selected files
        self.pvs = dict()
        self.file_list = dict()


class SnapshotFileFilterWidget(QtGui.QWidget):
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
        QtGui.QWidget.__init__(self, parent, **kw)

        self.common_settings = common_settings
        # Create main layout
        layout = QtGui.QHBoxLayout(self)
        layout.setMargin(0)
        layout.setSpacing(10)
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
        key_layout = QtGui.QHBoxLayout()
        key_label = QtGui.QLabel("Labels:", self)
        self.keys_input = SnapshotKeywordSelectorWidget(self.common_settings, parent=self)  # No need to force defaults
        self.keys_input.setPlaceholderText("label_1 label_2 ...")
        self.keys_input.keywords_changed.connect(self.update_filter)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.keys_input)

        # Comment filter
        comment_layout = QtGui.QHBoxLayout()
        comment_label = QtGui.QLabel("Comment:", self)
        self.comment_input = QtGui.QLineEdit(self)
        self.comment_input.setPlaceholderText("Filter by comment")
        self.comment_input.textChanged.connect(self.update_filter)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # File name filter
        name_layout = QtGui.QHBoxLayout()
        name_label = QtGui.QLabel("Name:", self)
        self.name_input = QtGui.QLineEdit(self)
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
