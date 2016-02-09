#!/usr/bin/env python
import sys
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import pyqtSlot, Qt, SIGNAL
import time
import datetime
import argparse
import re
from enum import Enum
import os
from .snapshot_ca import PvStatus, ActionStatus, Snapshot
import json
import numpy
import epics

# close with ctrl+C
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)


# Define enums
class PvViewStatus(Enum):
    eq = 0
    neq = 1
    err = 2


class PvCompareFilter(Enum):
    show_all = 0
    show_neq = 1
    show_eq = 2


class SnapshotGui(QtGui.QMainWindow):

    """
    Main GUI class for Snapshot application. It needs separate working
    thread where core of the application is running
    """

    def __init__(self, req_file_name=None, req_file_macros=None,
                 save_dir=None, force=False, parent=None):
        QtGui.QMainWindow.__init__(self, parent)

        self.resize(1500, 850)

        # common_settings is a dictionary which holds common configuration of
        # the application (such as directory with save files, request file
        # path, etc). It is propagated to other snapshot widgets if needed
        self.common_settings = dict()
        self.common_settings["req_file_name"] = ""
        self.common_settings["req_file_macros"] = dict()
        self.common_settings["existing_labels"] = list()
        self.common_settings["force"] = force

        if not req_file_name:
            self.configure_dialog = SnapshotConfigureDialog(self)
            self.configure_dialog.accepted.connect(self.set_request_file)
            self.configure_dialog.rejected.connect(self.close_gui)

            self.hide()
            self.configure_dialog.exec_()

        else:
            self.common_settings["req_file_name"] = req_file_name
            self.common_settings["req_file_macros"] = req_file_macros

        if not save_dir:
            # Default save dir
            save_dir = os.path.dirname(self.common_settings["req_file_name"])

        self.common_settings["save_dir"] = save_dir
        self.common_settings["pvs_to_restore"] = list()

        # Before creating GUI, snapshot must be initialized.
        self.init_snapshot(self.common_settings["req_file_name"],
                           self.common_settings["req_file_macros"])

        # Create main GUI components:
        #       | save_widget | restore_widget |
        #       --------------------------------
        #       |        compare_widget        |
        #       --------------------------------
        #       |            sts_log           |
        #        ______________________________
        #                   status_bar
        #

        # Status components are needed by other GUI elements
        status_log = SnapshotStatusLog(self)
        self.common_settings["sts_log"] = status_log
        status_bar = SnapshotStatus(self.common_settings, self)
        self.common_settings["sts_info"] = status_bar

        # Creating main layout
        self.save_widget = SnapshotSaveWidget(self.snapshot,
                                              self.common_settings, self)
        self.connect(self.save_widget, SIGNAL("save_done"),
                     self.handle_save_done)
        self.restore_widget = SnapshotRestoreWidget(self.snapshot,
                                                    self.common_settings, self)
        # If new files were added to restore list, all elements with Labels
        # should update with new existing labels. Force update for first time
        self.connect(self.restore_widget, SIGNAL("files_updated"),
                     self.handle_files_updated)
        self.handle_files_updated()

        self.compare_widget = SnapshotCompareWidget(self.snapshot,
                                                    self.common_settings, self)
        sr_splitter = QtGui.QSplitter(self)
        sr_splitter.addWidget(self.save_widget)
        sr_splitter.addWidget(self.restore_widget)
        element_size = (
            self.save_widget.sizeHint().width() + self.restore_widget.sizeHint().width())/2
        sr_splitter.setSizes([element_size, element_size])

        main_splitter = QtGui.QSplitter(self)
        main_splitter.addWidget(sr_splitter)
        main_splitter.addWidget(self.compare_widget)
        main_splitter.addWidget(self.compare_widget)
        main_splitter.addWidget(status_log)
        main_splitter.setOrientation(Qt.Vertical)

        # Set default widget and add status bar
        self.setCentralWidget(main_splitter)
        self.setStatusBar(status_bar)

        # Show GUI and manage window properties
        self.show()
        self.setWindowTitle(
            os.path.basename(self.common_settings["req_file_name"]) + ' - Snapshot')

        # Status log default height should be 100px Set with splitter methods
        widgets_sizes = main_splitter.sizes()
        widgets_sizes[main_splitter.indexOf(main_splitter)] = 100
        main_splitter.setSizes(widgets_sizes)

    def handle_save_done(self):
        # When save is done, save widget is updated by itself
        # Update restore widget (new file in directory)
        self.restore_widget.update_files()

    def set_request_file(self):
        self.common_settings["req_file_name"] = self.configure_dialog.file_path
        self.common_settings["req_file_macros"] = self.configure_dialog.macros

    def close_gui(self):
        sys.exit()

    def init_snapshot(self, req_file_path, req_macros=None):
        # creates new instance of snapshot loads the request file and emits
        # the signal new_snapshot to update the GUI
        self.snapshot = Snapshot(req_file_path, req_macros)
        self.common_settings["pvs_to_restore"] = self.snapshot.get_pvs_names()

    def handle_files_updated(self):
        # When new save file is added, or old one has changed, this method
        # should handle thongs like updating label widgets.
        self.save_widget.update_labels()


