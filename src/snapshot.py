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
from snapshot_ca import PvStatus, ActionStatus, Snapshot
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


class SnapshotStatusLog(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.sts_log = QtGui.QPlainTextEdit(self)
        self.sts_log.setReadOnly(True)

        layout = QtGui.QVBoxLayout()  # To have margin option
        layout.setMargin(10)
        layout.addWidget(self.sts_log)
        self.setLayout(layout)
        
    def log_line(self, text):
        time_stamp = "[" + datetime.datetime.fromtimestamp(
                time.time()).strftime('%H:%M:%S.%f') + "] "
        self.sts_log.insertPlainText(time_stamp + text + "\n")
        self.sts_log.ensureCursorVisible()


class SnapshotStatus(QtGui.QStatusBar):
    def __init__(self, parent=None):
        QtGui.QStatusBar.__init__(self, parent)
        self.setSizeGripEnabled(False)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.clear_status)

        self.status_txt = QtGui.QLineEdit()
        self.status_txt.setStyleSheet("""
            border : 0px;
            background-color : transparent;
            """)
        self.addWidget(self.status_txt)
        self.set_status()

    def set_status(self, text="Ready", duration=0, background="#E5E5E5"):
        self.status_txt.setText(text)
        style = "background-color : " + background
        self.setStyleSheet(style)

        if duration:
            self.timer.start(duration)

    def clear_status(self):
        self.set_status("Ready", 0, "#E5E5E5")


