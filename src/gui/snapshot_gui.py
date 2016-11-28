#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import datetime
import json
import os
import sys

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from ..ca_core.snapshot_ca import Snapshot, SnapshotError, ReqParseError
from .compare import SnapshotCompareWidget
from .restore import SnapshotRestoreWidget
from .save import SnapshotSaveWidget
from .utils import SnapshotConfigureDialog, SnapshotSettingsDialog, DetailedMsgBox


class SnapshotGui(QtGui.QMainWindow):
    """
    Main GUI class for Snapshot application. It needs separate working
    thread where core of the application is running
    """

    def __init__(self, req_file_path: str = None, req_file_macros = None, save_dir: str = None, force: bool =False,
                 default_labels: list = None, force_default_labels: bool = None, init_path: str = None,
                 config_path: str = None, parent=None):
        '''

        :param req_file_path: path to request file
        :param req_file_macros: macros can be as dict (key, value pairs) or a string in format A=B,C=D
        :param save_dir: path to the default save directory
        :param force: force saving on disconnected channels
        :param default_labels: list of default labels
        :param force_default_labels: if True, user can only select predefined labels
        :param init_path: default path to be shown on the file selector
        :param config_path: path to configuration file
        :param parent: Parent QtObject
        :return:
        '''
        QtGui.QMainWindow.__init__(self, parent)

        if config_path:
            # Validate configuration file
            try:
                config = json.load(open(config_path))
                # force-labels must be type of bool
                if not isinstance(config.get('labels', dict()).get('force-labels', False), bool):
                    raise TypeError('"force-labels" must be boolean')
            except Exception as e:
                msg = "Loading configuration file failed! Do you want to continue with out it?\n"
                msg_window = DetailedMsgBox(msg, str(e), 'Warning')
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
        self.common_settings["existing_labels"] = list()  # labels that are already in snap files
        self.common_settings["force"] = force

        if isinstance(default_labels, str):
            default_labels = default_labels.split(',')

        elif not isinstance(default_labels, list):
            default_labels = list()

        # default labels also in config file? Add them
        self.common_settings["default_labels"] = list(set(default_labels +
                                                          (config.get('labels', dict()).get('labels', list()))))

        self.common_settings["force_default_labels"] = config.get('labels', dict()).get('force-labels', False) or \
                                                       force_default_labels

        # Predefined filters
        self.common_settings["predefined_filters"] = config.get('filters', dict())

        if req_file_macros is None:
            req_file_macros = dict()

        if not req_file_name:
            configure_dialog = SnapshotConfigureDialog(self, init_path=init_path, init_macros=req_file_macros)
            configure_dialog.accepted.connect(self.set_request_file)

            self.hide()
            if configure_dialog.exec_() == QtGui.QDialog.Rejected:
                self.close_gui()

        else:
            self.common_settings["req_file_path"] = os.path.abspath(req_file_name)
            self.common_settings["req_file_macros"] = req_file_macros

        self.common_settings["pvs_to_restore"] = list()

        # Before creating GUI, snapshot must be initialized.
        self.init_snapshot(self.common_settings["req_file_path"],
                           self.common_settings["req_file_macros"])

        if not save_dir:
            # Default save dir (do this once we have valid req file)
            save_dir = os.path.dirname(self.common_settings["req_file_path"])

        self.common_settings["save_dir"] = os.path.abspath(save_dir)

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
        self.status_bar = SnapshotStatus(self.common_settings, self)
        self.common_settings["sts_info"] = self.status_bar

        # Create status log show/hide control and add it to status bar
        self.show_log_control = QtGui.QCheckBox("Show status log")
        self.show_log_control.setStyleSheet("background-color: transparent")
        self.show_log_control.stateChanged.connect(self.status_log.setVisible)
        self.status_log.setVisible(False)
        self.status_bar.addPermanentWidget(self.show_log_control)

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
        self.restore_widget.update_files()

        self.restore_widget.files_selected.connect(self.handle_selected_files)

        sr_splitter = QtGui.QSplitter(self)
        sr_splitter.addWidget(self.save_widget)
        sr_splitter.addWidget(self.restore_widget)
        element_size = (self.save_widget.sizeHint().width() + self.restore_widget.sizeHint().width()) / 2
        sr_splitter.setSizes([element_size, element_size])

        main_splitter = QtGui.QSplitter(self)
        main_splitter.addWidget(sr_splitter)
        main_splitter.addWidget(self.compare_widget)
        main_splitter.addWidget(self.status_log)
        main_splitter.setOrientation(Qt.Vertical)

        # Set default widget and add status bar
        self.setCentralWidget(main_splitter)
        self.setStatusBar(self.status_bar)

        # Show GUI and manage window properties
        self.show()
        self.setWindowTitle(
            os.path.basename(self.common_settings["req_file_path"]) + ' - Snapshot')

        # Status log default height should be 100px Set with splitter methods
        widgets_sizes = main_splitter.sizes()
        widgets_sizes[main_splitter.indexOf(main_splitter)] = 100
        main_splitter.setSizes(widgets_sizes)

    def open_new_req_file(self):
        configure_dialog = SnapshotConfigureDialog(self, init_path=self.common_settings['req_file_path'],
                                                   init_macros=self.common_settings['req_file_macros'])
        configure_dialog.accepted.connect(self.change_req_file)
        configure_dialog.exec_()  # Do not act on rejected

    def change_req_file(self, req_file_path, macros):
        self.status_bar.set_status("Loading new request file ...", 0, "orange")
        self.set_request_file(req_file_path, macros)
        self.init_snapshot(req_file_path, macros)

        # handle all gui components
        self.restore_widget.handle_new_snapshot_instance(self.snapshot)
        self.save_widget.handle_new_snapshot_instance(self.snapshot)
        self.compare_widget.handle_new_snapshot_instance(self.snapshot)

        self.setWindowTitle(os.path.basename(req_file_path) + ' - Snapshot')

        self.status_bar.set_status("New request file loaded.", 3000, "#64C864")

    def handle_saved(self):
        # When save is done, save widget is updated by itself
        # Update restore widget (new file in directory)
        self.restore_widget.update_files()

    def set_request_file(self, path:str, macros: dict):
        self.common_settings["req_file_path"] = path
        self.common_settings["req_file_macros"] = macros

    def init_snapshot(self, req_file_path, req_macros=None):
        req_macros = req_macros or {}
        reopen_config = False
        try:
            self.snapshot = Snapshot(req_file_path, req_macros)
            self.set_request_file(req_file_path, req_macros)

        except IOError:
            warn = "File {} does not exist!".format(req_file_path)
            QtGui.QMessageBox.warning(self, "Warning", warn, QtGui.QMessageBox.Ok, QtGui.QMessageBox.NoButton)
            reopen_config = True

        except ReqParseError as e:
            msg = 'Snapshot cannot be loaded due to a syntax error in request file. See details.'
            msg_window = DetailedMsgBox(msg, str(e), 'Warning', self, QtGui.QMessageBox.Ok)
            msg_window.exec_()
            reopen_config = True

        except SnapshotError as e:
            QtGui.QMessageBox.warning(self, "Warning", str(e), QtGui.QMessageBox.Ok, QtGui.QMessageBox.NoButton)
            reopen_config = True

        if reopen_config:
            configure_dialog = SnapshotConfigureDialog(self, init_path=req_file_path, init_macros=req_macros)
            configure_dialog.accepted.connect(self.init_snapshot)
            if configure_dialog.exec_() == QtGui.QDialog.Rejected:
                self.close_gui()

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
        settings_window.resize(800, 200)
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