class SnapshotSaveWidget(QtGui.QWidget):

    """
    Save widget is a widget that enables user to save current state of PVs
    listed in request file. Widget includes:
    Save widget consists of:
     - input-fields:
        * file extension (default YYMMDD_hhmm)
        * comment
        * labels
     - read-back showing whole file name
     - Save button

    Data about current app state (such as request file) must be provided as
    part of the structure "common_settings".
    """

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.common_settings = common_settings
        self.snapshot = snapshot

        # Default saved file name: If req file name is PREFIX.req, then saved
        # file name is: PREFIX_YYMMDD_hhmmss (holds time info)
        # Get the prefix ... use update_name() later
        self.save_file_sufix = ".snap"
        self.name_base = os.path.split(
            common_settings["req_file_name"])[1].split(".")[0] + "_"

        # Create layout and add GUI elements (input fields, buttons, ...)
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)
        min_label_width = 120

        # Make a field to select file extension (has a read-back)
        extension_layout = QtGui.QHBoxLayout()
        extension_layout.setSpacing(10)
        extension_label = QtGui.QLabel("Name extension:", self)
        extension_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        extension_label.setMinimumWidth(min_label_width)
        self.extension_input = QtGui.QLineEdit(self)

        extension_layout.addWidget(extension_label)
        extension_layout.addWidget(self.extension_input)

        # "Monitor" any name changes (by user, or by other methods)
        extension_rb_layout = QtGui.QHBoxLayout()
        extension_rb_layout.setSpacing(10)
        self.extension_input.textChanged.connect(self.update_name)
        file_name_label = QtGui.QLabel("File name: ", self)
        file_name_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        file_name_label.setMinimumWidth(min_label_width)
        self.file_name_rb = QtGui.QLabel(self)
        self.update_name()

        extension_rb_layout.addWidget(file_name_label)
        extension_rb_layout.addWidget(self.file_name_rb)
        extension_rb_layout.addStretch()

        # Make a field to enable user adding a comment
        comment_layout = QtGui.QHBoxLayout()
        comment_layout.setSpacing(10)
        comment_label = QtGui.QLabel("Comment:", self)
        comment_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        comment_label.setMinimumWidth(min_label_width)
        self.comment_input = QtGui.QLineEdit(self)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Make field for labels
        labels_layout = QtGui.QHBoxLayout()
        labels_layout.setSpacing(10)
        labels_label = QtGui.QLabel("Labels:", self)
        labels_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        labels_label.setMinimumWidth(min_label_width)
        self.labels_input = SnapshotKeywordSelectorWidget(
            self.common_settings, self)
        labels_layout.addWidget(labels_label)
        labels_layout.addWidget(self.labels_input)

        # Make Save button, status indicator and save report
        save_layout = QtGui.QHBoxLayout()
        save_layout.setSpacing(10)
        self.save_button = QtGui.QPushButton("Save", self)
        self.save_button.clicked.connect(self.start_save)

        save_layout.addWidget(self.save_button)

        # Status widgets
        self.sts_log = self.common_settings["sts_log"]
        self.sts_info = self.common_settings["sts_info"]

        # Add to main layout
        layout.addItem(extension_layout)
        layout.addItem(extension_rb_layout)
        layout.addItem(comment_layout)
        layout.addItem(labels_layout)
        layout.addStretch()
        layout.addItem(save_layout)

    def start_save(self):
        # Update file name and chek if exists. Then disable button for the time
        # of saving. Will be unlocked when save is finished.
        if not self.extension_input.text():
            #  Update name with latest timestamp
            self.update_name()

        if self.check_file_existance():
            self.save_button.setEnabled(False)
            self.sts_log.log_line("Save started.")
            self.sts_info.set_status("Saving ...", 0, "orange")

            # Start saving process and notify when finished
            status, pvs_status = self.snapshot.save_pvs(self.file_path,
                                                        force=self.common_settings[
                                                            "force"],
                                                        labels=self.labels_input.get_keywords(),
                                                        comment=self.comment_input.text())
            if status == ActionStatus.no_cnct:
                self.sts_log.log_line(
                    "ERROR: Save rejected. One or more PVs not connected.")
                self.sts_info.set_status("Cannot save", 3000, "#F06464")
                self.save_button.setEnabled(True)
            else:
                # If not no_cnct, then .ok
                self.save_done(pvs_status)
        else:
            # User rejected saving into same file. No error.
            self.sts_info.clear_status()

    def save_done(self, status):
        # Enable save button, and update status widgets
        error = False
        for key in status:
            sts = status[key]
            if status[key] == PvStatus.access_err:
                error = True and not self.common_settings["force"]
                self.sts_log.log_line("WARNING: " + key +
                                      ": Not saved (no connection or no read access)")

                status_txt = "Save error"
                status_background = "#F06464"

        if not error:
            self.sts_log.log_line("Save successful.")
            status_txt = "Save done"
            status_background = "#64C864"

        self.save_button.setEnabled(True)
        self.sts_info.set_status(status_txt, 3000, status_background)

        self.emit(SIGNAL("save_done"))

    def update_name(self):
        # When file extension is changed, update all corresponding variables
        name_extension_inp = self.extension_input.text()
        if not name_extension_inp:
            name_extension_rb = "{TIMESTAMP}" + self.save_file_sufix
            self.name_extension = datetime.datetime.fromtimestamp(
                time.time()).strftime('%Y%m%d_%H%M%S')
        else:
            self.name_extension = name_extension_inp
            name_extension_rb = name_extension_inp + self.save_file_sufix
        self.file_path = os.path.join(self.common_settings["save_dir"],
                                      self.name_base + self.name_extension +
                                      self.save_file_sufix)
        self.file_name_rb.setText(self.name_base + name_extension_rb)

    def check_file_existance(self):
        # If file exists, user must decide whether to overwrite it or not
        if os.path.exists(self.file_path):
            msg = "File already exists. Do you want to overwrite it?\n" + \
                  self.file_path
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)

            if reply == QtGui.QMessageBox.No:
                return False
        return True

    def update_labels(self):
        self.labels_input.update_sugested_keywords()