class SnapshotGui(QtGui.QMainWindow):
    """
    Main GUI class for Snapshot application. It needs separate working
    thread where core of the application is running
    """

    def __init__(self, req_file_name=None, req_file_macros=None,
                 save_dir=None, save_file_dft=None, mode=None, parent=None):
        QtGui.QMainWindow.__init__(self, parent)

        self.resize(1500, 850)

        # common_settings is a dictionary which holds common configuration of
        # the application (such as directory with save files, request file
        # path, etc). It is propagated to other snapshot widgets if needed
        self.common_settings = dict()
        self.common_settings["req_file_name"] = ""
        self.common_settings["req_file_macros"] = dict()   

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
            # Set current dir as save dir
            save_dir = os.path.dirname(os.path.realpath(__file__))

        self.common_settings["save_dir"] = save_dir
        self.common_settings["save_file_dft"] = save_file_dft
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
        status_bar = SnapshotStatus()
        self.common_settings["sts_info"] = status_bar

        # Creating main layout
        self.save_widget = SnapshotSaveWidget(self.snapshot,
                                              self.common_settings, self)
        self.connect(self.save_widget, SIGNAL("save_done"),
                     self.save_done)
        self.restore_widget = SnapshotRestoreWidget(self.snapshot,
                                                    self.common_settings, self)
        self.compare_widget = SnapshotCompareWidget(self.snapshot,
                                                    self.common_settings, self)

        sr_splitter = QtGui.QSplitter(self)
        sr_splitter.addWidget(self.save_widget)
        sr_splitter.addWidget(self.restore_widget)
        sr_splitter.setStretchFactor(0, 2)
        sr_splitter.setStretchFactor(1, 1)

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
        self.setWindowTitle(os.path.basename(self.common_settings["req_file_name"]) + ' - Snapshot')

        # Status log default height should be 100px Set with splitter methods
        widgets_sizes = main_splitter.sizes()
        widgets_sizes[main_splitter.indexOf(main_splitter)] = 100
        main_splitter.setSizes(widgets_sizes)

    def save_done(self):
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
        self.labels_input = QtGui.QLineEdit(self)
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
        #of saving. Will be unlocked when save is finished.
        if not self.extension_input.text():
            #  Update name with latest timestamp
            self.update_name()

        if self.check_file_existance():
            self.save_button.setEnabled(False)
            self.sts_log.log_line("Save started.")
            self.sts_info.set_status("Saving ...", 0, "orange")

            # Start saving process and notify when finished
            status, pvs_status = self.snapshot.save_pvs(self.file_path,
                                                        labels=self.labels_input.text(),
                                                        comment=self.comment_input.text())
            if status == ActionStatus.no_cnct:
                self.sts_log.log_line("ERROR: Save rejected. One or more PVs not connected.")
                self.sts_info.set_status("Cannot save", 3000, "#F06464")
                self.save_button.setEnabled(True)
            else:
                # If not no_cnct, then .ok
                self.save_done(pvs_status)
        else:
            # User rejected saving into same file. No error.
            self.sts_info.clear_status()

    def save_done(self, status):
        # Enable saving
        error = False
        for key in status:
            sts = status[key]
            if status[key] == PvStatus.access_err:
                error = True
                self.sts_log.log_line("ERROR: " + key + \
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
        name_extension_inp = self.extension_input.text()
        if not name_extension_inp:
            name_extension_rb = "{TIMESTAMP}" + self.save_file_sufix
            self.name_extension = datetime.datetime.fromtimestamp(
                time.time()).strftime('%Y%m%d_%H%M%S')
        else:
            self.name_extension = name_extension_inp
            name_extension_rb = name_extension_inp + self.save_file_sufix
        self.file_path = os.path.join(self.common_settings["save_dir"],
                                      self.name_base + self.name_extension + \
                                      self.save_file_sufix)
        self.file_name_rb.setText(self.name_base + name_extension_rb)

    def check_file_existance(self):
        if os.path.exists(self.file_path):
            msg = "File already exists. Do you want to override it?\n" + \
                  self.file_path
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)

            if reply == QtGui.QMessageBox.No:
                return False
        return True

    def paintEvent(self, pe):
        #To have possibility of class in style sheet
        opt = QtGui.QStyleOption()
        opt.init(self)
        p = QtGui.QPainter(self)
        s = self.style()
        s.drawPrimitive(QtGui.QStyle.PE_Widget, opt, p, self)


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

        # Create file list for first time
        self.file_selector.start_file_list_update()

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

        status = self.snapshot.restore_pvs(callback=self.restore_done_callback)
        if status == ActionStatus.no_data:
            self.sts_log.log_line("ERROR: No file selected.")
            self.sts_info.set_status("Restore rejected", 3000, "#F06464")
            self.restore_button.setEnabled(True)
        elif status == ActionStatus.no_cnct:
            self.sts_log.log_line("ERROR: Restore rejected. One or more PVs not connected.")
            self.sts_info.set_status("Restore rejected", 3000, "#F06464")
            self.restore_button.setEnabled(True)
        elif status == ActionStatus.busy:
            pass
            # Since enabling/disabling buttons this case should not happen.
            self.sts_log.log_line("ERROR: Restore rejected. Previous restore not finished.")

    def restore_done_callback(self, status, **kw):
        # Raise callback to handle GUI specific in GUI thread
        self.emit(SIGNAL("restore_done_callback"), status)

    def restore_done(self, status):
        error = False
        if not status:
            error = True
            self.sts_log.log_line("ERROR: No file selected.")
            self.sts_info.set_status("Cannot restore", 3000, "#F06464")
        else:
            for key in status:
                pv_status = status[key]
                if pv_status == PvStatus.access_err:
                    error = True
                    self.sts_log.log_line("ERROR: " + key + \
                        ": Not restored (no connection or readonly).")
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