# -------- Status widgets -----------
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

    def log_msgs(self, msgs, msg_times):
        if not isinstance(msgs, list):
            msgs = [msgs]

        if not isinstance(msg_times, list):
            msg_times = [msg_times] * len(msgs)

        msg_times = (datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S.%f') for t in msg_times)
        self.sts_log.insertPlainText("\n".join("[{}] {}".format(*t) for t in zip(msg_times, msgs)) + "\n")
        self.sts_log.ensureCursorVisible()


class SnapshotStatus(QtGui.QStatusBar):
    def __init__(self, common_settings, parent=None):
        QtGui.QStatusBar.__init__(self, parent)
        self.common_settings = common_settings
        self.setSizeGripEnabled(False)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._clear_status)
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

        # Force GUI updates to show status
        QtCore.QCoreApplication.processEvents()

        if duration:
            self.timer.start(duration)

    def _clear_status(self):
        self.set_status("Ready", 0, "rgba(0, 0, 0, 30)")


# This function should be called from outside, to start the gui
def start_gui(*args, **kwargs):
    app = QtGui.QApplication(sys.argv)

    # Load an application style
    default_style_path = os.path.dirname(os.path.realpath(__file__))
    default_style_path = os.path.join(default_style_path, "qss/default.qss")
    app.setStyleSheet("file:///" + default_style_path)

    gui = SnapshotGui(*args, **kwargs)

    sys.exit(app.exec_())