class SnapshotRestoreWidget(QtGui.QWidget):

    """
    restore widget is a widget that enables user to restore saved state of PVs
    listed in request file from one of the saved files.
    Save widget consists of:
     - file selector (tree of all files)
     - restore button
     - searcher/filter

    It also owns a compare widget.

    Data about current app state (such as request file) must be provided as
    part of the structure "common_settings".
    """

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.snapshot = snapshot
        self.common_settings = common_settings
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
        self.connect(self.file_selector, SIGNAL("new_pvs"),
                     self.load_new_pvs)

        self.restore_button = QtGui.QPushButton("Restore", self)
        self.restore_button.clicked.connect(self.start_restore)

        # Status widgets
        self.sts_log = self.common_settings["sts_log"]
        self.sts_info = self.common_settings["sts_info"]

        # Create file list for first time and update the GUI with new data
        # (label widgets)
        self.update_files()

        # Add all widgets to main layout
        layout.addWidget(self.file_selector)
        layout.addWidget(self.restore_button)

        self.connect(self, SIGNAL("restore_done_callback"), self.restore_done)

    def start_restore(self):
        # First disable restore button (will be enabled when finished)
        # Then Use one of the preloaded saved files to restore
        self.restore_button.setEnabled(False)
        # Force updating the GUI and disabling the button before future actions
        QtCore.QCoreApplication.processEvents()
        self.sts_log.log_line("Restore started.")
        self.sts_info.set_status("Restoring ...", 0, "orange")
        # Force updating the GUI with new status
        QtCore.QCoreApplication.processEvents()

        status = self.snapshot.restore_pvs(callback=self.restore_done_callback,
                                           force=self.common_settings["force"])
        if status == ActionStatus.no_data:
            self.sts_log.log_line("ERROR: No file selected.")
            self.sts_info.set_status("Restore rejected", 3000, "#F06464")
            self.restore_button.setEnabled(True)
        elif status == ActionStatus.no_cnct:
            self.sts_log.log_line(
                "ERROR: Restore rejected. One or more PVs not connected.")
            self.sts_info.set_status("Restore rejected", 3000, "#F06464")
            self.restore_button.setEnabled(True)
        elif status == ActionStatus.busy:
            self.sts_log.log_line(
                "ERROR: Restore rejected. Previous restore not finished.")

    def restore_done_callback(self, status, **kw):
        # Raise callback to handle GUI specific in GUI thread
        self.emit(SIGNAL("restore_done_callback"), status)

    def restore_done(self, status):
        # When snapshot finishes restore, GUI must be updated with
        # status of the restore action.
        error = False
        if not status:
            error = True
            self.sts_log.log_line("ERROR: No file selected.")
            self.sts_info.set_status("Cannot restore", 3000, "#F06464")
        else:
            for key in status:
                pv_status = status[key]
                if pv_status == PvStatus.access_err:
                    error = True and not self.common_settings["force"]
                    self.sts_log.log_line("WARNING: " + key +
                                          ": Not restored (no connection or no write access).")
                    self.sts_info.set_status("Restore error", 3000, "#F06464")
        if not error:
            self.sts_log.log_line("Restore successful.")
            self.sts_info.set_status("Restore done", 3000, "#64C864")

        # Enable button when restore is finished
        self.restore_button.setEnabled(True)

    def load_new_pvs(self):
        self.snapshot.prepare_pvs_to_restore_from_list(self.file_selector.pvs)

    def update_files(self):
        self.file_selector.start_file_list_update()
        self.emit(SIGNAL("files_updated"))


