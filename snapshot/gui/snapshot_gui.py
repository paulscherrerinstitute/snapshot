#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import datetime
import json
import os
import sys
import concurrent.futures


from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from snapshot.ca_core import Snapshot
from snapshot.core import (
    SnapshotError,
    background_workers,
    enable_tracing,
    since_start,
)
from snapshot.parser import ReqParseError, get_save_files, initialize_config

from .compare import SnapshotCompareWidget
from .restore import SnapshotRestoreWidget
from .save import SnapshotSaveWidget
from .utils import DetailedMsgBox, SnapshotConfigureDialog, make_separator


class SnapshotGui(QMainWindow):
    """
    Main GUI class for Snapshot application. It needs separate working
    thread where core of the application is running
    """

    def __init__(self, config: dict = {}, parent=None):
        """
        :param config: application settings
        :param parent: parent QtObject
        :return:
        """
        QMainWindow.__init__(self, parent)

        self.resize(1500, 850)

        if not config or config['config_ok'] is False:
            msg = "Loading configuration file failed! " \
                  "Do you want to continue without it?\n"
            msg_window = DetailedMsgBox(msg, config['config_error'], 'Warning')
            reply = msg_window.exec_()

            if reply == QMessageBox.No:
                QTimer.singleShot(0, lambda: self.close())
                return

        self.common_settings = config

        if not config['req_file_path'] or not config['macros_ok']:
            req_file_macros = config['req_file_macros']
            req_file_path = config['req_file_path']
            init_path = config['init_path']
            configure_dialog = \
                SnapshotConfigureDialog(self,
                                        init_macros=req_file_macros,
                                        init_path=os.path.join(init_path,
                                                               req_file_path))
            configure_dialog.accepted.connect(self.set_request_file)
            if configure_dialog.exec_() == QDialog.Rejected:
                QTimer.singleShot(0, lambda: self.close())
                return

        # Before creating GUI, snapshot must be initialized.
        self.snapshot = Snapshot()

        # Create main GUI components:
        #         menu bar
        #        ______________________________
        #       | save_widget | restore_widget |
        #       |             |                |
        #       | autorefresh |                |
        #       --------------------------------
        #       |        compare_widget        |
        #       --------------------------------
        #       |            sts_log           |
        #        ______________________________
        #                   status_bar
        #

        # menu bar
        menu_bar = self.menuBar()

        file_menu = QMenu("File", menu_bar)
        open_new_req_file_action = QAction("Open", file_menu)
        open_new_req_file_action.setMenuRole(QAction.NoRole)
        open_new_req_file_action.triggered.connect(self.open_new_req_file)
        file_menu.addAction(open_new_req_file_action)

        save_menu_action = QAction("Set output directory", file_menu)
        save_menu_action.setMenuRole(QAction.NoRole)
        save_menu_action.triggered.connect(self.save_new_output_dir)
        file_menu.addAction(save_menu_action)

        quit_action = QAction("Quit", file_menu)
        quit_action.setMenuRole(QAction.NoRole)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        menu_bar.addMenu(file_menu)

        # Status components are needed by other GUI elements
        self.status_log = SnapshotStatusLog(self)
        self.common_settings["sts_log"] = self.status_log
        self.status_bar = SnapshotStatus(self.common_settings, self)
        self.common_settings["sts_info"] = self.status_bar

        # Create status log show/hide control and add it to status bar
        self.show_log_control = QCheckBox("Show status log")
        self.show_log_control.setStyleSheet("background-color: transparent")
        self.show_log_control.stateChanged.connect(self.status_log.setVisible)
        self.status_log.setVisible(False)
        self.status_bar.addPermanentWidget(self.show_log_control)

        # Creating main layout
        # Compare widget. Must be updated in case of file selection
        self.compare_widget = SnapshotCompareWidget(self.snapshot,
                                                    self.common_settings, self)

        self.compare_widget.pvs_filtered.connect(self.handle_pvs_filtered)
        self.compare_widget.restore_requested.connect(
            self._handle_restore_request)

        self.save_widget = SnapshotSaveWidget(self.snapshot,
                                              self.common_settings, self)

        self.restore_widget = SnapshotRestoreWidget(self.snapshot,
                                                    self.common_settings, self)
        self.restore_widget.files_updated.connect(self.handle_files_updated)

        self.restore_widget.files_selected.connect(self.handle_selected_files)

        self.save_widget.saved.connect(self.restore_widget.rebuild_file_list)

        # Restore checkbox
        self.restore_save = QCheckBox("Restore after save")
        self.restore_save.setChecked(True)
        self.restore_save.toggled.connect(self.toggle_restore_after_save)

        self.autorefresh = QCheckBox("Periodic PV update")
        self.autorefresh.setChecked(True)
        self.autorefresh.toggled.connect(self.toggle_autorefresh)

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.save_widget)
        left_layout.addStretch()
        left_layout.addWidget(make_separator(self, 'horizontal'))
        left_layout.addWidget(self.restore_save)
        left_layout.addWidget(self.restore_widget)
        left_layout.addWidget(make_separator(self, 'horizontal'))
        left_layout.addWidget(self.autorefresh)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        sr_splitter = QSplitter(self)
        sr_splitter.addWidget(left_widget)
        sr_splitter.addWidget(self.restore_widget)
        sr_splitter.setStretchFactor(0, 1)
        sr_splitter.setStretchFactor(1, 2)

        main_splitter = QSplitter(self)
        main_splitter.addWidget(sr_splitter)
        main_splitter.addWidget(self.compare_widget)
        main_splitter.addWidget(self.status_log)
        main_splitter.setOrientation(Qt.Vertical)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)

        # Set default widget and add status bar
        self.setCentralWidget(main_splitter)
        self.setStatusBar(self.status_bar)

        # Show GUI and manage window properties
        self.show()
        self.setWindowTitle(
            os.path.basename(self.common_settings["req_file_path"]) +
            ' - Snapshot')

        # Status log default height should be 100px Set with splitter methods
        widgets_sizes = main_splitter.sizes()
        widgets_sizes[main_splitter.indexOf(main_splitter)] = 100
        main_splitter.setSizes(widgets_sizes)

        # Schedule opening the request file for after the GUI is shown.
        QTimer.singleShot(
            100,
            lambda: self.change_req_file(
                self.common_settings['req_file_path'],
                self.common_settings['req_file_macros'],))

    def toggle_restore_after_save(self, checked):
        self.restore_widget.set_checkbox_restore(checked)

    def toggle_autorefresh(self, checked):
        if checked:
            self.autorefresh.setText("Periodic PV update")
            self.autorefresh.setStyleSheet("")
            background_workers.resume_one('pv_updater')
        else:
            current_text = self.autorefresh.text()
            time_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.autorefresh.setText(
                f'{current_text}   (last update: {time_str})')
            # background color to medium gray when not activated
            self.autorefresh.setStyleSheet(
                "QCheckBox {background-color : #868482;}")
            # self.autorefresh.setStyleSheet("QCheckBox {border-left-color: darkgray;}")
            background_workers.suspend_one('pv_updater')

    def save_new_output_dir(self):
        self.output_path = QFileDialog.getExistingDirectory(
            self, 'Select Folder')
        self.common_settings['save_dir'] = self.output_path

    def open_new_req_file(self):
        configure_dialog = SnapshotConfigureDialog(
            self, init_path=self.common_settings['req_file_path'],
            init_macros=self.common_settings['req_file_macros'])
        configure_dialog.accepted.connect(self.change_req_file)
        configure_dialog.exec_()  # Do not act on rejected

    def change_req_file(self, req_file_path, macros):
        background_workers.suspend()
        self.status_bar.set_status("Loading new request file ...", 0, "orange")

        self.set_request_file(req_file_path, macros)
        save_dir = self.common_settings['save_dir']

        # Read snapshots and instantiate PVs in parallel
        def getfiles(*args):
            return get_save_files(*args)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_files = executor.submit(getfiles, save_dir,
                                           req_file_path)
        self.init_snapshot(req_file_path, macros)
        if self.common_settings['save_dir'] == save_dir:
            already_parsed_files = future_files.result()
        else:
            # Apparently init_snapshot() found that the request file was
            # invalid, the save_dir changed, and we need to junk the
            # already read snapfiles.
            future_files.cancel()
            already_parsed_files = get_save_files(
                self.common_settings['save_dir'],
                self.common_settings['req_file_path'])

        # handle all gui components
        self.restore_widget.handle_new_snapshot_instance(self.snapshot,
                                                         already_parsed_files)
        self.save_widget.handle_new_snapshot_instance(self.snapshot)
        self.compare_widget.handle_new_snapshot_instance(self.snapshot)

        self.setWindowTitle(os.path.basename(req_file_path) + ' - Snapshot')

        self.status_bar.set_status("New request file loaded.", 3000, "#64C864")
        background_workers.resume()
        since_start("GUI processing finished")

    def set_request_file(self, path: str, macros: dict):
        self.common_settings["req_file_path"] = path
        self.common_settings["req_file_macros"] = macros
        if not self.common_settings['save_dir']:
            self.common_settings['save_dir'] = os.path.dirname(path)

    def init_snapshot(self, req_file_path, req_macros=None):
        self.snapshot.clear_pvs()
        req_macros = req_macros or {}
        reopen_config = False
        try:
            self.snapshot = Snapshot(req_file_path, req_macros)
            self.set_request_file(req_file_path, req_macros)

        except (ReqParseError, OSError) as e:
            msg = 'Request file cannot be loaded. ' \
                'See details for type of error.'
            msg_window = DetailedMsgBox(msg, str(e), 'Warning', self,
                                        QMessageBox.Ok)
            msg_window.exec_()
            reopen_config = True

        except SnapshotError as e:
            QMessageBox.warning(
                self,
                "Warning",
                str(e),
                QMessageBox.Ok,
                QMessageBox.NoButton)
            reopen_config = True

        if reopen_config:
            configure_dialog = SnapshotConfigureDialog(
                self, init_path=req_file_path, init_macros=req_macros)
            configure_dialog.accepted.connect(self.init_snapshot)
            if configure_dialog.exec_() == QDialog.Rejected:
                self.close()

        # Merge request file metadata into common settings, replacing existing
        # settings.
        # TODO Labels and filters are only overridden if given in the request
        # file, for backwards compatibility with config files. After config
        # files are out of use, change this to always override old values.
        req_labels = self.snapshot.req_file_metadata.get('labels', {})
        if req_labels:
            self.common_settings['force_default_labels'] = \
                req_labels.get('force_default_labels', False)
            self.common_settings['default_labels'] = \
                req_labels.get('labels', [])
        req_filters = self.snapshot.req_file_metadata.get('filters', {})
        if req_filters:
            filters = self.common_settings['predefined_filters']
            for fltype in ('filters', 'rgx-filters', 'rgx-filters-names'):
                filters[fltype] = req_filters.get(fltype, [])

        self.common_settings['machine_params'] = \
            self.snapshot.req_file_metadata.get('machine_params', {})

        # Metadata to be filled from snapshot files.
        self.common_settings['existing_labels'] = []
        self.common_settings['existing_params'] = []

    def handle_files_updated(self):
        self.save_widget.update_labels()
        self.compare_widget.clear_snap_files()

    def handle_selected_files(self, selected_files):
        # selected_files is a dict() with file names as keywords and
        # dict() of pv data as value
        self.compare_widget.new_selected_files(selected_files)

    def _handle_restore_request(self, pvs_list):
        self.restore_widget.do_restore(pvs_list)

    def handle_pvs_filtered(self, pv_names_set):
        # Yes, this merely sets the reference to the set of names, so
        # technically, it needn't be done every time. But good luck tracking
        # down who updated the list without this ;)
        self.restore_widget.filtered_pvs = pv_names_set


