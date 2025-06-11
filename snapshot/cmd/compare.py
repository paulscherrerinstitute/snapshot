#!/usr/bin/env python
import concurrent.futures
import sys
import os
import glob
import datetime
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QCheckBox, QDialog, QMessageBox
from PyQt5.QtCore import Qt, QTimer
import time 
from snapshot.gui.utils import DetailedMsgBox, get_version
from snapshot.gui.snapshot_gui import SnapshotCompareWidget, SnapshotStatusLog, SnapshotStatus, SnapshotConfigureDialog, Snapshot, SnapshotRestoreWidget
from snapshot.core import SnapshotError, background_workers, since_start, SnapshotPv, PvUpdaterBulk, PvUpdater
from snapshot.parser import get_save_files, initialize_config, parse_from_save_file

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QSplitter,
    QComboBox,
)

from snapshot.request_files.snapshot_file import ReqParseError


# this is going to be a 'restricted' view of the default snapshot with some removed features and a different pvupdater

class StandaloneCompareWindow(QMainWindow):
    def __init__(self, config=None, parent=None, pv_updater_cls=PvUpdater) -> None:
        super().__init__(parent)
        QMainWindow.__init__(self, parent)  
        if config is None:
            config = {}
        self.output_path = None
        self.resize(1200, 800)

        if not config or config["config_ok"] is False:
            msg = (
                "Loading configuration file failed! "
                "Do you want to continue without it?\n"
            )
            msg_window = DetailedMsgBox(msg, config["config_error"], "Warning")
            reply = msg_window.exec_()

            if reply == QMessageBox.No:
                QTimer.singleShot(0, lambda: self.close())
                return

        self.common_settings = config

        if not config["req_file_path"] or not config["macros_ok"]:
            req_file_macros = config["req_file_macros"]
            req_file_path = config["req_file_path"]
            init_path = config["init_path"]
            configure_dialog = SnapshotConfigureDialog(
                self,
                init_macros=req_file_macros,
                init_path=os.path.join(init_path, req_file_path),
            )
            configure_dialog.accepted.connect(self.set_request_file)
            if configure_dialog.exec_() == QDialog.Rejected:
                QTimer.singleShot(0, lambda: self.close())
                return

        # Before creating GUI, snapshot must be initialized.
        self.snapshot = Snapshot(use_bulk_add=True)

        # Create main GUI components:
        #         menu bar
        #       --------------------------------
        #       |        compare_widget        |
        #       --------------------------------
        #       |            sts_log           |
        #        ______________________________
        #                   status_bar
        #

        self.menuBar()

        # file_menu = QMenu("File", menu_bar)
        # open_new_req_file_action = QAction("Open", file_menu)
        # open_new_req_file_action.setMenuRole(QAction.NoRole)
        # open_new_req_file_action.triggered.connect(self.open_new_req_file)
        # file_menu.addAction(open_new_req_file_action)


        # Status components are needed by other GUI elements
        self.status_log = SnapshotStatusLog(self)
        self.common_settings["sts_log"] = self.status_log
        self.status_bar = SnapshotStatus(self.common_settings, self)
        self.common_settings["sts_info"] = self.status_bar

        # Create status log show/hide control and add it to status bar
        self.show_log_control = QCheckBox("Show status log")
        self.show_log_control.setStyleSheet("background-color: transparent")
        self.show_log_control.stateChanged.connect(self.status_log.setVisible)
        self.status_log.setVisible(True)
        self.status_bar.addPermanentWidget(self.show_log_control)

        # Creating main layout
        # Compare widget. Must be updated in case of file selection
        self.compare_widget = SnapshotCompareWidget(
            self.snapshot, self.common_settings, self, pv_updater_cls=pv_updater_cls
        )

        self.compare_widget.pvs_filtered.connect(self.handle_pvs_filtered)



        self.restore_widget = SnapshotRestoreWidget(
            self.snapshot,
            self.common_settings,
            self,
        )
        self.restore_widget.files_updated.connect(self.handle_files_updated)
        

        self.restore_widget.files_selected.connect(self.handle_selected_files)
        
        # Hide the restore widget since it's not needed in compare mode
        self.restore_widget.hide()

        self.autorefresh = QCheckBox("Periodic PV update")
        self.autorefresh.setChecked(True)
        self.autorefresh.toggled.connect(self.toggle_autorefresh)
        
        self.pv_update_time = QComboBox()
        self.pv_update_time.addItems(["1s", "5s", "10s", "15s", "30s"])
        # self.pv_update_time.setMinimumWidth(25)
        self.pv_update_time.setMaximumWidth(50)
        self.pv_update_time.setCurrentIndex(1)  # Start with 5s
        self.pv_update_time.currentIndexChanged.connect(self.set_pv_update_timer)

        left_layout = QVBoxLayout()
        left_layout.addStretch()
        # left_layout.addWidget(make_separator(self, "horizontal"))
        pv_updater_layout = QHBoxLayout()
        pv_updater_layout.addWidget(self.autorefresh)
        pv_updater_layout.addWidget(self.pv_update_time)
        left_layout.addLayout(pv_updater_layout)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        sr_splitter = QSplitter(self)
        sr_splitter.addWidget(left_widget)
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
            os.path.basename(self.common_settings["req_file_path"]) + " - Snapshot v" + get_version()
        )

        # Status log default height should be 100px Set with splitter methods
        widgets_sizes = main_splitter.sizes()
        widgets_sizes[main_splitter.indexOf(main_splitter)] = 100
        main_splitter.setSizes(widgets_sizes)

        # Schedule opening the request file for after the GUI is shown.
        QTimer.singleShot(
            100,
            lambda: self.change_req_file(
                self.common_settings["req_file_path"],
                self.common_settings["req_file_macros"],
            ),
        )

        if self.common_settings["read_only"]:
            self.status_bar.set_read_only()

        # Schedule the timer change after 100ms
        QTimer.singleShot(100, self._reset_update_timer)
        self.status_log.log_msgs("GUI initialized...", time.time())
        self.snapshot.set_status_log(self.status_log)
        

    def _reset_update_timer(self):
        """Reset the update timer to 5s after initial 1s period"""
        self.pv_update_time.setCurrentIndex(4)  # Set to 30s

    def handle_selected_files(self, selected_files):
        # selected_files is a dict() with file names as keywords and
        # dict() of pv data as value
        self.compare_widget.new_selected_files(selected_files)


    def load_snapshot_files(self, snapshot_file):
        """Load all snapshot files from the same directory as the input file."""
        directory = os.path.dirname(snapshot_file)
        base_name = os.path.splitext(os.path.basename(snapshot_file))[0]
        pattern = os.path.join(directory, f"{base_name}*.snap")

        files_data = {}
        for file_path in sorted(glob.glob(pattern)):
            file_name = os.path.basename(file_path)
            if file_name == "ioc_latest.snap":
                continue
            files_data[file_path] = {
                "file_name": os.path.basename(file_path),
                "file_path": file_path,
                "meta_data": {},
            }

        
        # Add files to model and trigger comparison
        self.compare_widget.model.add_snap_files(files_data)

        # Force update of the view
        self.compare_widget._proxy.invalidate()
        self.compare_widget.view.resizeColumnsToContents()

    def change_req_file(self, req_file_path, macros):
        background_workers.suspend()
        self.status_bar.set_status("Loading new file ...", 0, "orange")

        self.set_request_file(req_file_path, macros)
        save_dir = self.common_settings["save_dir"]

        # Read snapshots and instantiate PVs in parallel
        def getfiles(*args):
            return get_save_files(*args)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_files = executor.submit(getfiles, save_dir, req_file_path)
        self.init_snapshot(req_file_path, macros)
        if self.common_settings["save_dir"] == save_dir:
            future_files.result()
        else:
            # Apparently init_snapshot() found that the request file was
            # invalid, the save_dir changed, and we need to junk the
            # already read snapfiles.
            future_files.cancel()
            get_save_files(
                self.common_settings["save_dir"],
                self.common_settings["req_file_path"],
            )

        # handle all gui components
        self.compare_widget.handle_new_snapshot_instance(self.snapshot)

        self.status_bar.set_status("New file loaded.", 3000, "#64C864")
        background_workers.resume()
        since_start("GUI processing finished")

        # Force an immediate update after loading the file and refresh the view
        def immediate_update():
            self.compare_widget.model._updater.fetch_now()
            self.compare_widget.view.viewport().update()
            self.compare_widget.view.resizeColumnsToContents()
        
        QTimer.singleShot(0, immediate_update)

    def handle_pvs_filtered(self, pv_names_set):
        # Yes, this merely sets the reference to the set of names, so
        # technically, it needn't be done every time. But good luck tracking
        # down who updated the list without this ;)
        self.restore_widget.filtered_pvs = pv_names_set

    def set_request_file(self, path: str, macros: dict):
        self.common_settings["req_file_path"] = path
        self.common_settings["req_file_macros"] = macros
        if not self.common_settings["save_dir"]:
            self.common_settings["save_dir"] = os.path.dirname(path)

    def set_pv_update_timer(self):
        """Set the PV update timer based on the combo box selection"""
        self.compare_widget.set_pv_update_time(
            int(self.pv_update_time.currentText().strip("s"))
        )
        # Force an immediate update when changing the timer
        self.compare_widget.model._updater.fetch_now()

    def toggle_autorefresh(self, checked):
        if checked:
            self.autorefresh.setText("Periodic PV update")
            self.autorefresh.setStyleSheet("")
            background_workers.resume_one("pv_updater")
        else:
            current_text = self.autorefresh.text()
            time_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.autorefresh.setText(f"{current_text}   (last update: {time_str})")
            # background color to medium gray when not activated
            self.autorefresh.setStyleSheet("QCheckBox {background-color : #868482;}")
            # self.autorefresh.setStyleSheet("QCheckBox {border-left-color: darkgray;}")
            background_workers.suspend_one("pv_updater")

    def open_new_req_file(self):
        configure_dialog = SnapshotConfigureDialog(
            self,
            init_path=self.common_settings["req_file_path"],
            init_macros=self.common_settings["req_file_macros"],
        )
        configure_dialog.accepted.connect(self.change_req_file)
        configure_dialog.exec_()  # Do not act on rejected

    # def handle_pvs_filtered(self, pv_names_set):
        # Yes, this merely sets the reference to the set of names, so
        # technically, it needn't be done every time. But good luck tracking
        # down who updated the list without this ;)
        # self.restore_widget.filtered_pvs = pv_names_set

    def init_snapshot(self, req_file_path, req_macros=None):
        self.snapshot.clear_pvs()
        req_macros = req_macros or {}
        reopen_config = False
        try:
            self.snapshot = Snapshot(req_file_path, req_macros, use_bulk_add=True, status_log=self.status_log)
            self.set_request_file(req_file_path, req_macros)

            # readonly mode detection
            self.common_settings["read_only"] = self.snapshot.req_file_metadata.get(
                "read_only", self.common_settings["read_only"]
            )
            if self.common_settings["read_only"]:
                self.restore_widget.hide_restore_buttons()
            else:
                self.restore_widget.show_restore_buttons()

        except (ReqParseError, OSError) as e:
            msg = "Request file cannot be loaded. " "See details for type of error."
            msg_window = DetailedMsgBox(msg, str(e), "Warning", self, QMessageBox.Ok)
            msg_window.exec_()
            reopen_config = True

        except SnapshotError as e:
            QMessageBox.warning(
                self, "Warning", str(e), QMessageBox.Ok, QMessageBox.NoButton
            )
            reopen_config = True

        if reopen_config:
            configure_dialog = SnapshotConfigureDialog(
                self, init_path=req_file_path, init_macros=req_macros
            )
            configure_dialog.accepted.connect(self.init_snapshot)
            if configure_dialog.exec_() == QDialog.Rejected:
                self.close()

        # Merge request file metadata into common settings, replacing existing
        # settings.
        # TODO Labels and filters are only overridden if given in the request
        # file, for backwards compatibility with config files. After config
        # files are out of use, change this to always override old values.
        req_labels = self.snapshot.req_file_metadata.get("labels", {})
        if req_labels:
            self.common_settings["force_default_labels"] = req_labels.get(
                "force_default_labels", False
            )
            self.common_settings["default_labels"] = req_labels.get("labels", [])
        req_filters = self.snapshot.req_file_metadata.get("filters", {})
        if req_filters:
            filters = self.common_settings["predefined_filters"]
            for fltype in ("filters", "rgx_filters", "rgx_filters_names"):
                filters[fltype] = req_filters.get(fltype, [])

        self.common_settings["machine_params"] = self.snapshot.req_file_metadata.get(
            "machine_params", {}
        )

        # Metadata to be filled from snapshot files.
        self.common_settings["existing_labels"] = []
        self.common_settings["existing_params"] = []

        # Find all snapshot files in the same directory as the request file
        directory = os.path.dirname(req_file_path)
        base_name = os.path.splitext(os.path.basename(req_file_path))[0]
        pattern = os.path.join(directory, f"{base_name}*.snap")

        selected_files = {}
        for file_path in sorted(glob.glob(pattern)):
            # Skip ioc_latest files
            if os.path.basename(file_path) == 'ioc_latest.snap':
                continue
                
            # Parse the snapshot file to get its values and metadata
            saved_pvs, meta_data, err = parse_from_save_file(file_path)
            if err:
                print(f"Warning: Errors parsing {file_path}: {err}")
                continue
            
            # Use just the file name as the key, not the full path
            file_name = os.path.basename(file_path)
            selected_files[file_name] = {
                "file_name": file_name,
                "file_path": file_path,
                "meta_data": meta_data,
                "pvs": saved_pvs
            }

        # Delay the signal emission to ensure the compare widget is fully constructed
        QTimer.singleShot(100, lambda: self.restore_widget.files_selected.emit(selected_files))
        QTimer.singleShot(100, lambda: self.restore_widget.hide())

    def handle_files_updated(self):
        self.load_snapshot_files(self.common_settings["req_file_path"])

    def _replace_macros_on_file_data(self, file_data):
        macros = self.snapshot.macros or file_data["meta_data"].get("macros", dict())
        # Use the already parsed PVs from file_data if available
        if "pvs" in file_data:
            pvs_list = file_data["pvs"]
        else:
            pvs_list, _, errors = parse_from_save_file(file_data["file_path"])
            
        # PVS data mapped to real pvs names (no macros)
        pvs_list_full_names = {
            SnapshotPv.macros_substitution(pv_name_raw, macros): {
                "value": pv_data.get("value"),
                "raw_value": pv_data.get("value")  # Store raw value for display
            }
            for pv_name_raw, pv_data in pvs_list.items()
        }

        return pvs_list_full_names, []


def standalone_compare(*args, **kwargs):
    since_start("Interpreter started")
    

    config = initialize_config(**kwargs)
    app = QApplication(sys.argv)
    _ = StandaloneCompareWindow(config, pv_updater_cls=PvUpdaterBulk)
    
    since_start("Standalone compare constructed")

    sys.exit(app.exec_())