class SnapshotRestoreFileSelector(QtGui.QWidget):

    """
    Widget for visual representation (and selection) of existing saved_value
    files.
    """

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.snapshot = snapshot
        self.selected_file = None
        self.common_settings = common_settings

        self.file_list = dict()
        self.pvs = dict()

        # Filter handling
        self.file_filter = dict()
        self.file_filter["keys"] = list()
        self.file_filter["comment"] = ""

        self.filter_input = SnapshotFileFilterWidget(
            self.common_settings, self)

        self.connect(self.filter_input, SIGNAL(
            "file_filter_updated"), self.filter_file_list_selector)

        # Create list with: file names, comment, labels
        self.file_selector = QtGui.QTreeWidget(self)
        self.file_selector.setRootIsDecorated(False)
        self.file_selector.setIndentation(0)
        self.file_selector.setColumnCount(3)
        self.file_selector.setHeaderLabels(["File", "Comment", "Labels"])
        self.file_selector.setAlternatingRowColors(True)
        self.file_selector.itemSelectionChanged.connect(self.choose_file)
        self.file_selector.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_selector.customContextMenuRequested.connect(self.open_menu)

        self.filter_file_list_selector()

        # Add to main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(0)
        layout.addWidget(self.filter_input)
        layout.addWidget(self.file_selector)

        # Context menu
        self.menu = QtGui.QMenu(self)
        self.menu.addAction("Delete file", self.delete_file)

    def start_file_list_update(self):
        # Rescans directory and adds new/modified files and removes none
        # existing ones from the list.
        file_prefix = os.path.split(
            self.common_settings["req_file_name"])[1].split(".")[0] + "_"

        self.update_file_list_selector(self.get_save_files(self.common_settings["save_dir"],
                                                           file_prefix,
                                                           self.file_list))
        self.filter_file_list_selector()

    def get_save_files(self, save_dir, name_prefix, current_files):
        # Parses all new or modified files. Parsed files are returned as a
        # dictionary.
        parsed_save_files = dict()
        # Check if any file added or modified (time of modification)
        for file_name in os.listdir(save_dir):
            file_path = os.path.join(save_dir, file_name)
            if os.path.isfile(file_path) and file_name.startswith(name_prefix):
                if (file_name not in current_files) or \
                   (current_files[file_name]["modif_time"] != os.path.getmtime(file_path)):

                    pvs_list, meta_data = self.snapshot.parse_from_save_file(
                        file_path)

                    # save data (no need to open file again later))
                    parsed_save_files[file_name] = dict()
                    parsed_save_files[file_name]["pvs_list"] = pvs_list
                    parsed_save_files[file_name]["meta_data"] = meta_data
                    parsed_save_files[file_name][
                        "modif_time"] = os.path.getmtime(file_path)

        return parsed_save_files

    def update_file_list_selector(self, file_list):

        existing_labels = self.common_settings["existing_labels"]

        for modified_file in file_list:
            meta_data = file_list[modified_file]["meta_data"]
            labels = meta_data.get("labels", list())
            comment = meta_data.get("comment", "")

            # check if already on list (was just modified) and modify file
            # selector
            if modified_file not in self.file_list:
                selector_item = QtGui.QTreeWidgetItem(
                    [modified_file, comment, " ".join(labels)])
                self.file_selector.addTopLevelItem(selector_item)
                self.file_list[modified_file] = file_list[modified_file]
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

                # Check if can be removed (no other file has the same label)
                if labels_to_remove:
                    # Check all loaded files if label is in use
                    in_use = [False] * len(labels_to_remove)
                    for laoded_file in self.file_list.keys():
                        loaded_file_labels = self.file_list[
                            laoded_file]["meta_data"]["labels"]
                        i = 0
                        for label in labels_to_remove:
                            in_use[i] = in_use[
                                i] or label in loaded_file_labels
                            i += 1
                    i = 0
                    for label in labels_to_remove:
                        if not in_use[i]:
                            existing_labels.remove(label)
                        i += 1

                # Modify visual representation
                item_to_modify = modified_file_ref["file_selector"]
                item_to_modify.setText(1, comment)
                item_to_modify.setText(2, " ".join(labels))
        self.filter_input.update_labels()

        # Set column sizes
        self.file_selector.resizeColumnToContents(0)
        self.file_selector.setColumnWidth(1, 350)

        # Sort by file name (alphabetical order)
        self.file_selector.sortItems(0, Qt.AscendingOrder)

    def filter_file_list_selector(self):
        file_filter = self.filter_input.file_filter

        for key in self.file_list:
            file_line = self.file_list[key]["file_selector"]
            file_to_filter = self.file_list.get(key)

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
                    comment_status = comment_filter in file_to_filter[
                        "meta_data"]["comment"]
                else:
                    comment_status = True

                if name_filter:
                    name_status = name_filter in key
                else:
                    name_status = True

                # Set visibility if any of the filters conditions met
                file_line.setHidden(
                    not(name_status and keys_status and comment_status))

    def open_menu(self, point):
        self.menu.show()
        pos = self.file_selector.mapToGlobal(point)
        pos += QtCore.QPoint(0, self.menu.sizeHint().height())
        self.menu.move(pos)

    def choose_file(self):
        if self.file_selector.selectedItems():
            self.selected_file = self.file_selector.selectedItems()[0].text(0)
            self.pvs = self.file_list[self.selected_file]["pvs_list"]

        self.emit(SIGNAL("new_pvs"))

    def delete_file(self):
        if self.selected_file:
            file_path = os.path.join(self.common_settings["save_dir"],
                                     self.selected_file)

            msg = "Do you want to delete file: " + file_path + "?"
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)
            if reply == QtGui.QMessageBox.Yes:
                try:
                    os.remove(file_path)
                    self.file_list.pop(self.selected_file)
                    self.pvs = dict()
                    self.file_selector.takeTopLevelItem(
                        self.file_selector.indexOfTopLevelItem(self.file_selector.currentItem()))
                except OSError as e:
                    warn = "Problem deleting file:\n" + str(e)
                    QtGui.QMessageBox.warning(self, "Warning", warn,
                                              QtGui.QMessageBox.Ok,
                                              QtGui.QMessageBox.NoButton)