# -------- Status widgets -----------
class SnapshotStatusLog(QWidget):
    """ Command line like logger widget """

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.sts_log = QPlainTextEdit(self)
        self.sts_log.setReadOnly(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.sts_log)
        self.setLayout(layout)

    def log_msgs(self, msgs, msg_times):
        if not isinstance(msgs, list):
            msgs = [msgs]

        if not isinstance(msg_times, list):
            msg_times = [msg_times] * len(msgs)

        msg_times = (datetime.datetime.fromtimestamp(
            t).strftime('%H:%M:%S.%f') for t in msg_times)
        self.sts_log.insertPlainText(
            "\n".join(
                "[{}] {}".format(
                    *
                    t) for t in zip(
                    msg_times,
                    msgs)) +
            "\n")
        self.sts_log.ensureCursorVisible()


class SnapshotStatus(QStatusBar):
    def __init__(self, common_settings, parent=None):
        QStatusBar.__init__(self, parent)
        self.common_settings = common_settings
        self.setSizeGripEnabled(False)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.clear_status)
        self.status_txt = QLabel()
        self.status_txt.setStyleSheet("background-color: transparent")
        self.addWidget(self.status_txt)
        self.set_status()

    def set_status(self, text="Ready", duration=0,
                   background="rgba(0, 0, 0, 30)"):
        # Stop any existing timers
        self.timer.stop()

        if self.common_settings["force"]:
            text = f"[force mode] {text}"
        self.status_txt.setText(text)
        style = f"background-color : {background}"
        self.setStyleSheet(style)

        # Force GUI updates to show status
        QtCore.QCoreApplication.processEvents()

        if duration:
            self.timer.start(duration)

    def clear_status(self):
        self.set_status("Ready", 0, "rgba(0, 0, 0, 30)")


# This function should be called from outside, to start the gui
def start_gui(*args, **kwargs):
    if kwargs.get('trace_execution'):
        enable_tracing()

    since_start("Interpreter started")

    config = initialize_config(**kwargs)

    app = QApplication(sys.argv)

    # Load an application style
    default_style_path = os.path.dirname(os.path.realpath(__file__))
    default_style_path = os.path.join(default_style_path, "qss/default.qss")
    app.setStyleSheet("file:///" + default_style_path)

    # IMPORTANT the reference to the SnapshotGui Object need to be retrieved
    # otherwise the GUI will not show up
    _ = SnapshotGui(config)

    since_start("GUI constructed")

    sys.exit(app.exec_())