class SnapshotRestoreFileSelector(QtGui.QWidget):
    def __init__(self, snapshot, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.snapshot = snapshot
        self.selected_file = None
        self.common_settings = common_settings

        self.file_list = dict()
        self.pvs = dict()

        # Filter handling
        self.file_filter = dict()
        #self.file_filter["time"] = list()  # star and end date
        self.file_filter["keys"] = list()
        self.file_filter["comment"] = ""

        self.filter_input = SnapshotFileFilterWidget(self)
        self.connect(self.filter_input, SIGNAL(
            "file_filter_updated"), self.filter_file_list_selector)

        # Create list with: file names, comment, labels
        self.file_selector = QtGui.QTreeWidget(self)
        self.file_selector.setRootIsDecorated(False)
        self.file_selector.setIndentation(0)
        self.file_selector.setStyleSheet("""
            QTreeWidget::item:pressed,QTreeWidget::item:selected{
            background-color:#FF6347;color:#FFFFFF}‌​
            """)
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
                    parsed_save_files[file_name]["modif_time"] = os.path.getmtime(file_path)

        return parsed_save_files

    def update_file_list_selector(self, file_list):
        for key in file_list:
            meta_data = file_list[key]["meta_data"]
            labels = meta_data.get("labels", "")
            comment = meta_data.get("comment", "")

            # check if already on list (was just modified) and modify file
            # selector
            if key not in self.file_list:
                selector_item = QtGui.QTreeWidgetItem([key, comment, labels])
                self.file_selector.addTopLevelItem(selector_item)
                self.file_list[key] = file_list[key]
                self.file_list[key]["file_selector"] = selector_item
            else:
                # If everything ok only one file should exist in list
                to_modify = self.file_list[key]["file_selector"]
                to_modify.setText(1, comment)
                to_modify.setText(2, labels)

        # Set column sizes
        self.file_selector.resizeColumnToContents(0)
        self.file_selector.setColumnWidth(1, 400)

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
                #time_filter = file_filter.get("time")
                keys_filter = file_filter.get("keys")
                comment_filter = file_filter.get("comment")
                name_filter = file_filter.get("name")

                #### DATE FILTER REMOVED ###
                #if time_filter is not None:
                #    # valid names are all between this two dates
                #    # convert file name back to date and check if between
                #    modif_time = file_to_filter["meta_data"]["save_time"]#

                #    if time_filter[0] is not None and time_filter is not None:
                #        time_filter.sort()#

                #    if time_filter[0] is not None:
                #        time_status = (modif_time >= time_filter[0])
                #    else:
                #        time_status = True

                #    if time_filter[1] is not None:
                #        time_status = time_status and (
                #            modif_time <= time_filter[1]+86399)  # End of day
                #else:
                #    time_status = True
                #### DATE FILTER REMOVED ###

                if keys_filter:
                    # get file keys as list
                    labels = file_to_filter[
                        "meta_data"]["labels"].split(' ')
                    keys_status = False

                    for key in labels:
                        # Breake when first found
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
                    self.file_selector.takeTopLevelItem(self.file_selector.indexOfTopLevelItem(self.file_selector.currentItem()))
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

        # Create main layout
        layout = QtGui.QHBoxLayout(self)
        layout.setMargin(0)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Create filter selectors (with readbacks)
        # - text input to filter by name
        # - text input to filter comment
        # - labels selector

        #### DATE FILTER REMOVED ###
        # date selector
        #date_layout = QtGui.QHBoxLayout()
        #date_layout.setMargin(0)
        #date_layout.setSpacing(10)

        #from_label = QtGui.QLabel("From:", self)
        #self.date_from = SnapshotDateSelector(self)
        #to_label = QtGui.QLabel("To:", self)
        #self.date_to = SnapshotDateSelector(self, day_end=True)

        #date_layout.addWidget(from_label)
        #date_layout.addWidget(self.date_from)
        #date_layout.addWidget(to_label)
        #date_layout.addWidget(self.date_to)
        #### DATE FILTER REMOVED ###

        # Init filters
        self.file_filter = dict()
        #self.file_filter["time"] = [
        #    self.date_from.selected_date, self.date_to.selected_date]
        self.file_filter["keys"] = list()
        self.file_filter["comment"] = ""
        self.file_filter["name"] = ""

        #### DATE FILTER REMOVED ###
        # Connect after file_filter exist
        #self.connect(
        #    self.date_from, SIGNAL("date_updated"), self.update_filter)
        #self.connect(self.date_to, SIGNAL("date_updated"), self.update_filter)
        #### DATE FILTER REMOVED ###

        # Labels filter
        key_layout = QtGui.QHBoxLayout()
        key_label = QtGui.QLabel("Labels:", self)
        self.keys_input = QtGui.QLineEdit(self)
        self.keys_input.setPlaceholderText("label_1 label_2 ...")
        self.keys_input.textChanged.connect(self.update_filter)
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

        # Add to main layout
        #### DATE FILTER REMOVED ###
        #layout.addItem(date_layout)
        #### DATE FILTER REMOVED ###
        layout.addItem(name_layout)
        layout.addItem(comment_layout)
        layout.addItem(key_layout)


    def update_filter(self):
        #### DATE FILTER REMOVED ###
        #self.file_filter["time"] = [
        #    self.date_from.selected_date, self.date_to.selected_date]
        #### DATE FILTER REMOVED ###
        if self.keys_input.text().strip(''):
            self.file_filter["keys"] = self.keys_input.text().strip('').split(' ')
        else:
            self.file_filter["keys"] = list()
        self.file_filter["comment"] = self.comment_input.text().strip('')
        self.file_filter["name"] = self.name_input.text().strip('')

        self.emit(SIGNAL("file_filter_updated"))


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
        raise a callback which is then catched in worker and passed with
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
        #print(QtCore.QThread.currentThreadId())
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
        QtGui.QTreeWidgetItem.__init__(self, parent, [pv_name, "", "", "PV not connected!"])
        self.pv_name = pv_name

        # Have data stored in native types, for easier filtering etc.
        self.connect_sts = None
        self.saved_value = None
        self.saved_sts = None
        self.value = None
        self.compare = None
        self.has_error = None

        # Variables to hold current filter. Whenever filter is applied they are
        # updated. When filter is applied from items own metods (like
        # update_state), this stored values are used.
        self.compare_filter = 0
        self.completeness_filter = True
        self.name_filter = None

    def update_state(self, pv_value, pv_saved, pv_compare, pv_cnct_sts, saved_sts, **kw):
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

        compare_match = ((PvCompareFilter(compare_filter) == PvCompareFilter.show_eq) and
                         self.compare) or ((PvCompareFilter(compare_filter) == PvCompareFilter.show_neq) and
                                             (not self.compare)) or (PvCompareFilter(compare_filter) == PvCompareFilter.show_all)

        # Do show values which has incomplete data?
        completeness_match = completeness_filter or \
            (not completeness_filter and not self.has_error)

        self.setHidden(
            not(name_match and compare_match and completeness_match))


# Helper widgets
class SnapshotDateSelector(QtGui.QWidget):

    def __init__(self, parent=None, dft_date=None, day_end=False, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        layout = QtGui.QHBoxLayout(self)
        layout.setMargin(0)
        layout.setSpacing(0)
        self.date_input = SnapshotDateSelectorInput(self, dft_date, day_end)
        clear_button = QtGui.QPushButton("Clear", self)
        clear_button.setMaximumWidth(50)
        clear_button.clicked.connect(self.clear_date)

        self.connect(self.date_input, SIGNAL("date_updated"), self.update_date)

        layout.addWidget(self.date_input)
        layout.addWidget(clear_button)

        self.selected_date = None

    def clear_date(self):
        self.date_input.clear_date()
        self.selected_date = self.date_input.selected_date

    def update_date(self):
        self.selected_date = self.date_input.selected_date
        self.emit(SIGNAL("date_updated"))


class SnapshotDateSelectorInput(QtGui.QLineEdit):

    def __init__(self, parent=None, dft_date=None, day_end=False, **kw):
        QtGui.QLineEdit.__init__(self, parent, **kw)

        self.selector = SnapshotDateSelectorWindow(self, dft_date, day_end)
        self.connect(self.selector, SIGNAL("date_selected"), self.update_date)

        self.selected_date = None

    def mousePressEvent(self, event):
        self.selector.move(self.mapToGlobal(self.pos()))
        self.selector.show()

    def update_date(self):
        self.selected_date = self.selector.selected_date
        self.setText(self.selector.date_line.text())
        self.emit(SIGNAL("date_updated"))

    def clear_date(self):
        self.selector.clear_date()


class SnapshotDateSelectorWindow(QtGui.QWidget):

    def __init__(self, parent=None, dft_date=None, day_end=False, **kw):

        QtGui.QWidget.__init__(self, parent, **kw)
        self.dft_date = dft_date
        self.day_end = day_end
        self.date_valid = False
        # Main Layout
        layout = QtGui.QVBoxLayout(self)

        # readback + today button + clear button
        head_layout = QtGui.QHBoxLayout()
        self.date_line = QtGui.QLineEdit(self)
        self.date_line.setPlaceholderText("dd.mm.yyyy")
        self.date_line.editingFinished.connect(self.check_date)
        today_button = QtGui.QPushButton("Today", self)
        today_button.clicked.connect(self.set_today)
        clear_button = QtGui.QPushButton("Clear", self)
        clear_button.clicked.connect(self.clear_internal)
        head_layout.addWidget(self.date_line)
        head_layout.addWidget(today_button)
        head_layout.addWidget(clear_button)

        # Calendar and apply button
        self.cal = QtGui.QCalendarWidget(self)
        self.cal.clicked.connect(self.cal_changed)
        apply_button = QtGui.QPushButton("Apply", self)
        apply_button.clicked.connect(self.apply_date)

        layout.addItem(head_layout)
        layout.addWidget(self.cal)
        layout.addWidget(apply_button)

        # Make as a window
        self.setWindowTitle("Date selector")
        self.setWindowFlags(Qt.Window | Qt.Tool)
        self.setAttribute(Qt.WA_X11NetWmWindowTypeMenu, True)
        self.setEnabled(True)

        self.selected_date = 0
        self.set_today()

    def cal_changed(self):
        self.date_line.setText(self.cal.selectedDate().toString("dd.MM.yyyy"))
        self.date_valid = True

    def set_today(self):
        today = time.time()
        y = int(datetime.datetime.fromtimestamp(today).strftime('%Y'))
        m = int(datetime.datetime.fromtimestamp(today).strftime('%m'))
        d = int(datetime.datetime.fromtimestamp(today).strftime('%d'))
        self.cal.setSelectedDate(QtCore.QDate(y, m, d))
        self.date_line.setText(
            datetime.datetime.fromtimestamp(today).strftime('%d.%m.%Y'))
        self.date_valid = True

    def clear_internal(self):
        # To be used only by this widget
        self.date_line.setText("")
        self.date_valid = True

    def check_date(self):
        date_str = self.date_line.text()
        condition = re.compile('[0-9]{2}\.[0-9]{2}\.[0-9]{4}')
        if condition.match(date_str) is not None:
            self.date_valid = True
            date_to_set = date_str.split('.')
            self.cal.setSelectedDate(
                QtCore.QDate(int(date_to_set[2]), int(date_to_set[1]), int(date_to_set[0])))
        else:
            self.date_valid = False

        return self.date_valid

    def apply_date(self):
        if self.date_valid:
            if self.day_end:
                time_str_full = self.date_line.text()
            else:
                time_str_full = self.date_line.text()
            if self.date_line.text():
                self.selected_date = time.mktime(
                    time.strptime(time_str_full, '%d.%m.%Y'))
            else:
                self.selected_date = self.dft_date

            self.emit(SIGNAL("date_selected"))
            self.hide()

    def clear_date(self):
        # To be used from outside
        self.clear_internal()
        self.apply_date()


class SnapshotFileSelector(QtGui.QWidget):

    """ Widget to select file with dialog box. """

    def __init__(self, parent=None, label_text="File:", button_text="Browse",
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
        #self.req_file_dialog.setOptions(QtGui.QFileDialog.DontUseNativeDialog)
        self.req_file_dialog.fileSelected.connect(self.set_file_input_text)

        # This widget has 3 parts:
        #   label
        #   input field (when value of input is changed, it is stored locally)
        #   icon button to open file dialog
        label = QtGui.QLabel(label_text, self)
        label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        file_path_button = QtGui.QToolButton(self)
        file_path_button.setText("...")

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
        self.file_selector = SnapshotFileSelector(self)
        macros_layout = QtGui.QHBoxLayout()
        macros_label = QtGui.QLabel("Macros:", self)
        macros_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        self.macros_input = QtGui.QLineEdit(self)
        self.macros_input.setPlaceholderText("MACRO1=M1,MACRO2=M2,...")
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


def parse_macros(macros_str):
    """ Comma separated macros string to dictionary. """
    macros = dict()
    if macros_str:
        macros_list = macros_str.split(',')
        for macro in macros_list:
            split_macro = macro.split('=')
            macros[split_macro[0]] = split_macro[1]
    return(macros)


def main():
    ''' Main logic '''

    args_pars = argparse.ArgumentParser()
    args_pars.add_argument('REQUEST_FILE', nargs='?')
    args_pars.add_argument('-macros', '-m',
                           help="Macros for request file e.g.: \"SYS=TEST,DEV=D1\"")
    args_pars.add_argument('-dir', '-d',
                           help="Directory for saved files")
    args = args_pars.parse_args()

    # Parse macros string if exists
    macros = parse_macros(args.macros)

    # Application has "cleanlooks style" to have more consistent look on
    # different platforms
    app = QtGui.QApplication(sys.argv)
    app.setStyle("cleanlooks")
    # Set double click interval to avoid multiple action when two clicks are made
    # to quick, and the button is not disabled yet

    # Load an application style
    default_style_path = os.path.dirname(os.path.realpath(__file__))
    default_style_path = os.path.join(default_style_path, "default.qss")
    app.setStyleSheet("file:///" + default_style_path)

    gui = SnapshotGui(args.REQUEST_FILE, macros, args.dir)

    sys.exit(app.exec_())

# Start program here
if __name__ == '__main__':
    main()