class SnapshotFileFilterWidget(QtGui.QWidget):

    """
        Is a widget with 3 filter options:
            - by time (removed)
            - by comment
            - by labels
            - by name

        Emits signal: filter_changed when any of the filter changed.
    """

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
        self.keys_input = SnapshotKeywordSelectorWidget(
            self.common_settings, self)
        self.keys_input.setPlaceholderText("label_1 label_2 ...")
        self.connect(self.keys_input, SIGNAL("keywords_changed"),
                     self.update_filter)
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

        layout.addItem(name_layout)
        layout.addItem(comment_layout)
        layout.addItem(key_layout)

    def update_filter(self):
        if self.keys_input.get_keywords():
            self.file_filter["keys"] = self.keys_input.get_keywords()
        else:
            self.file_filter["keys"] = list()
        self.file_filter["comment"] = self.comment_input.text().strip('')
        self.file_filter["name"] = self.name_input.text().strip('')

        self.emit(SIGNAL("file_filter_updated"))

    def update_labels(self):
        self.keys_input.update_sugested_keywords()


# PV Compare part
class SnapshotCompareWidget(QtGui.QWidget):

    """
    Widget for live comparing pv values. All infos about PVs that needs to be
    monitored are already in the "snapshot" object controlled by worker. They
    were loaded with
    """

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)
        self.snapshot = snapshot
        self.common_settings = common_settings

        # Create main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)
        # Create filter selectors
        # - text input to filter by name
        # - drop down to filter by compare status
        # - check box to select if showing pvs with incomplete data
        filter_layout = QtGui.QHBoxLayout()
        pv_filter_layout = QtGui.QHBoxLayout()
        pv_filter_layout.setSpacing(10)
        pv_filter_label = QtGui.QLabel("Filter:", self)
        pv_filter_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        self.pv_filter_inp = QtGui.QLineEdit(self)
        self.pv_filter_inp.setPlaceholderText("Filter by PV name")
        self.pv_filter_inp.textChanged.connect(self.filter_list)
        pv_filter_layout.addWidget(pv_filter_label)
        pv_filter_layout.addWidget(self.pv_filter_inp)

        self.compare_filter_inp = QtGui.QComboBox(self)
        self.compare_filter_inp.addItems(
            ["Show all", "Not equal only", "Equal only"])
        self.compare_filter_inp.currentIndexChanged.connect(self.filter_list)
        self.compare_filter_inp.setMaximumWidth(200)
        self.completnes_filter_inp = QtGui.QCheckBox(
            "Show PVs with incomplete data.", self)
        self.completnes_filter_inp.setChecked(True)
        self.completnes_filter_inp.stateChanged.connect(self.filter_list)
        self.completnes_filter_inp.setMaximumWidth(500)
        filter_layout.addItem(pv_filter_layout)
        filter_layout.addWidget(self.compare_filter_inp)
        filter_layout.addWidget(self.completnes_filter_inp)
        filter_layout.setAlignment(Qt.AlignLeft)
        filter_layout.setSpacing(10)

        # Create list where each line presents one PV with data:
        # - pv name
        # - current pv value
        # - saved pv value
        # - status string
        self.pv_view = QtGui.QTreeWidget(self)
        self.pv_view.setRootIsDecorated(False)
        self.pv_view.setIndentation(0)
        self.pv_view.setColumnCount(4)
        self.pv_view.setHeaderLabels(
            ["PV", "Current value", "Saved value", "Status"])
        self.pv_view.setAlternatingRowColors(True)
        # Add all widgets to main layout
        layout.addItem(filter_layout)
        layout.addWidget(self.pv_view)

        # fill the compare view and start comparing
        self.populate_compare_list()
        self.start_compare()

        # Disable possibility to select item in the compare list
        self.pv_view.setSelectionMode(QtGui.QAbstractItemView.NoSelection)
        self.pv_view.setFocusPolicy(Qt.NoFocus)

    def populate_compare_list(self):
        """
        Create tree item for each PV. List of pv names was returned after
        parsing the request file. Attributes except PV name are empty at
        init. Will be updated when monitor happens, snapshot object will
        raise a callback which is then caught in worker and passed with
        signal.
        """

        # First remove all existing entries
        while self.pv_view.topLevelItemCount() > 0:
            self.pv_view.takeTopLevelItem(0)

        for pv_name in self.common_settings["pvs_to_restore"]:
            saved_val = ""
            status = ""
            curr_val = ""
            pv_line = SnapshotCompareTreeWidgetItem(pv_name, self.pv_view)
            self.pv_view.addTopLevelItem(pv_line)

        # Set column sizes
        self.pv_view.resizeColumnToContents(0)
        self.pv_view.setColumnWidth(1, 150)
        self.pv_view.setColumnWidth(2, 150)
        # Sort by name (alphabetical order)
        self.pv_view.sortItems(0, Qt.AscendingOrder)

        self.connect(self, SIGNAL("update_pv_callback"), self.update_pv)

    def filter_list(self):
        # Just pass the filter conditions to all items in the list. # Use
        # values directly from GUI elements (filter selectors).
        for i in range(self.pv_view.topLevelItemCount()):
            curr_item = self.pv_view.topLevelItem(i)
            curr_item.apply_filter(self.compare_filter_inp.currentIndex(),
                                   self.completnes_filter_inp.isChecked(),
                                   self.pv_filter_inp.text())

    def start_compare(self):
        self.snapshot.start_continuous_compare(self.update_pv_callback)

    def update_pv_callback(self, **data):
        self.emit(SIGNAL("update_pv_callback"), data)

    def update_pv(self, data):
        # If everything ok, only one line should match
        line_to_update = self.pv_view.findItems(
            data["pv_name"], Qt.MatchCaseSensitive, 0)[0]

        line_to_update.update_state(**data)


