#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt, SIGNAL
import time
import datetime
from enum import Enum
import os
import sys
from .snapshot_ca import PvStatus, ActionStatus, Snapshot, macros_substitution, parse_macros, parse_dict_macros_to_text
import json
import numpy
import copy
import re


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

    def __init__(self, req_file_name=None, req_file_macros=None, save_dir=None, force=False, default_labels=None,
                 force_default_labels=None,init_path=None, config_path=None, parent=None):
        QtGui.QMainWindow.__init__(self, parent)

        if req_file_macros is None:
            req_file_macros = dict()

        if config_path:
            try:
                config = json.load(open(config_path))
                # force-labels must be type of bool
                if not isinstance(config.get('labels', dict()).get('force-labels', False), bool):
                    raise TypeError('"force-labels" must be boolean')
            except Exception as e:
                msg = "Loading configuration file failed! Do you want to continue with out it?\n"

                msg_window = QtGui.QMessageBox(self)
                msg_window.setWindowTitle("Warning")
                msg_window.setText(msg)
                msg_window.setDetailedText(str(e))
                msg_window.setStandardButtons(QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
                msg_window.setDefaultButton(QtGui.QMessageBox.Yes)
                reply = msg_window.exec_()

                if reply == QtGui.QMessageBox.No:
                    self.close_gui()

                config = dict()
        else:
            config = dict()

        self.resize(1500, 850)

        # common_settings is a dictionary which holds common configuration of
        # the application (such as directory with save files, request file
        # path, etc). It is propagated to other snapshot widgets if needed
        self.common_settings = dict()
        self.common_settings["save_file_prefix"] = ""
        self.common_settings["req_file_path"] = ""
        self.common_settings["req_file_macros"] = dict()
        self.common_settings["existing_labels"] = list() # labels that are already in snap files
        self.common_settings["force"] = False

        if isinstance(default_labels, str):
            self.common_settings["default_labels"] = default_labels.split(',')

        elif isinstance(default_labels, list):
            self.common_settings["default_labels"] = default_labels

        else:
            self.common_settings["default_labels"] = list() # No defaults

        # default labels also in config file? Add them
        self.common_settings["default_labels"] += config.get('labels', dict()).get('labels', list())
        self.common_settings["force_default_labels"] = config.get('labels', dict()).get('force-labels', False) or force_default_labels

        # Predefined filters
        self.common_settings["predefined_filters"] = config.get('filters', dict())

        if not req_file_name:
            self.configure_dialog = SnapshotConfigureDialog(self, init_path=init_path)
            self.configure_dialog.macros_input.setText(parse_dict_macros_to_text(req_file_macros))
            self.configure_dialog.accepted.connect(self.set_request_file)
            self.configure_dialog.rejected.connect(self.close_gui)

            self.hide()
            self.configure_dialog.exec_()

        else:
            self.common_settings["req_file_path"] = os.path.abspath(req_file_name)
            self.common_settings["req_file_macros"] = req_file_macros

        if not save_dir:
            # Default save dir
            save_dir = os.path.dirname(self.common_settings["req_file_path"])

        self.common_settings["save_dir"] = os.path.abspath(save_dir)
        self.common_settings["pvs_to_restore"] = list()

        # Before creating GUI, snapshot must be initialized.
        self.init_snapshot(self.common_settings["req_file_path"],
                           self.common_settings["req_file_macros"])

        # Create main GUI components:
        #         menu bar
        #        ______________________________
        #       | save_widget | restore_widget |
        #       --------------------------------
        #       |        compare_widget        |
        #       --------------------------------
        #       |            sts_log           |
        #        ______________________________
        #                   status_bar
        #

        # menu bar
        menu_bar = self.menuBar()

        settings_menu = QtGui.QMenu("Snapshot", menu_bar)
        open_settings_action = QtGui.QAction("Settings", settings_menu)
        open_settings_action.setMenuRole(QtGui.QAction.NoRole)
        open_settings_action.triggered.connect(self.open_settings)
        settings_menu.addAction(open_settings_action)
        menu_bar.addMenu(settings_menu)

        file_menu = QtGui.QMenu("File", menu_bar)
        open_new_req_file_action = QtGui.QAction("Open", file_menu)
        open_new_req_file_action.setMenuRole(QtGui.QAction.NoRole)
        open_new_req_file_action.triggered.connect(self.open_new_req_file)
        file_menu.addAction(open_new_req_file_action)
        menu_bar.addMenu(file_menu)

        # Status components are needed by other GUI elements
        self.status_log = SnapshotStatusLog(self)
        self.common_settings["sts_log"] = self.status_log
        status_bar = SnapshotStatus(self.common_settings, self)
        self.common_settings["sts_info"] = status_bar

        # Create status log show/hide control and add it to status bar
        self.show_log_control = QtGui.QCheckBox("Show status log")
        self.show_log_control.setStyleSheet("background-color: transparent")
        self.show_log_control.stateChanged.connect(self.status_log.setVisible)
        self.status_log.setVisible(False)
        status_bar.addPermanentWidget(self.show_log_control)

        # Creating main layout
        # Compare widget. Must be updated in case of file selection
        self.compare_widget = SnapshotCompareWidget(self.snapshot,
                                                    self.common_settings, self)

        self.compare_widget.pvs_filtered.connect(self.handle_pvs_filtered)

        self.save_widget = SnapshotSaveWidget(self.snapshot,
                                              self.common_settings, self)
        self.save_widget.saved.connect(self.handle_saved)

        self.restore_widget = SnapshotRestoreWidget(self.snapshot,
                                                    self.common_settings, self)
        # If new files were added to restore list, all elements with Labels
        # should update with new existing labels. Force update for first time
        self.restore_widget.files_updated.connect(self.handle_files_updated)
        # Trigger files update for first time to properly update label selectors
        self.restore_widget.clear_update_files()

        self.restore_widget.files_selected.connect(self.handle_selected_files)

        sr_splitter = QtGui.QSplitter(self)
        sr_splitter.addWidget(self.save_widget)
        sr_splitter.addWidget(self.restore_widget)
        element_size = (
            self.save_widget.sizeHint().width() + self.restore_widget.sizeHint().width())/2
        sr_splitter.setSizes([element_size, element_size])

        main_splitter = QtGui.QSplitter(self)
        main_splitter.addWidget(sr_splitter)
        main_splitter.addWidget(self.compare_widget)
        main_splitter.addWidget(self.status_log)
        main_splitter.setOrientation(Qt.Vertical)

        # Set default widget and add status bar
        self.setCentralWidget(main_splitter)
        self.setStatusBar(status_bar)

        # Show GUI and manage window properties
        self.show()
        self.setWindowTitle(
            os.path.basename(self.common_settings["req_file_path"]) + ' - Snapshot')

        # Status log default height should be 100px Set with splitter methods
        widgets_sizes = main_splitter.sizes()
        widgets_sizes[main_splitter.indexOf(main_splitter)] = 100
        main_splitter.setSizes(widgets_sizes)

    def open_new_req_file(self):
        # First pause old snapshot
        self.snapshot.stop_continuous_compare()

        self.configure_dialog = SnapshotConfigureDialog(self, init_path=os.path.dirname(
            self.common_settings['req_file_path']))
        self.configure_dialog.accepted.connect(self.change_req_file)
        self.configure_dialog.exec_()

    def change_req_file(self):
        self.set_request_file()

        self.init_snapshot(self.common_settings['req_file_path'], self.common_settings['req_file_macros'])

        # handle all gui components
        self.restore_widget.handle_new_snapshot_instance(self.snapshot)
        self.save_widget.handle_new_snapshot_instance(self.snapshot)
        self.compare_widget.handle_new_snapshot_instance(self.snapshot)

        self.setWindowTitle(
            os.path.basename(self.common_settings["req_file_path"]) + ' - Snapshot')

    def handle_saved(self):
        # When save is done, save widget is updated by itself
        # Update restore widget (new file in directory)
        self.restore_widget.update_files()

    def set_request_file(self):
        self.common_settings["req_file_path"] = self.configure_dialog.file_path
        self.common_settings["req_file_macros"] = self.configure_dialog.macros

    def init_snapshot(self, req_file_path, req_macros = None):
        req_macros = req_macros or {}

        self.snapshot = Snapshot(req_file_path, req_macros)
        self.common_settings["pvs_to_restore"] = self.snapshot.get_pvs_names()

    def handle_files_updated(self, updated_files):
        # When new save file is added, or old one has changed, this method
        # should handle things like updating label widgets and compare widget.
        self.save_widget.update_labels()
        self.compare_widget.update_shown_files(updated_files)

    def handle_selected_files(self, selected_files):
        # selected_files is a dict() with file names as keywords and
        # dict() of pv data as value
        self.compare_widget.new_selected_files(selected_files)

    def open_settings(self):
        settings_window = SnapshotSettingsDialog(self.common_settings, self)  # Destroyed when closed
        settings_window.new_config.connect(self.handle_new_config)
        settings_window.resize(800,200)
        settings_window.show()

    def handle_new_config(self, config):
        for config_name, config_value in config.items():
            if config_name == "macros":
                self.snapshot.change_macros(config_value)
                self.common_settings["pvs_to_restore"] = self.snapshot.get_pvs_names()
                self.common_settings["req_file_macros"] = config_value
                self.compare_widget.populate_compare_list()
                self.restore_widget.handle_selected_files(self.restore_widget.file_selector.selected_files)
            elif config_name == "force":
                self.common_settings["force"] = config_value
                self.common_settings["sts_info"].set_status()
            elif config_name == "save_dir":
                self.common_settings["save_dir"] = config_value
                self.restore_widget.clear_update_files()

    def handle_pvs_filtered(self, pvs=None):
        if pvs is None:
            pvs = list()

        self.restore_widget.filtered_pvs = pvs

    def close_gui(self):
        sys.exit()


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

    saved = QtCore.pyqtSignal()

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.common_settings = common_settings
        self.snapshot = snapshot

        # Default saved file name: If req file name is PREFIX.req, then saved
        # file name is: PREFIX_YYMMDD_hhmmss (holds time info)
        # Get the prefix ... use update_name() later
        self.save_file_sufix = ".snap"

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

        # Create collapsible group with advanced options, 
        # then update output file name and finish adding widgets to layout
        self.advanced = SnapshotAdvancedSaveSettings("Advanced", self.common_settings, self)

        self.update_name()

        extension_rb_layout.addWidget(file_name_label)
        extension_rb_layout.addWidget(self.file_name_rb)
        extension_rb_layout.addStretch()

        # Make Save button
        save_layout = QtGui.QHBoxLayout()
        save_layout.setSpacing(10)
        self.save_button = QtGui.QPushButton("Save", self)
        self.save_button.clicked.connect(self.start_save)

        save_layout.addWidget(self.save_button)

        # Status widgets
        self.sts_log = self.common_settings["sts_log"]
        self.sts_info = self.common_settings["sts_info"]

        # Add to main layout
        layout.addLayout(extension_layout)
        layout.addLayout(extension_rb_layout)
        layout.addWidget(self.advanced)
        layout.addLayout(save_layout)
        layout.addStretch()

    def handle_new_snapshot_instance(self, snapshot):
        self.snapshot = snapshot
        self.extension_input.setText('')
        self.update_name()
        self.update_labels()
        self.advanced.labels_input.clear_keywords()
        self.advanced.comment_input.setText('')

    def start_save(self):
        # Check if save can be done (all pvs connected or in force mode)
        force = self.common_settings["force"]
        not_connected_pvs = self.snapshot.get_not_connected_pvs_names()
        do_save = True
        if not force and not_connected_pvs:
            # If file exists, user must decide whether to overwrite it or not
            msg = "Some PVs are not connected (see details). Do you want to save anyway?\n"

            msg_window = QtGui.QMessageBox(self)
            msg_window.setWindowTitle("Warning")
            msg_window.setText(msg)
            msg_window.setDetailedText("\n".join(not_connected_pvs))
            msg_window.setStandardButtons(QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
            msg_window.setDefaultButton(QtGui.QMessageBox.Yes)
            reply = msg_window.exec_()

            if reply == QtGui.QMessageBox.No:
                force = False
                do_save = False
            else:
                force = True

        # Update file name and chek if exists. Then disable button for the time
        # of saving. Will be unlocked when save is finished.

        #  Update name with latest timestamp and file prefix.
        self.update_name()

        if do_save and self.check_file_existance():
            self.save_button.setEnabled(False)
            self.sts_log.log_line("Save started.")
            self.sts_info.set_status("Saving ...", 0, "orange")

            # Use advanced settings only if selected
            if self.advanced.isChecked():
                labels = self.advanced.labels_input.get_keywords()
                comment = self.advanced.comment_input.text()
            else:
                labels = list()
                comment = ""

            # Start saving process and notify when finished
            status, pvs_status = self.snapshot.save_pvs(os.path.basename(self.common_settings["req_file_path"]),
                                                        self.file_path,
                                                        force=force,
                                                        labels=labels,
                                                        comment=comment,
                                                        symlink_path= os.path.join(
                                                                        self.common_settings["save_dir"],
                                                                        self.common_settings["save_file_prefix"] +
                                                                        'latest' + self.save_file_sufix))
            if status == ActionStatus.no_cnct:
                self.sts_log.log_line(
                    "ERROR: Save rejected. One or more PVs not connected.")
                self.sts_info.set_status("Cannot save", 3000, "#F06464")
                self.save_button.setEnabled(True)
            else:
                # If not no_cnct, then .ok
                self.save_done(pvs_status, force)
        else:
            # User rejected saving with unconnected PVs or into existing file.
            # Not an error state.
            self.sts_info.clear_status()

    def save_done(self, status, forced):
        # Enable save button, and update status widgets
        error = False
        for pv_name, sts in status.items():
            if sts == PvStatus.access_err:
                error = True and not forced
                self.sts_log.log_line("WARNING: " + pv_name +
                                      ": Not saved (no connection or no read access)")

                status_txt = "Save error"
                status_background = "#F06464"

        if not error:
            self.sts_log.log_line("Save successful.")
            status_txt = "Save done"
            status_background = "#64C864"

        self.save_button.setEnabled(True)
        self.sts_info.set_status(status_txt, 3000, status_background)

        self.saved.emit()

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

        # Use manually entered prefix only if advanced options are selected
        if self.advanced.file_prefix_input.text() and self.advanced.isChecked():
            self.common_settings["save_file_prefix"] = self.advanced.file_prefix_input.text()
        else:
            self.common_settings["save_file_prefix"] = os.path.split(self.common_settings
                ["req_file_path"])[1].split(".")[0] + "_"

        self.file_path = os.path.join(self.common_settings["save_dir"],
                                      self.common_settings["save_file_prefix"] + 
                                      self.name_extension + self.save_file_sufix)
        self.file_name_rb.setText(self.common_settings["save_file_prefix"] +
                                    name_extension_rb)

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
        self.advanced.update_labels()


class SnapshotAdvancedSaveSettings(QtGui.QGroupBox):
    def __init__(self, text, common_settings, parent=None):
        self.parent = parent

        QtGui.QGroupBox.__init__(self, text, parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 15)")
        min_label_width = 120
        # frame is a container with all widgets, tat should be collapsed
        self.frame = QtGui.QFrame(self)
        self.frame.setContentsMargins(0,20,0,0)
        self.frame.setStyleSheet("background-color: None")
        self.setCheckable(True)
        self.frame.setVisible(False)
        self.setChecked(False)
        self.toggled.connect(self.toggle)

        layout = QtGui.QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.frame)
        self.setLayout(layout)

        self.frame_layout = QtGui.QVBoxLayout()
        self.frame_layout.setMargin(0)
        self.frame.setLayout(self.frame_layout)

        # Make a field to enable user adding a comment
        comment_layout = QtGui.QHBoxLayout()
        comment_layout.setSpacing(10)
        comment_label = QtGui.QLabel("Comment:", self.frame)
        comment_label.setStyleSheet("background-color: None")
        comment_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        comment_label.setMinimumWidth(min_label_width)
        self.comment_input = QtGui.QLineEdit(self.frame)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Make field for labels
        labels_layout = QtGui.QHBoxLayout()
        labels_layout.setSpacing(10)
        labels_label = QtGui.QLabel("Labels:", self.frame)
        labels_label.setStyleSheet("background-color: None")
        labels_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        labels_label.setMinimumWidth(min_label_width)
        # If default labels are defined, then force default labels
        self.labels_input = SnapshotKeywordSelectorWidget(common_settings,
                                                          defaults_only=common_settings['force_default_labels'],
                                                          parent=self)
        labels_layout.addWidget(labels_label)
        labels_layout.addWidget(self.labels_input)

        # Make field for specifying save file prefix
        file_prefix_layout = QtGui.QHBoxLayout()
        file_prefix_layout.setSpacing(10)
        file_prefix_label = QtGui.QLabel("File name prefix:", self.frame)
        file_prefix_label.setStyleSheet("background-color: None")
        file_prefix_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        file_prefix_label.setMinimumWidth(min_label_width)
        self.file_prefix_input = QtGui.QLineEdit(self.frame)
        file_prefix_layout.addWidget(file_prefix_label)
        file_prefix_layout.addWidget(self.file_prefix_input)
        self.file_prefix_input.textChanged.connect(
            self.parent.update_name)

        #self.frame_layout.addStretch()
        self.frame_layout.addLayout(comment_layout)
        self.frame_layout.addLayout(labels_layout)
        self.frame_layout.addLayout(file_prefix_layout)

    def update_labels(self):
        self.labels_input.update_suggested_keywords()

    def toggle(self):
        self.frame.setVisible(self.isChecked())
        self.parent.update_name()


# noinspection PyArgumentList
class SnapshotRestoreWidget(QtGui.QWidget):

    """
    Restore widget is a widget that enables user to restore saved state of PVs
    listed in request file from one of the saved files.
    Save widget consists of:
     - file selector (tree of all files)
     - restore button
     - searcher/filter

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

        self.restore_button = QtGui.QPushButton("Restore Filtered", self)
        self.restore_button.clicked.connect(self.start_restore_filtered)
        self.restore_button.setToolTip("Restores only currently filtered PVs from the selected .snap file.")

        self.restore_all_button = QtGui.QPushButton("Restore All", self)
        #self._filtered = None
        self.restore_all_button.clicked.connect(self.start_restore_all)
        self.restore_all_button.setToolTip("Restores all PVs from the selected .snap file.")

        # Buttons layout
        btn_layout = QtGui.QHBoxLayout()
        btn_layout.addWidget(self.restore_all_button)
        btn_layout.addWidget(self.restore_button)


        # Status widgets
        self.sts_log = self.common_settings["sts_log"]
        self.sts_info = self.common_settings["sts_info"]

        # Create file list for first time and update the GUI with new data
        # (label widgets)
        self.clear_update_files()

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
            self.do_restore()  #This way functions below skip unnecessary checks
        elif filtered_n:
            self.do_restore(filtered_only=True)
        # Do not start a restore if nothing to restore

    def do_restore(self, filtered_only=False):
        # Check if restore can be done (values loaded to snapshot).
        if filtered_only:
            filtered = self.filtered_pvs
        else:
            filtered = None

        if self.snapshot.restore_values_loaded:
            # Check if all pvs connected or in force mode)
            force = self.common_settings["force"]
            not_connected_pvs = self.snapshot.get_not_connected_pvs_names(filtered)
            do_restore = True
            if not force and not_connected_pvs:
                msg = "Some PVs are not connected (see details). Do you want to restore anyway?\n"

                msg_window = QtGui.QMessageBox(self)
                msg_window.setWindowTitle("Warning")
                msg_window.setText(msg)
                msg_window.setDetailedText("\n".join(not_connected_pvs))
                msg_window.setStandardButtons(QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
                msg_window.setDefaultButton(QtGui.QMessageBox.Yes)
                reply = msg_window.exec_()

                if reply == QtGui.QMessageBox.No:
                    force = False
                    do_restore = False
                else:
                    force = True

            if do_restore:
                if self.snapshot.restore_values_loaded:
                    # First disable restore button (will be enabled when finished)
                    # Then Use one of the preloaded saved files to restore
                    self.restore_all_button.setEnabled(False)
                    # Force updating the GUI and disabling the button before future actions
                    QtCore.QCoreApplication.processEvents()
                    self.sts_log.log_line("Restore started.")
                    self.sts_info.set_status("Restoring ...", 0, "orange")
                    # Force updating the GUI with new status
                    QtCore.QCoreApplication.processEvents()

                    status = self.snapshot.restore_pvs(callback=self.restore_done_callback,
                                                       force=force, selected=filtered)
                    if status == ActionStatus.no_data:
                        # Because of checking "restore_values_loaded" before
                        # starting a restore, this case should not happen.
                        self.sts_log.log_line("ERROR: Nothing to restore.")
                        self.sts_info.set_status("Restore rejected", 3000, "#F06464")
                        self.restore_all_button.setEnabled(True)
                    elif status == ActionStatus.no_cnct:
                        self.sts_log.log_line(
                            "ERROR: Restore rejected. One or more PVs not connected.")
                        self.sts_info.set_status("Restore rejected", 3000, "#F06464")
                        self.restore_all_button.setEnabled(True)
                    elif status == ActionStatus.busy:
                        self.sts_log.log_line(
                            "ERROR: Restore rejected. Previous restore not finished.")
        else:
            # Don't start a restore if file not selected
            warn = "Cannot start a restore. File with saved values is not selected."
            QtGui.QMessageBox.warning(self, "Warning", warn,
                                      QtGui.QMessageBox.Ok,
                                      QtGui.QMessageBox.NoButton)

    def restore_done_callback(self, status, forced, **kw):
        # Raise callback to handle GUI specific in GUI thread
        self.restored_callback.emit(status, forced)

    def restore_done(self, status, forced):
        # When snapshot finishes restore, GUI must be updated with
        # status of the restore action.
        error = False
        for key in status:
            pv_status = status[key]
            if pv_status == PvStatus.access_err:
                error = True and not forced
                self.sts_log.log_line("WARNING: " + key +
                                      ": Not restored (no connection or no write access).")
                self.sts_info.set_status("Restore error", 3000, "#F06464")
        if not error:
            self.sts_log.log_line("Restore successful.")
            self.sts_info.set_status("Restore done", 3000, "#64C864")

        # Enable button when restore is finished
        self.restore_all_button.setEnabled(True)

    def handle_selected_files(self, selected_files):
        # Prepare for restore if one specific file is selected, or clear
        # restore data if none specific file is selected.
        selected_data = dict()
        for file_name in selected_files:
            file_data = self.file_selector.file_list.get(file_name, None)
            if file_data:
                selected_data[file_name] = file_data

        # First update other GUI components (compare widget) and then pass pvs to compare to the snapshot core
        self.files_selected.emit(selected_data)

        if len(selected_files) == 1 and file_data:
            self.snapshot.prepare_pvs_to_restore_from_list(file_data.get("pvs_list", None),
                                                           file_data["meta_data"].get("macros", None))
        else:
            self.snapshot.clear_pvs_to_restore()

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
        self.file_selector.itemSelectionChanged.connect(self.select_files)
        self.file_selector.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_selector.customContextMenuRequested.connect(self.open_menu)

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
        self.menu.addAction("Update file meta-data", self.update_file_metadata)
        

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
                if item[1]: # list of errors

                    err_details += '- - - ' + item[0] + \
                                   ' - - -\n * ' # file name
                    err_details += '\n * '.join(item[1])
                    err_details += '\n\n'

            err_details = err_details[:-2]  # Remove last two new lines

        if err_details:
            msg = str(len(err_to_report)) + " of the snapshot saved files (.snap) were loaded with errors " \
                                            "(see details)."
            msg_window = QtGui.QMessageBox(self)
            msg_window.setWindowTitle("Warning")
            msg_window.setText(msg)
            msg_window.setDetailedText(err_details)
            msg_window.setStandardButtons(QtGui.QMessageBox.Ok)
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

        return(parsed_save_files, err_to_report)

    def update_file_list_selector(self, modif_file_list):

        existing_labels = self.common_settings["existing_labels"]

        for modified_file, modified_data in modif_file_list.items():
            meta_data = modified_data["meta_data"]
            labels = meta_data.get("labels", list())
            comment = meta_data.get("comment", "")
            time = datetime.datetime.fromtimestamp(modified_data.get("modif_time", 0)).strftime('%d.%m.%Y %H:%M:%S')

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
        self.file_selector.resizeColumnToContents(1)
        self.file_selector.setColumnWidth(0, 60)
        self.file_selector.setColumnWidth(2, 350)

        # Sort by file name (alphabetical order)
        self.file_selector.sortItems(1, Qt.AscendingOrder)

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
                    not(name_status and keys_status and comment_status))

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
                                selected_file, Qt.MatchCaseSensitive, 0)[0]))

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
                settings_window.resize(800,200)
                # if OK was pressed, update actual file and reflect changes in the list
                if settings_window.exec_():
                    self.snapshot.replace_metadata(self.selected_files[0], self.file_list.get(self.selected_files[0])["meta_data"])
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


# PV Compare part
class SnapshotCompareWidget(QtGui.QWidget):

    """
    Widget for live comparing pv values. All infos about PVs that needs to be
    monitored are already in the "snapshot" object controlled by worker. They
    were loaded with
    """
    pvs_filtered = QtCore.pyqtSignal(list)
    updated_pv_callback = QtCore.pyqtSignal(dict)

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)
        self.snapshot = snapshot
        self.common_settings = common_settings
        self.file_compare_struct = dict()

        # Create main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)
        # Create filter selectors
        # - text input to filter by name
        # - drop down to filter by compare status
        # - check box to select if showing pvs with incomplete data
        self.filter_mode = "no-file"
        filter_layout = QtGui.QHBoxLayout()
        pv_filter_layout = QtGui.QHBoxLayout()
        pv_filter_layout.setSpacing(10)
        pv_filter_label = QtGui.QLabel("Filter:", self)
        pv_filter_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)

        predefined_filters = self.common_settings["predefined_filters"]
        if predefined_filters:
            self.pv_filter_sel = QtGui.QComboBox(self)
            self.pv_filter_sel.setEditable(True)
            self.pv_filter_sel.setIconSize(QtCore.QSize(35,15))
            sel_layout = QtGui.QHBoxLayout()
            sel_layout.addStretch()
            self.pv_filter_sel.setLayout(sel_layout)
            self.pv_filter_inp = self.pv_filter_sel.lineEdit()
            self.pv_filter_inp.setPlaceholderText("Filter by PV name")

            # Add filters
            self.pv_filter_sel.addItem(None)
            for rgx in predefined_filters.get('rgx-filters', list()):
                self.pv_filter_sel.addItem(QtGui.QIcon(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                                    "images/rgx.png")),rgx)
            self.pv_filter_sel.addItems(predefined_filters.get('filters', list()))


            self.pv_filter_sel.currentIndexChanged.connect(self.predefined_selected)
        else:
            self.pv_filter_inp = QtGui.QLineEdit(self)
            self.pv_filter_inp.setPlaceholderText("Filter by PV name")
            self.pv_filter_sel = self.pv_filter_inp


        self.pv_filter_inp.textChanged.connect(self.filter_list)
        self._inp_palette_ok = self.pv_filter_inp.palette()
        self._inp_palette_err = QtGui.QPalette()
        self._inp_palette_err.setColor(QtGui.QPalette.Base, QtGui.QColor("#F39292"))


        pv_filter_layout.addWidget(pv_filter_label)
        pv_filter_layout.addWidget(self.pv_filter_sel)

        self.regex = QtGui.QCheckBox("Regex", self)
        self.regex.stateChanged.connect(self.regex_change)

        self.compare_filter_inp = QtGui.QComboBox(self)
        self.compare_filter_inp.addItems(
            ["Show all", "Different only", "Equal only"])
        self.compare_filter_inp.currentIndexChanged.connect(self.filter_list)
        self.compare_filter_inp.setMaximumWidth(200)
        self.completnes_filter_inp = QtGui.QCheckBox(
            "Show disconnected PVs.", self)
        self.completnes_filter_inp.setChecked(True)
        self.completnes_filter_inp.stateChanged.connect(self.filter_list)
        self.completnes_filter_inp.setMaximumWidth(500)

        filter_layout.addLayout(pv_filter_layout)
        filter_layout.addWidget(self.regex)

        sep = QtGui.QFrame(self)
        sep.setFrameShape(QtGui.QFrame.VLine)
        filter_layout.addWidget(sep)

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
        self.pv_view.setSortingEnabled(True)
        self.pv_view.setRootIsDecorated(False)
        self.pv_view.setIndentation(0)
        self.pv_view.setColumnCount(2)
        self.column_names = ["PV", "Current value"]
        self.pv_view.setHeaderLabels(self.column_names)
        # Add all widgets to main layout
        layout.addLayout(filter_layout)
        layout.addWidget(self.pv_view)

        # fill the compare view and start comparing
        self.populate_compare_list()

        # Select max 1 item from the list. Do not use focus on this widget.
        self.pv_view.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.pv_view.setFocusPolicy(Qt.NoFocus)

        # Context menu
        self.pv_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pv_view.customContextMenuRequested.connect(self.open_menu)
        self.menu = QtGui.QMenu(self)
        self.menu.addAction("Copy PV name",self.copy_pv_name)

    def open_menu(self, point):
        if len(self.pv_view.selectedItems()) > 0:
            self.menu.show()
            pos = self.pv_view.mapToGlobal(point)
            pos += QtCore.QPoint(0, self.menu.sizeHint().height())
            self.menu.move(pos)

    def copy_pv_name(self):
        cb = QtGui.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard )
        cb.setText(self.pv_view.selectedItems()[0].text(0), mode=cb.Clipboard)

    def handle_new_snapshot_instance(self, snapshot):
        #self.new_selected_files(dict()) # act as there is no selected file
        self.snapshot = snapshot
        self.populate_compare_list()


    def populate_compare_list(self):
        """
        Create tree item for each PV. List of pv names was returned after
        parsing the request file. Attributes except PV name are empty at
        init. Will be updated when monitor happens or files are selected.
        """
        self.pv_view.setSortingEnabled(False)

        self.snapshot.stop_continuous_compare()
        # First remove all existing entries
        while self.pv_view.topLevelItemCount() > 0:
            self.pv_view.takeTopLevelItem(0)

        for pv_name in self.common_settings["pvs_to_restore"]:
            pv_line = SnapshotCompareTreeWidgetItem(pv_name, self.pv_view)
            self.pv_view.addTopLevelItem(pv_line)

        # Names of all PVs should be visible
        self.pv_view.resizeColumnToContents(0)
        # Sort by name (alphabetical order)
        self.pv_view.sortItems(0, Qt.AscendingOrder)

        self.updated_pv_callback.connect(self.update_pv)
        self.snapshot.start_continuous_compare(self.update_pv_callback)
        self.pv_view.setSortingEnabled(True)

    def predefined_selected(self, idx):
        txt = self.pv_filter_inp.text()
        if idx == 0:
            # First empty option
            pass
        if not self.pv_filter_sel.itemIcon(idx).isNull():
            # Set back to first index, to get rid of the icon. Set to regex and pass text of filter to the input
            self.pv_filter_sel.setCurrentIndex(0)
            self.regex.setChecked(True)
            self.pv_filter_inp.setText(txt)
        else:
            #Imitate same behaviour
            self.pv_filter_sel.setCurrentIndex(0)
            self.regex.setChecked(False)
            self.pv_filter_inp.setText(txt)

    def regex_change(self, state):
        text = self.pv_filter_inp.text()
        if state:
            if not text:
                self.pv_filter_inp.setText('.*')
            else:
                self.filter_list()
        elif text == '.*':
            self.pv_filter_inp.setText('')
        else:
            self.filter_list()

    def filter_list(self):
        # Just pass the filter conditions to all items in the list. # Use
        # values directly from GUI elements (filter selectors).

        # If regex, check for syntax errors and prepare compiler object
        if self.regex.isChecked():
            try:
                input = re.compile(self.pv_filter_inp.text())
                self.pv_filter_inp.setPalette(self._inp_palette_ok)
            except:
                # Syntax error (happens a lot during typing an expression). In such cases make compiler which will
                # not match any pv name and color input "redish"
                input = re.compile("")
                self.pv_filter_inp.setPalette(self._inp_palette_err)
        else:
            # Normal search
            input = self.pv_filter_inp.text()


        filtered = list()
        for i in range(self.pv_view.topLevelItemCount()):
            curr_item = self.pv_view.topLevelItem(i)
            visible = curr_item.apply_filter(self.compare_filter_inp.currentIndex(),
                                             self.completnes_filter_inp.isChecked(),
                                             input,
                                             self.compare_filter_inp.currentIndex(),
                                             self.filter_mode)
            if visible:
                filtered.append(curr_item.pv_name)

        # Notify that pvs vere filtered
        self.pvs_filtered.emit(filtered)

    def update_pv_callback(self, **data):
        self.updated_pv_callback.emit(data)

    def update_pv(self, data):
        # If everything ok, only one line should match
        matching_lines = self.pv_view.findItems(
            data["pv_name"], Qt.MatchCaseSensitive, 0)
        if matching_lines:
            line_to_update = matching_lines[0]
            line_to_update.update_state(**data)

    def new_selected_files(self, selected_files):
        # Set compare mode
        if len(selected_files.keys()) == 1:
            self.filter_mode = "pv-compare"
        elif len(selected_files.keys()) > 1:
            self.filter_mode = "file-compare"
        else:
            self.filter_mode = "no-file"

        # Create column for each of the selected files.
        self.pv_view.setColumnCount(3 + len(selected_files.keys()))
        self.pv_view.setColumnWidth(1, 200)  # Width of current value
        self.pv_view.setColumnWidth(2, 30)
        self.column_names = ["PV", "Current value", ""]

        self.file_compare_struct = dict()
        i = 3
        for file_name, file_data in selected_files.items():
            self.pv_view.setColumnWidth(i, 200)

            if self.snapshot.macros:
                macros = self.snapshot.macros
            else:
                macros = file_data["meta_data"].get("macros", dict())

            pvs_list_full_names = dict()  # PVS data mapped to real pvs names (no macros)
            for pv_name_raw, pv_data in file_data["pvs_list"].items():
                pvs_list_full_names[macros_substitution(pv_name_raw, macros)] = pv_data # snapshot_ca.py function

            # To get a proper update, need to go through "pvs_to_restore". Otherwise values of PVs listed in request
            # but not in the saved file are not cleared (value from previous file is seen on the screen)
            for pv_name in self.common_settings["pvs_to_restore"]:
                    pv_data = pvs_list_full_names.get(pv_name, {"pv_value": None})
                    matching_lines = self.pv_view.findItems(
                        pv_name, Qt.MatchCaseSensitive, 0)
                    if matching_lines:
                        line_to_update = matching_lines[0]
                        pv_value = pv_data.get("pv_value", None)
                        line_to_update.add_saved_value(i, pv_value)

                        # Pass compare info to the tree widget item, which uses it
                        # for visibility calculation
                        line_to_update.files_equal = self.update_compare_struct(pv_name, pv_value)

            self.column_names.append(file_name)
            i += 1

        self.pv_view.setHeaderLabels(self.column_names)
        self.filter_list()

    def update_shown_files(self, updated_files):
        files_to_update = dict()
        # Check if one of updated files is currently selected, and update
        # the values if it is.
        i = 3
        for file_name in self.column_names[3:]:
            was_updated_file = updated_files.get(file_name, None)
            if was_updated_file:
                saved_pvs = was_updated_file["pvs_list"]
                for pv_name in self.common_settings["pvs_to_restore"]:
                    pv_data = saved_pvs.get(pv_name, {"pv_value": None})
                    matching_lines = self.pv_view.findItems(
                        pv_name, Qt.MatchCaseSensitive, 0)
                    if matching_lines:
                        pv_value = pv_data.get("pv_value", None)
                        line_to_update = matching_lines[0]
                        line_to_update.add_saved_value(i, pv_value)
                        line_to_update.files_equal = self.update_compare_struct(pv_name, pv_value)
            i += 1
        self.filter_list()

    def update_compare_struct(self, pv_name, pv_value):
        # Compare to previous files (to have a filter selected files)
        pv_compare_struct = self.file_compare_struct.get(pv_name, None)
        compare = True
        if not pv_compare_struct:
            # create with first file
            pv_compare_struct = dict()
            pv_compare_struct["compare_status"] = compare
            pv_compare_struct["compare_value"] = pv_value
            # Get data type with first access
            if pv_value is not None:
                if isinstance(pv_value, numpy.ndarray):
                    # Handle arrays
                    pv_compare_struct["pv_type"] = "array"
                else:
                    pv_compare_struct["pv_type"] = "common"
            else:
                pv_compare_struct["pv_type"] = "none"

            self.file_compare_struct[pv_name] = pv_compare_struct

        elif pv_compare_struct["compare_status"]:
            # If all previous equal check new one
            pv_type = pv_compare_struct["pv_type"]
            compare_value = pv_compare_struct["compare_value"]
            if pv_type == "none" and pv_value is not None:
                # Saved in this file, but not in previous. Different files.
                compare = False
            elif pv_type == "array":
                compare = numpy.array_equal(pv_value, compare_value)
            else:
                compare = (pv_value == compare_value)
            pv_compare_struct["compare_status"] = compare

        return pv_compare_struct["compare_status"]


class SnapshotCompareTreeWidgetItem(QtGui.QTreeWidgetItem):

    """
    Extended to hold last info about connection status and value. Also
    implements methods to set visibility according to filter
    """

    def __init__(self, pv_name, parent=None):
        # Item with [pv_name, current_value, saved_values...]
        QtGui.QTreeWidgetItem.__init__(
            self, parent, [pv_name, "PV disconnected!"])
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.warn_icon = QtGui.QIcon(os.path.join(dir_path, "images/warn.png"))
        self.neq_icon = QtGui.QIcon(os.path.join(dir_path, "images/neq.png"))
        self.setIcon(1, self.warn_icon)
        self.pv_name = pv_name

        # Have data stored in native types, for easier filtering etc.
        self.connect_sts = None
        self.value = None
        self.compare = None
        self.has_error = True

        # Variables to hold current filter. Whenever filter is applied they are
        # updated. When filter is applied from items own methods (like
        # update_state), this stored values are used.
        self.compare_filter = 0
        self.connected_filter = True
        self.name_filter = ""
        self.mode = "no-file"
        self.files_equal = False

    def update_state(self, pv_value, pv_compare, pv_cnct_sts, **kw):
        # Is called whenever pv value, connection status changes or new saved
        # file is selected
        self.connect_sts = pv_cnct_sts
        self.value = pv_value
        self.compare = pv_compare

        if self.mode == "pv-compare":
            if self.compare:
                self.handle_status(PvViewStatus.eq)
            elif self.compare is False:
                self.handle_status(PvViewStatus.neq)
        else:
            self.handle_status(None)

        if not self.connect_sts:
            self.setText(1, "PV disconnected!")
            self.setIcon(1, self.warn_icon)
            self.compare = None
        else:
            self.setIcon(1, QtGui.QIcon())
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

        # Filter with saved filter data, to check conditions with new values.
        self.apply_filter(self.compare_filter, self.connected_filter, self.name_filter, self.compare_filter,
                          self.mode)

    def add_saved_value(self, index, value):
        if value is not None:
            if isinstance(value, numpy.ndarray):
                # Handle arrays
                self.setText(index, json.dumps(value.tolist()))
            elif isinstance(value, str):
                # If string do not dump it will add "" to a string
                self.setText(index, value)
            else:
                # dump other values
                self.setText(index, json.dumps(value))
        else:
            self.setText(index, "")

    def handle_status(self, status):
        # Set color of QTree item depending on the status
        if status == PvViewStatus.eq:
            self.setIcon(2, QtGui.QIcon())
        elif status == PvViewStatus.neq:
            self.setIcon(2, self.neq_icon)
        else:
            self.setIcon(2, QtGui.QIcon())

    def apply_filter(self, compare_filter=PvCompareFilter.show_all, connected_filter=True, name_filter=None,
                     file_filter=PvCompareFilter.show_neq, filter_mode="no-file"):

        """ Controls visibility of item, depending on filter conditions. """
        # Save filters to use the when processed by value change
        self.compare_filter = compare_filter
        self.connected_filter = connected_filter
        self.name_filter = name_filter
        self.file_filter = file_filter
        self.mode = filter_mode

        # if name filter empty --> no filter applied (show all)
        if isinstance(name_filter, str):
            name_match = name_filter in self.pv_name
        else:
            # regex parser
            name_match = (name_filter.fullmatch(self.pv_name) is not None)

        connected_match = self.connected_filter or self.connect_sts

        if self.mode == "no-file":
            # Only name and connection
            self.setHidden(not name_match or not connected_match)
            self.handle_status(None)

        elif self.mode == "file-compare":
            compare_file_filter = PvCompareFilter(self.file_filter)
            file_match = (((compare_file_filter == PvCompareFilter.show_eq) and self.files_equal) or
                             ((compare_file_filter == PvCompareFilter.show_neq) and self.files_equal is False) or
                             (compare_file_filter == PvCompareFilter.show_all))
            self.setHidden(not(name_match and ((self.connect_sts and file_match) or (
                           not self.connect_sts and connected_match))))
            self.handle_status(None)

        elif self.mode == "pv-compare":
            compare_filter = PvCompareFilter(compare_filter)
            compare_match = (((compare_filter == PvCompareFilter.show_eq) and self.compare) or
                             ((compare_filter == PvCompareFilter.show_neq) and self.compare is False) or
                             (compare_filter == PvCompareFilter.show_all))
            self.setHidden(not(name_match and ((self.connect_sts and compare_match) or (
                           not self.connect_sts and connected_match))))

        return(not self.isHidden())


# Status widgets
class SnapshotStatusLog(QtGui.QWidget):

    """ Command line like logger widget """

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.sts_log = QtGui.QPlainTextEdit(self)
        self.sts_log.setReadOnly(True)

        layout = QtGui.QVBoxLayout()
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


# Helper widgets
class SnapshotConfigureDialog(QtGui.QDialog):

    """ Dialog window to select and apply file. """

    def __init__(self, parent=None, init_path=None, **kw):
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
            self, label_width=macros_label.sizeHint().width(), init_path=init_path)

        macros_layout.addWidget(macros_label)
        macros_layout.addWidget(self.macros_input)
        macros_layout.setSpacing(10)

        self.setMinimumSize(600, 50)

        layout.addWidget(self.file_selector)
        layout.addLayout(macros_layout)

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

    def focusInEvent(self, event):
        self.file_selector.setFocus()


class SnapshotSettingsDialog(QtGui.QWidget):

    new_config = QtCore.pyqtSignal(dict)

    def __init__(self, common_settings, parent=None):
        self.common_settings = common_settings
        QtGui.QWidget.__init__(self, parent)
        group_box = QtGui.QGroupBox("General Snapshot Settings", self)
        group_box.setFlat(False)
        layout = QtGui.QVBoxLayout()
        form_layout = QtGui.QFormLayout()
        form_layout.setFieldGrowthPolicy(QtGui.QFormLayout.AllNonFixedFieldsGrow)
        form_layout.setMargin(10)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # get current values
        self.curr_macros = self.common_settings["req_file_macros"]
        self.curr_save_dir = self.common_settings["save_dir"]
        self.curr_forced = self.common_settings["force"]
        # Macros
        self.macro_input = QtGui.QLineEdit(self)
        self.macro_input.setText(parse_dict_macros_to_text(self.curr_macros))
        self.macro_input.textChanged.connect(self.monitor_changes)
        form_layout.addRow("Macros:", self.macro_input)

        # Snapshot directory
        self.save_dir_input = SnapshotFileSelector(self, label_text="", show_files=False)
        self.save_dir_input.setText(self.curr_save_dir)
        self.save_dir_input.path_changed.connect(self.monitor_changes)
        form_layout.addRow("Saved files directory:", self.save_dir_input)

         # Force
        self.force_input = QtGui.QCheckBox(self)
        self.force_input.setChecked(self.curr_forced)
        self.force_input.stateChanged.connect(self.monitor_changes)
        form_layout.addRow("Force mode:", self.force_input)

        self.button_box = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Apply | QtGui.QDialogButtonBox.Cancel, parent=self)

        self.apply_button = self.button_box.button(QtGui.QDialogButtonBox.Apply)
        self.ok_button = self.button_box.button(QtGui.QDialogButtonBox.Ok)
        self.cancel_button = self.button_box.button(QtGui.QDialogButtonBox.Cancel)

        self.ok_button.setDisabled(True)
        self.apply_button.setDisabled(True)

        self.button_box.clicked.connect(self.handle_click)
        group_box.setLayout(form_layout)
        layout.addWidget(group_box)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

        # Widget as window
        self.setWindowTitle("Snapshot Settings")
        self.setWindowFlags(Qt.Window | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_X11NetWmWindowTypeMenu, True)
        self.setEnabled(True)

    def handle_click(self, button):
        if button == self.apply_button:
            self.apply_config()
        elif button == self.ok_button:
            self.apply_config()
            self.close()
        elif button == self.cancel_button:
            self.close()

    def monitor_changes(self):
        parsed_macros = parse_macros(self.macro_input.text())

        if (parsed_macros != self.curr_macros) or (self.save_dir_input.text() != self.curr_save_dir) or\
                (self.force_input.isChecked() != self.curr_forced):
            self.ok_button.setDisabled(False)
            self.apply_button.setDisabled(False)
        else:
            self.ok_button.setDisabled(True)
            self.apply_button.setDisabled(True)

    def apply_config(self):
        # Return only changed settings
        config = dict()
        parsed_macros = parse_macros(self.macro_input.text())

        if self.save_dir_input.text() != self.curr_save_dir:
            if os.path.isdir(self.save_dir_input.text()):
                config["save_dir"] = self.save_dir_input.text()
                self.curr_save_dir = self.save_dir_input.text()
            else:
                # Prompt user that path is not valid
                warn = "Cannot set saved files directory to: \"" + self.save_dir_input.text() +\
                       "\". Check if it is valid path to directory."
                QtGui.QMessageBox.warning(self, "Warning", warn,
                                          QtGui.QMessageBox.Ok)
                self.save_dir_input.setText(self.curr_save_dir)


        if parsed_macros != self.curr_macros:
            config["macros"] = parse_macros(self.macro_input.text())
            self.curr_macros = parse_macros(self.macro_input.text())


        if self.force_input.isChecked() != self.curr_forced:
            config["force"] = self.force_input.isChecked()
            self.curr_forced = self.force_input.isChecked()

        self.monitor_changes()  # To update buttons state

        self.new_config.emit(config)



class SnapshotFileSelector(QtGui.QWidget):

    """ Widget to select file with dialog box. """

    path_changed = QtCore.pyqtSignal()

    def __init__(self, parent=None, label_text="File:", button_text="...", label_width=None,
                 init_path=None, show_files=True, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)
        self.file_path = init_path

        self.show_files = show_files
        # Create main layout
        layout = QtGui.QHBoxLayout(self)
        layout.setMargin(0)
        layout.setSpacing(10)
        self.setLayout(layout)

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

        file_path_button.clicked.connect(self.open_selector)
        file_path_button.setFixedSize(27, 27)
        self.file_path_input = QtGui.QLineEdit(self)
        self.file_path_input.textChanged.connect(self.change_file_path)
        if label.text():
            layout.addWidget(label)
        layout.addWidget(self.file_path_input)
        layout.addWidget(file_path_button)

        self.initial_file_path = self.text()
        if init_path:
            self.initial_file_path = init_path

    def open_selector(self):
        dialog=QtGui.QFileDialog(self)
        dialog.fileSelected.connect(self.handle_selected)
        dialog.setDirectory(self.initial_file_path)

        if not self.show_files:
            dialog.setFileMode(QtGui.QFileDialog.Directory)
            dialog.setOption(QtGui.QFileDialog.ShowDirsOnly, True)
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


class SnapshotKeywordSelectorWidget(QtGui.QComboBox):

    """
    Widget for defining keywords (labels). Existing keywords are read from
    the common_settings data structure and are suggested to the user in
    drop down menu. Keywords that are selected are returned as list.
    """
    keywords_changed = QtCore.pyqtSignal()

    def __init__(self, common_settings, defaults_only=False, parent=None):
        QtGui.QComboBox.__init__(self, parent)

        self.defaults_only = defaults_only
        self.common_settings = common_settings

        # data holders
        self.selectedKeywords = list()
        self.keywordWidgets = dict()

        # Main layout
        # [selected widgets][input][drop down arrow (part of QComboBox)]
        self.layout = QtGui.QHBoxLayout()
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
        if event.key() in [Qt.Key_Tab, Qt.Key_Enter, Qt.Key_Return, Qt.Key_Space]:
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

        # Skip if already selected or not in predefined labels if defaults_only (force=True overrides defaults_only)
        if keyword and (keyword not in self.selectedKeywords) and (not self.defaults_only or force or self.defaults_only
                                                                    and keyword in default_labels):
            key_widget = SnapshotKeywordWidget(keyword, self)
            key_widget.delete.connect(self.remove_keyword)
            self.keywordWidgets[keyword] = key_widget
            self.selectedKeywords.append(keyword)
            self.layout.insertWidget(len(self.selectedKeywords)-1, key_widget)
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
        labels = list() + self.common_settings["default_labels"]
        if not self.defaults_only:
            labels += self.common_settings["existing_labels"]
            self.addItem("")
        else:
            self.addItem("Select labels ...")

        labels.sort()
        self.addItems(labels)

    def clear_keywords(self):
        keywords_to_remove = copy.copy(self.get_keywords())
        for keyword in keywords_to_remove:
            self.remove_keyword(keyword)


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
    delete = QtCore.pyqtSignal(str)

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
        self.delete.emit(self.keyword)


class SnapshotEditMetadataDialog(QtGui.QDialog):
    def __init__(self, metadata, common_settings, parent=None):
        self.common_settings = common_settings
        self.metadata = metadata

        QtGui.QDialog.__init__(self, parent)
        group_box = QtGui.QGroupBox("Meta-data", self)
        group_box.setFlat(False)
        layout = QtGui.QVBoxLayout()
        form_layout = QtGui.QFormLayout()
        form_layout.setFieldGrowthPolicy(QtGui.QFormLayout.AllNonFixedFieldsGrow)
        form_layout.setMargin(10)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # Make a field to enable user adding a comment
        self.comment_input = QtGui.QLineEdit(self)
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

        self.button_box = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | 
            QtGui.QDialogButtonBox.Cancel, parent=self)

        self.ok_button = self.button_box.button(QtGui.QDialogButtonBox.Ok)
        self.cancel_button = self.button_box.button(QtGui.QDialogButtonBox.Cancel)

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


# This function should be called from outside, to start the gui
def start_gui(*args, **kwargs):
    app = QtGui.QApplication(sys.argv)

    # Load an application style
    default_style_path = os.path.dirname(os.path.realpath(__file__))
    default_style_path = os.path.join(default_style_path, "qss/default.qss")
    app.setStyleSheet("file:///" + default_style_path)

    gui = SnapshotGui(*args, **kwargs)

    sys.exit(app.exec_())