class SnapshotCompareTreeWidgetItem(QtGui.QTreeWidgetItem):

    """
    Extended to hold last info about connection status and value. Also
    implements methods to set visibility according to filter
    """

    def __init__(self, pv_name, parent=None):
        # Item with [pv_name, current_value, saved_value, status]
        QtGui.QTreeWidgetItem.__init__(
            self, parent, [pv_name, "", "", "PV not connected!"])
        self.pv_name = pv_name

        # Have data stored in native types, for easier filtering etc.
        self.connect_sts = None
        self.saved_value = None
        self.saved_sts = None
        self.value = None
        self.compare = None
        self.has_error = True

        # Variables to hold current filter. Whenever filter is applied they are
        # updated. When filter is applied from items own methods (like
        # update_state), this stored values are used.
        self.compare_filter = 0
        self.completeness_filter = True
        self.name_filter = None

    def update_state(self, pv_value, pv_saved, pv_compare, pv_cnct_sts, saved_sts, **kw):
        # Is called whenever pv value, connection status changes or new saved
        # file is selected
        self.connect_sts = pv_cnct_sts
        # indicates if list of saved PVs loaded to snapshot
        self.saved_sts = saved_sts
        self.saved_value = pv_saved
        self.value = pv_value
        self.compare = pv_compare
        self.has_error = False

        if not self.connect_sts:
            self.setText(1, "")  # no connection means no value
            self.setText(3, "PV not connected!")
            self.compare = None
            self.has_error = True
        else:
            if isinstance(self.value, numpy.ndarray):
                self.setText(1, json.dumps(self.value.tolist()))
            elif self.value is not None:
                # if string do not dump it will add "" to a string
                if isinstance(self.value, str):
                    self.setText(1, self.value)
                else:
                    # dump other values
                    self.setText(1, json.dumps(self.value))
            else:
                self.setText(1, "")

        if self.saved_value is not None:
            if isinstance(self.saved_value, numpy.ndarray):
                # Handle arrays
                self.setText(2, json.dumps(self.saved_value.tolist()))
            elif isinstance(self.saved_value, str):
                # If string do not dump it will add "" to a string
                self.setText(2, self.saved_value)
            else:
                # dump other values
                self.setText(2, json.dumps(self.saved_value))
        else:
            self.setText(2, "")
            self.setText(3, "No saved value.")
            self.compare = None
            self.has_error = True

        if self.has_error or (self.compare is None):
            self.set_color(PvViewStatus.err)
        else:
            if self.compare:
                self.setText(3, "Equal")
                self.set_color(PvViewStatus.eq)
            else:
                self.setText(3, "Not equal")
                self.set_color(PvViewStatus.neq)

        # Filter with saved filter data, to check conditions with new values.
        self.apply_filter(self.compare_filter, self.completeness_filter,
                          self.name_filter)

    def set_color(self, status):
        # Set color of QTree item depending on the status
        brush = QtGui.QBrush()

        if status == PvViewStatus.eq:
            brush.setColor(QtGui.QColor(0, 190, 0))
        elif status == PvViewStatus.neq:
            brush.setColor(QtGui.QColor(204, 0, 0))

        # TODO porting to python 2 xrange
        for i in range(0, self.columnCount()):
            # ideally would set a background color, but it look like a bug (no
            # background is applied with method setBackground()
            self.setForeground(i, brush)

    def apply_filter(self, compare_filter=PvCompareFilter.show_all,
                     completeness_filter=True, name_filter=None):
        """ Controls visibility of item, depending on filter conditions. """

        # Save filters to use the when processed by value change
        self.compare_filter = compare_filter
        self.completeness_filter = completeness_filter
        self.name_filter = name_filter

        # if name filter empty --> no filter applied (show all)
        if name_filter:
            name_match = name_filter in self.pv_name
        else:
            name_match = True

            # Do show values which has incomplete data?
        completeness_match = completeness_filter or \
            (not completeness_filter and not self.has_error)

        compare_completnes_match = ((PvCompareFilter(compare_filter) == PvCompareFilter.show_eq) and
                                    (self.compare or completeness_match)) or ((PvCompareFilter(compare_filter) == PvCompareFilter.show_neq) and
                                                                              (self.compare is False) or completeness_match) or ((PvCompareFilter(compare_filter) == PvCompareFilter.show_all) and completeness_match)

        self.setHidden(
            not(name_match and compare_completnes_match))


# Status widgets
class SnapshotStatusLog(QtGui.QWidget):

    """ Command line like logger widget """

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.sts_log = QtGui.QPlainTextEdit(self)
        self.sts_log.setReadOnly(True)

        layout = QtGui.QVBoxLayout()  # To have margin option
        layout.setMargin(10)
        layout.addWidget(self.sts_log)
        self.setLayout(layout)

    def log_line(self, text):
        # New message is added with time of the action
        time_stamp = "[" + datetime.datetime.fromtimestamp(
            time.time()).strftime('%H:%M:%S.%f') + "] "
        self.sts_log.insertPlainText(time_stamp + text + "\n")
        self.sts_log.ensureCursorVisible()


class SnapshotStatus(QtGui.QStatusBar):

    def __init__(self, common_settings, parent=None):
        QtGui.QStatusBar.__init__(self, parent)
        self.common_settings = common_settings
        self.setSizeGripEnabled(False)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.clear_status)
        self.status_txt = QtGui.QLabel()
        self.status_txt.setStyleSheet("background-color: transparent")
        self.addWidget(self.status_txt)
        self.set_status()

    def set_status(self, text="Ready", duration=0, background="rgba(0, 0, 0, 30)"):
        if self.common_settings["force"]:
            text = "[force mode] " + text
        self.status_txt.setText(text)
        style = "background-color : " + background
        self.setStyleSheet(style)

        if duration:
            self.timer.start(duration)

    def clear_status(self):
        self.set_status("Ready", 0, "rgba(0, 0, 0, 30)")


#### Helper widgets
class SnapshotConfigureDialog(QtGui.QDialog):

    """ Dialog window to select and apply file. """

    def __init__(self, parent=None, **kw):
        QtGui.QDialog.__init__(self, parent, **kw)
        self.file_path = ""
        self.macros = ""
        layout = QtGui.QVBoxLayout()
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # This Dialog consists of file selector and buttons to apply
        # or cancel the file selection
        macros_layout = QtGui.QHBoxLayout()
        macros_label = QtGui.QLabel("Macros:", self)
        macros_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        self.macros_input = QtGui.QLineEdit(self)
        self.macros_input.setPlaceholderText("MACRO1=M1,MACRO2=M2,...")
        self.file_selector = SnapshotFileSelector(
            self, label_width=macros_label.sizeHint().width())

        macros_layout.addWidget(macros_label)
        macros_layout.addWidget(self.macros_input)
        macros_layout.setSpacing(10)

        self.setMinimumSize(600, 50)

        layout.addWidget(self.file_selector)
        layout.addItem(macros_layout)

        button_box = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        button_box.accepted.connect(self.config_accepted)
        button_box.rejected.connect(self.reject)

    def config_accepted(self):
        # Save to file path to local variable and emit signal
        if not self.file_selector.file_path:
            self.file_path = ""
        else:
            self.file_path = self.file_selector.file_path
        if os.path.exists(self.file_path):
            self.macros = parse_macros(self.macros_input.text())
            self.accept()
        else:
            warn = "File does not exist!"
            QtGui.QMessageBox.warning(self, "Warning", warn,
                                      QtGui.QMessageBox.Ok,
                                      QtGui.QMessageBox.NoButton)


class SnapshotFileSelector(QtGui.QWidget):

    """ Widget to select file with dialog box. """

    def __init__(self, parent=None, label_text="File:", button_text="...", label_width=None,
                 init_path=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)
        self.file_path = init_path

        # Create main layout
        layout = QtGui.QHBoxLayout(self)
        layout.setMargin(0)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Create file dialog box. When file is selected set file path to be
        # shown in input field (can be then edited manually)
        self.req_file_dialog = QtGui.QFileDialog(self)
        # self.req_file_dialog.setOptions(QtGui.QFileDialog.DontUseNativeDialog)
        self.req_file_dialog.fileSelected.connect(self.set_file_input_text)

        # This widget has 3 parts:
        #   label
        #   input field (when value of input is changed, it is stored locally)
        #   icon button to open file dialog
        label = QtGui.QLabel(label_text, self)
        label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        if label_width is not None:
            label.setMinimumWidth(label_width)
        file_path_button = QtGui.QToolButton(self)
        file_path_button.setText(button_text)

        file_path_button.clicked.connect(self.req_file_dialog.show)
        file_path_button.setFixedSize(27, 27)
        self.file_path_input = QtGui.QLineEdit(self)
        self.file_path_input.textChanged.connect(self.change_file_path)

        layout.addWidget(label)
        layout.addWidget(self.file_path_input)
        layout.addWidget(file_path_button)

    def set_file_input_text(self):
        self.file_path_input.setText(self.req_file_dialog.selectedFiles()[0])

    def change_file_path(self):
        self.file_path = self.file_path_input.text()


class SnapshotKeywordSelectorWidget(QtGui.QComboBox):

    """
    Widget for defining keywords (labels). Existing keywords are read from
    the common_settings data structure and are suggested to the user in
    drop down menu. Keywords that are selected are returned as list.
    """

    def __init__(self, common_settings, parent=None):
        QtGui.QComboBox.__init__(self, parent)
        self.setEditable(True)
        self.common_settings = common_settings

        # Main layout
        # [selected widgets][input][drop down arrow (part of QComboBox)]
        self.layout = QtGui.QHBoxLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(5, 0, 35, 0)
        self.layout.setSpacing(2)

        self.input = SnapshotKeywordSelectorInput(self.input_handler, self)
        self.layout.addWidget(self.input)
        self.setCurrentIndex(0)
        self.connect(self, QtCore.SIGNAL("currentIndexChanged(QString)"),
                     self.add_to_selected)

        self.update_sugested_keywords()

        # data holders
        self.selected_keywords = list()
        self.keyword_widgets = dict()

        # Extra styling
        self.lineEdit().setStyleSheet("background-color: white")

    def get_keywords(self):
        # Return list of currently selected keywords
        return self.selected_keywords

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
        if event.key() in [Qt.Key_Tab, Qt.Key_Enter, Qt.Key_Return, Qt.Key_Space]:
            if self.input.text().endswith(" "):
                key_to_add = self.input.text().split(" ")[-2]
            else:
                key_to_add = self.input.text()
            self.add_to_selected(key_to_add)

        elif event.key() == Qt.Key_Backspace and len(self.selected_keywords):
            self.remove_keyword(self.selected_keywords[-1])

    def focusInEvent(self, event):
        # Focus should always be on the self.input
        self.input.setFocus()

    def add_to_selected(self, keyword):
        # When called, keyword is added to list of selected keywords and
        # new graphical representation is added left to the input field
        self.setCurrentIndex(0)
        self.input.setText("")
        keyword = keyword.strip()
        if keyword and (keyword not in self.selected_keywords):
            key_widget = SnapshotKeywordWidget(keyword, self)
            self.connect(key_widget, SIGNAL("delete"), self.remove_keyword)
            self.keyword_widgets[keyword] = key_widget
            self.selected_keywords.append(keyword)
            self.layout.insertWidget(len(self.selected_keywords)-1, key_widget)
            self.emit(SIGNAL("keywords_changed"))

    def remove_keyword(self, keyword):
        # Remove keyword from list of selected and delete graphical element
        keyword = keyword.strip()
        if keyword in self.selected_keywords:
            self.selected_keywords.remove(keyword)
            key_widget = self.keyword_widgets.get(keyword)
            self.layout.removeWidget(key_widget)
            key_widget.deleteLater()
            self.emit(SIGNAL("keywords_changed"))

    def setPlaceholderText(self, text):
        # Placeholder text is always in the input field
        self.input.setPlaceholderText(text)

    def update_sugested_keywords(self):
        # Method to be called when global list of existing labels (keywords)
        # is changed and widget must be updated.
        self.clear()
        self.common_settings["existing_labels"].sort()
        self.addItem("")
        self.addItems(self.common_settings["existing_labels"])


class SnapshotKeywordSelectorInput(QtGui.QLineEdit):

    """
    Subclass of QLineEdit, which handles keyboard events in a keyword
    selector specific way (defines keys for applying new keyword to selected,
    and removing it from the list). Events that takes actions on the main
    widget are passed to the specified function, other are handled natively.
    """

    def __init__(self, callback, parent=None):
        QtGui.QLineEdit.__init__(self, parent)
        self.callback = callback
        self.setFrame(False)
        self.setTextMargins(0, 0, 0, 0)

    def keyPressEvent(self, event):
        # Pass special key events to the main widget, handle others.
        if event.key() in [Qt.Key_Tab, Qt.Key_Enter, Qt.Key_Return, Qt.Key_Space, Qt.Key_Escape] or\
           (not self.text().strip() and event.key() == Qt.Key_Backspace):
            self.callback(event)
        else:
            QtGui.QLineEdit.keyPressEvent(self, event)

    def focusOutEvent(self, event):
        # Pass the event to the main widget which will add current string to
        # the selected keywords, and then remove the focus
        self.callback(event)
        QtGui.QLineEdit.focusOutEvent(self, event)


class SnapshotKeywordWidget(QtGui.QFrame):

    """
    Graphical representation of the selected widget. A Frame with remove
    button.
    """

    def __init__(self, text=None, parent=None):
        QtGui.QFrame.__init__(self, parent)
        self.layout = QtGui.QHBoxLayout()
        self.layout.setContentsMargins(3, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setMaximumHeight(parent.size().height()-4)
        self.setLayout(self.layout)

        self.keyword = text

        label = QtGui.QLabel(text, self)
        delete_button = QtGui.QToolButton(self)
        icon_path = os.path.dirname(os.path.realpath(__file__))
        icon_path = os.path.join(icon_path, "images/remove.png")
        delete_button.setIcon(QtGui.QIcon(icon_path))
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
        self.emit(SIGNAL("delete"), self.keyword)


#### Global functions
def parse_macros(macros_str):

    """ Converting comma separated macros string to dictionary. """

    macros = dict()
    if macros_str:
        macros_list = macros_str.split(',')
        for macro in macros_list:
            split_macro = macro.split('=')
            macros[split_macro[0]] = split_macro[1]
    return(macros)


def main():

    ''' Main creates Qt application and handles arguments '''

    args_pars = argparse.ArgumentParser()
    args_pars.add_argument('REQUEST_FILE', nargs='?')
    args_pars.add_argument('-macros', '-m',
                           help="Macros for request file e.g.: \"SYS=TEST,DEV=D1\"")
    args_pars.add_argument('-dir', '-d',
                           help="Directory for saved files")
    args_pars.add_argument('--force', '-f',
                           help="Forces save/restore in case of disconnected PVs", action='store_true')
    args = args_pars.parse_args()

    # Parse macros string if exists
    macros = parse_macros(args.macros)

    app = QtGui.QApplication(sys.argv)

    # Load an application style
    default_style_path = os.path.dirname(os.path.realpath(__file__))
    default_style_path = os.path.join(default_style_path, "qss/default.qss")
    app.setStyleSheet("file:///" + default_style_path)

    gui = SnapshotGui(args.REQUEST_FILE, macros, args.dir, args.force)

    sys.exit(app.exec_())

# Start the application here
if __name__ == '__main__':
    main()
