#!/usr/bin/env python
import sys
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import pyqtSlot, Qt, SIGNAL
import time
import datetime
import argparse
import re
from enum import Enum

from .snapshot_ca import *

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


class SnapshotStatusLog(QtGui.QPlainTextEdit):
    def log_line(self, text):
        time_stamp = "[" + datetime.datetime.fromtimestamp(
                time.time()).strftime('%H:%M:%S.%f') + "] "
        self.insertPlainText(time_stamp + text + "\n")
        self.ensureCursorVisible()


class SnapshotGui(QtGui.QWidget):

    '''
    Main GUI class for Snapshot application. It needs separate working
    thread where core of the application is running
    '''

    def __init__(self, worker, req_file_name=None, req_file_macros=None,
                 save_dir=None, save_file_dft=None, mode=None, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.worker = worker
        self.setMinimumSize(1100, 900)

        # common_settings is a dictionary which holds common configuration of
        # the application (such as directory with save files, request file
        # path, etc). It is propagated to other snapshot widgets if needed

        self.configure_dialog = SnapshotConfigureDialog(self)
        self.configure_dialog.accepted.connect(self.set_request_file)
        self.configure_dialog.rejected.connect(self.close)

        self.common_settings = dict()
        if not req_file_name:
            self.hide()
            self.configure_dialog.exec()

        else:
            self.common_settings["req_file_name"] = req_file_name
            self.common_settings["req_file_macros"] = req_file_macros

        if not save_dir:
            # Set current dir as save dir
            save_dir = os.path.dirname(os.path.realpath(__file__))

        self.common_settings["save_dir"] = save_dir
        self.common_settings["save_file_dft"] = save_file_dft

        self.common_settings["pvs_to_restore"] = list()

        # Before first interaction with the worker object list all signals
        # on which action must be taken
        self.connect(self.worker, SIGNAL("save_done(PyQt_PyObject)"),
                     self.save_done)
        self.connect(self.worker, SIGNAL("new_snapshot_loaded(PyQt_PyObject)"),
                     self.handle_new_snapshot)

        # Before creating GUI, snapshot must be initialized. This must be
        # blocking operation. Cannot proceed without snapshot instance.
        QtCore.QMetaObject.invokeMethod(self.worker, "init_snapshot",
                                        Qt.BlockingQueuedConnection,
                                        QtCore.Q_ARG(
                                            str, self.common_settings["req_file_name"]),
                                        QtCore.Q_ARG(dict, self.common_settings["req_file_macros"]))

        # Create snapshot GUI:
        # Snapshot gui consists of two tabs: "Save" and "Restore" default
        # is selected depending on mode parameter TODO
        main_layout = QtGui.QVBoxLayout(self)
        self.setLayout(main_layout)

        # Log widget
        separator = QtGui.QFrame(self)
        separator.setFrameShape(QtGui.QFrame.HLine)
        sts_log = SnapshotStatusLog(self)
        sts_log.setMaximumHeight(100)
        sts_log.setReadOnly(True)
        self.common_settings["sts_log"] = sts_log
        tabs = QtGui.QTabWidget(self)

        # Each tab has it's own widget. Need one for save and one for restore.
        self.save_widget = SnapshotSaveWidget(self.worker,
                                              self.common_settings, tabs)
        self.restore_widget = SnapshotRestoreWidget(self.worker,
                                                    self.common_settings, tabs)

        tabs.addTab(self.save_widget, "Save")
        tabs.addTab(self.restore_widget, "Restore")

        # Compare widget ("separator" line before)
        self.compare_widget = SnapshotCompareWidget(self.worker,
                                                    self.common_settings, self)


        # Add to main layout
        main_layout.addWidget(tabs)
        main_layout.addWidget(self.compare_widget)
        main_layout.addWidget(separator)
        main_layout.addWidget(sts_log)

        # Show GUI and manage window properties
        self.show()
        self.setWindowTitle('Snapshot')

    def make_file_list(self, file_list):
        # Just pass data to Restore widget
        self.restore_widget.make_file_list(file_list)

    def save_done(self, status):
        # When save is done, save widget is updated by itself
        # Update restore widget (new file in directory)
        self.restore_widget.start_file_list_update()

    def handle_new_snapshot(self, pvs_names_list):
        # This function should do anything that is needed when new worker
        # creates new instance of snapshot

        # Store pv names list to common settings and call all widgets that need to
        # be updated
        self.common_settings["pvs_to_restore"] = pvs_names_list
        self.compare_widget.create_compare_list()
        self.compare_widget.create_compare_list()

    def set_request_file(self):
        self.common_settings["req_file_name"] = self.configure_dialog.file_path
        self.common_settings["req_file_macros"] = self.configure_dialog.macros


class SnapshotSaveWidget(QtGui.QWidget):

    '''
    Save widget is a widget that enables user to save current state of PVs
    listed in request file. Widget includes:
    Save widget consists of:
     - input-fields:
        * file extension (default YYMMDD_hhmm)
        * comment
        * keywords
     - read-back showing whole file name
     - Save button

    Data about current app state (such as request file) must be provided as
    part of the structure "common_settings".

    '''

    def __init__(self, worker, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.common_settings = common_settings
        self.worker = worker

        # Default saved file name: If req file name is PREFIX.req, then saved
        # file name is: PREFIX_YYMMDD_hhmmss (holds time info)
        # Get the prefix ... use update_name() later
        self.save_file_sufix = ".snap"
        self.name_base = os.path.split(
            common_settings["req_file_name"])[1].split(".")[0] + "_"

        # Before creating elements that can use worker to signals from working
        # thread that are response of this widget actions. If this widget must
        # be updated by other widget actions, catch appropriate signals outside
        # and call methods from outside.
        #
        # * "save_done" is response of the worker when save is finished. Returns
        #   (file_path, status).
        self.connect(self.worker, SIGNAL("save_done(PyQt_PyObject)"),
                     self.save_done)

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
        # Monitor any changes (by user, or by other methods)
        self.extension_input.textChanged.connect(self.update_name)
        file_name_label = QtGui.QLabel("File name: ", self)
        self.file_name_rb = QtGui.QLabel(self)
        self.file_name_rb.setMinimumWidth(300)
        # Get first time stamp name
        self.update_name()
        self.extension_input.setText(self.name_extension)
        extension_layout.addWidget(extension_label)
        extension_layout.addWidget(self.extension_input)
        extension_layout.addWidget(file_name_label)
        extension_layout.addWidget(self.file_name_rb)

        # Make a field to enable user adding a comment
        comment_layout = QtGui.QHBoxLayout()
        comment_layout.setSpacing(10)
        comment_label = QtGui.QLabel("Comment:", self)
        comment_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        comment_label.setMinimumWidth(min_label_width)
        self.comment_input = QtGui.QLineEdit(self)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Make field for keywords
        keyword_layout = QtGui.QHBoxLayout()
        keyword_layout.setSpacing(10)
        keyword_label = QtGui.QLabel("Keywords:", self)
        keyword_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        keyword_label.setMinimumWidth(min_label_width)
        self.keyword_input = QtGui.QLineEdit(self)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)

        # Make Save button, status indicator and save report
        save_layout = QtGui.QHBoxLayout()
        save_layout.setSpacing(10)
        self.save_button = QtGui.QPushButton("Save", self)
        self.save_button.clicked.connect(self.start_save)
        self.save_sts = QtGui.QLabel(self)

        self.save_sts.setMaximumWidth(200)
        self.save_sts.setMaximumHeight(30)
        self.save_sts.setMargin(5)
        self.save_sts.setStyleSheet("background-color : white")
        save_layout.addWidget(self.save_button)
        save_layout.addWidget(self.save_sts)

        # Full status report ("error log")
        self.sts_log = self.common_settings["sts_log"]
        # Add to main layout
        layout.addItem(extension_layout)
        layout.addItem(comment_layout)
        layout.addItem(keyword_layout)
        layout.addStretch()
        layout.addItem(save_layout)

    def start_save(self):
        # Update file name and chek if exists. Then disable button for the time
        #of saving. Will be unlocked when save is finished.
        if not self.extension_input.text():
            #  Update name with latest timestamp
            self.update_name()
        save = self.check_file_existance()
        if save:
            self.save_button.setEnabled(False)
            self.sts_log.log_line("Save started.")
            self.save_sts.setText("Saving ...")
            self.save_sts.setStyleSheet("background-color : orange")
            QtCore.QMetaObject.invokeMethod(self.worker, "save_pvs",
                                            Qt.QueuedConnection,
                                            QtCore.Q_ARG(str, self.file_path),
                                            QtCore.Q_ARG(
                                                str, self.keyword_input.text()),
                                            QtCore.Q_ARG(str, self.comment_input.text()))
        else:
            self.save_sts.setText("")
            self.save_sts.setStyleSheet("background-color : white") 

    def save_done(self, status):
        # Enable saving
        self.save_button.setEnabled(True)
        self.save_sts.setText("Save done")
        self.save_sts.setStyleSheet("background-color : #64C864")

        for key in status:
            sts = status[key]
            if status[key] == PvStatus.access_err:
                self.sts_log.log_line("ERROR: " + key + \
                    ": Not saved (no connection or no read access)")

                self.save_sts.setText("Error during save.")
                self.save_sts.setStyleSheet("background-color : #F06464")

        self.sts_log.log_line("Save done.")

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
            msg = "File already exists.Do you want to override it?\n" + \
                  self.file_path
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)

            if reply == QtGui.QMessageBox.No:
                return False
        return True


class SnapshotRestoreWidget(QtGui.QWidget):

    '''
    restore widget is a widget that enables user to restore saved state of PVs
    listed in request file from one of the saved files.
    Save widget consists of:
     - file selector (tree of all files)
     - restore button
     TODO add meta data searcher/filter

    It also owns a compare widget.

    Data about current app state (such as request file) must be provided as
    part of the structure "common_settings".

    '''

    def __init__(self, worker, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.worker = worker
        self.common_settings = common_settings
        # dict of available files to avoid multiple openings of one file when
        # not needed. It is shared with worker thread (currently only for
        # reading)
        self.file_list = dict()

        # Before creating elements that can use worker, connect to signals from
        # working thread that are response of this widget actions. If this
        # widget must be updated by other widget actions, catch appropriate
        # signals outside and call methods from outside.
        #
        # * "restore_done" is response of the worker when restore is finished.
        #   Returns (file_path, status)
        # * "save_files_loaded" response of the worker when file parsing done.
        #   Returns (file_list)
        self.connect(self.worker, SIGNAL("restore_done(PyQt_PyObject)"),
                     self.restore_done)
        self.connect(self.worker, SIGNAL("save_files_loaded(PyQt_PyObject)"),
                     self.update_file_list_selector)

        # Create main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Filter widgets
        # Filter handling
        self.file_filter = dict()
        self.file_filter["time"] = list()  # star and end date
        self.file_filter["keys"] = list()
        self.file_filter["comment"] = ""

        self.filter_input = SnapshotFileFilterWidget(self)
        self.connect(self.filter_input, SIGNAL(
            "file_filter_updated"), self.filter_file_list_selector)

        self.filter_file_list_selector()

        # Make restore button, status indicator and restore report
        restore_layout_main = QtGui.QVBoxLayout()

        # Create list with: file names, keywords, comments
        self.file_selector = QtGui.QTreeWidget(self)
        self.file_selector.setIndentation(0)
        self.file_selector.setStyleSheet("QTreeWidget::item:pressed,QTreeWidget::item:selected{background-color:#FF6347;color:#FFFFFF}‌​")
        self.file_selector.setColumnCount(3)
        self.file_selector.setHeaderLabels(["File", "Keywords", "Comment"])
        self.file_selector.header().resizeSection(0, 300)
        self.file_selector.header().resizeSection(1, 300)
        self.file_selector.setAlternatingRowColors(True)
        self.file_selector.itemSelectionChanged.connect(self.choose_file)

        # Button with short status
        restore_layout = QtGui.QHBoxLayout()
        restore_layout.setSpacing(10)
        self.restore_button = QtGui.QPushButton("Restore", self)
        self.restore_button.clicked.connect(self.start_restore)
        self.restore_sts = QtGui.QLabel(self)
        self.restore_sts.setMaximumWidth(200)
        self.restore_sts.setMaximumHeight(30)
        self.restore_sts.setMargin(5)
        self.restore_sts.setStyleSheet("background-color : white")
        restore_layout.addWidget(self.restore_button)
        restore_layout.addWidget(self.restore_sts)
        # Full status report ("error log")
        self.sts_log = self.common_settings["sts_log"]

        restore_layout_main.addWidget(self.file_selector)
        restore_layout_main.addItem(restore_layout)

        # Create file list for first time (this is done  by worker)
        self.start_file_list_update()

        # Add all widgets to main layout
        layout.addWidget(self.filter_input)
        layout.addItem(restore_layout_main)

    def start_restore(self):
        # First disable restore button (will be enabled when finished)
        # Then Use one of the preloaded saved files to restore
        self.restore_button.setEnabled(False)
        self.sts_log.log_line("Restore started.")
        self.restore_sts.setText("Restoring ...")
        self.restore_sts.setStyleSheet("background-color : orange")

        QtCore.QMetaObject.invokeMethod(self.worker,
                                        "restore_pvs",
                                        Qt.QueuedConnection)

    def restore_done(self, status):
        # Enable button when restore is finished (worker notifies)
        self.restore_button.setEnabled(True)
        self.restore_sts.setText("Restore done")
        self.restore_sts.setStyleSheet("background-color : #64C864")

        if not status:
            self.sts_log.log_line("ERROR: No file selected.")
            self.restore_sts.setText("Cannot restore")
            self.restore_sts.setStyleSheet("background-color : #F06464")
        else:
            for key in status:
                sts = status[key]
                if status[key] == PvStatus.access_err:
                    self.sts_log.log_line("ERROR: " + key + \
                        ": Not restored (no connection or readonly)")

                    self.restore_sts.setText("Error during restore.")
                    self.restore_sts.setStyleSheet(
                        "background-color : #F06464")
        self.sts_log.log_line("Restore done.")

    def start_file_list_update(self):
        # Rescans directory and adds new/modified files and removes none
        # existing ones from the list.

        # set prefix of the files (do outside invokeMethod because looks less
        # ugly :D)
        file_prefix = os.path.split(
            self.common_settings["req_file_name"])[1].split(".")[0] + "_"

        QtCore.QMetaObject.invokeMethod(self.worker, "get_save_files",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(str, self.common_settings["save_dir"]),
                                        QtCore.Q_ARG(str, file_prefix),
                                        QtCore.Q_ARG(dict, self.file_list))

        self.filter_file_list_selector()

    def choose_file(self):
        pvs = self.file_list[
            self.file_selector.selectedItems()[0].text(0)]["pvs_list"]
        QtCore.QMetaObject.invokeMethod(self.worker,
                                        "load_pvs_to_snapshot",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(dict, pvs))

    def update_file_list_selector(self, file_list):
        for key in file_list:
            meta_data = file_list[key]["meta_data"]
            keywords = meta_data.get("keywords", "")
            comment = meta_data.get("comment", "")

            # check if already on list (was just modified) and modify file
            # selector
            if key not in self.file_list:
                selector_item = QtGui.QTreeWidgetItem([key, keywords, comment])
                self.file_selector.addTopLevelItem(selector_item)
                self.file_list[key] = file_list[key]
                self.file_list[key]["file_selector"] = selector_item
            else:
                # If everything ok only one file should exist in list
                to_modify = self.file_list[key]["file_selector"]
                to_modify.setText(1, keywords)
                to_modify.setText(2, comment)

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
                time_filter = file_filter.get("time")
                keys_filter = file_filter.get("keys")
                comment_filter = file_filter.get("comment")

                if time_filter is not None:
                    # valid names are all between this two dates
                    # convert file name back to date and check if between
                    modif_time = file_to_filter["meta_data"]["save_time"]
                    if time_filter[0] is not None:
                        time_status = (modif_time >= time_filter[0])
                    else:
                        time_status = True

                    if time_filter[1] is not None:
                        time_status = time_status and (
                            modif_time <= time_filter[1])
                else:
                    time_status = True

                if keys_filter:
                    # get file keys as list
                    keywords = file_to_filter[
                        "meta_data"]["keywords"].split(',')
                    keys_status = False

                    for key in keywords:
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

                # Set visibility if any of the filters conditions met
                file_line.setHidden(
                    not(time_status and keys_status and comment_status))


class SnapshotFileFilterWidget(QtGui.QWidget):

    '''
        Is a widget with 3 filter options:
            - by time
            - by keywords
            - by name

        Emits signal: filter_changed when any of the filter changed.
    '''

    def __init__(self, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        # Create main layout
        layout = QtGui.QHBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Create filter selectors (with readbacks)
        # - date selector
        # - check_boxes for keywords
        # - text input to filter comments

        # date selector
        date_layout = QtGui.QHBoxLayout()
        date_layout.setMargin(0)
        date_layout.setSpacing(10)

        from_label = QtGui.QLabel("From:", self)
        self.date_from = SnapshotDateSelector(self)
        to_label = QtGui.QLabel("To:", self)
        self.date_to = SnapshotDateSelector(self, day_end=True)

        date_layout.addWidget(from_label)
        date_layout.addWidget(self.date_from)
        date_layout.addWidget(to_label)
        date_layout.addWidget(self.date_to)

        # Init filters
        self.file_filter = dict()
        self.file_filter["time"] = [
            self.date_from.selected_date, self.date_to.selected_date]
        self.file_filter["keys"] = list()
        self.file_filter["comment"] = ""

        # Connect after file_filter exist
        self.connect(
            self.date_from, SIGNAL("date_updated"), self.update_filter)
        self.connect(self.date_to, SIGNAL("date_updated"), self.update_filter)

        # Key filter
        key_layout = QtGui.QHBoxLayout()
        key_label = QtGui.QLabel("Keywords:", self)
        self.keys_input = QtGui.QLineEdit(self)
        self.keys_input.setPlaceholderText("key1,key2,...")
        self.keys_input.textChanged.connect(self.update_filter)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.keys_input)

        # Comment filter
        comment_layout = QtGui.QHBoxLayout()
        comment_label = QtGui.QLabel("Comment:", self)
        self.comment_input = QtGui.QLineEdit(self)
        self.comment_input.setPlaceholderText("Filter")
        self.comment_input.textChanged.connect(self.update_filter)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Add to main layout
        layout.addItem(date_layout)
        layout.addItem(key_layout)
        layout.addItem(comment_layout)

    def update_filter(self):
        self.file_filter["time"] = [
            self.date_from.selected_date, self.date_to.selected_date]
        if self.keys_input.text().strip(''):
            self.file_filter["keys"] = self.keys_input.text().strip('').split(',')
        else:
            self.file_filter["keys"] = list()
        self.file_filter["comment"] = self.comment_input.text().strip('')

        self.emit(SIGNAL("file_filter_updated"))


# PV Compare part
class SnapshotCompareWidget(QtGui.QWidget):

    '''

    Widget for live comparing pv values. All infos about PVs that needs to be
    monitored are already in the "snapshot" object controlled by worker. They
    were loaded with

    '''

    def __init__(self, worker, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.worker = worker
        self.common_settings = common_settings

        # Before creating elements that can use worker to signals from working
        # thread that are response of this widget actions. If this widget must
        # be updated by other widget actions, catch appropriate signals outside
        # and call methods from outside.
        self.connect(self.worker, SIGNAL("pv_changed(PyQt_PyObject)"),
                     self.update_pv)

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
        self.pv_view.setColumnCount(4)
        self.pv_view.setHeaderLabels(
            ["PV", "Current value", "Saved value", "Status"])
        self.pv_view.header().resizeSection(0, 400)
        self.pv_view.header().resizeSection(1, 200)
        self.pv_view.header().resizeSection(2, 100)
        self.pv_view.setAlternatingRowColors(True)

        # Add all widgets to main layout
        # TODO add filter selector widget
        layout.addItem(filter_layout)
        layout.addWidget(self.pv_view)

        # fill the compare view and start comparing
        self.create_compare_list()
        self.start_compare()

        # Disable possibility to select item in the compare list
        self.pv_view.setSelectionMode(QtGui.QAbstractItemView.NoSelection)
        self.pv_view.setFocusPolicy(Qt.NoFocus)

    def create_compare_list(self):
        '''
        Create tree item for each PV. List of pv names was returned after
        parsing the request file. Attributes except PV name are empty at
        init. Will be updated when monitor happens, snapshot object will
        raise a callback which is then catched in worker and passed with
        signal. TODO which function handles.
        '''

        # First remove all existing entries
        while self.pv_view.topLevelItemCount() > 0:
            self.pv_view.takeTopLevelItem(0)

        for pv_name in self.common_settings["pvs_to_restore"]:
            saved_val = ""
            status = ""
            curr_val = ""
            pv_line = SnapshotCompareTreeWidgetItem(pv_name, self.pv_view)
            self.pv_view.addTopLevelItem(pv_line)
        # Sort by name (alphabetical order)
        self.pv_view.sortItems(0, Qt.AscendingOrder)

    def filter_list(self):
        # Just pass the filter conditions to all items in the list. # Use
        # values directly from GUI elements (filter selectors).
        for i in range(self.pv_view.topLevelItemCount()):
            curr_item = self.pv_view.topLevelItem(i)
            curr_item.apply_filter(self.compare_filter_inp.currentIndex(),
                                   self.completnes_filter_inp.isChecked(),
                                   self.pv_filter_inp.text())

    def start_compare(self):
        # Just invoke worker, to set snapshot sending a callbacks
        QtCore.QMetaObject.invokeMethod(self.worker, "start_continous_compare",
                                        Qt.QueuedConnection)

    def update_pv(self, data):
        # If everything ok, only one line should match
        line_to_update = self.pv_view.findItems(
            data["pv_name"], Qt.MatchCaseSensitive, 0)[0]

        line_to_update.update_state(**data)


class SnapshotCompareTreeWidgetItem(QtGui.QTreeWidgetItem):

    '''
    Extended to hold last info about connection status and value. Also
    implements methods to set visibility according to filter
    '''

    def __init__(self, pv_name, parent=None):
        # Item with [pv_name, current_value, saved_value, status]
        QtGui.QTreeWidgetItem.__init__(self, parent, [pv_name, "", "", ""])
        self.pv_name = pv_name

        # Have data stored in native types, for easier filtering etc.
        self.connect_sts = None
        self.saved_value = None
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
            if isinstance(self.value, (numpy.ndarray)):
                self.setText(1, json.dumps(self.value.tolist()))
            elif self.value is not None:
                # if string do not dump it will add "" to a string
                if isinstance(self.value, (str)):
                    self.setText(1, self.value)
                else:
                    # dump other values
                    self.setText(1, json.dumps(self.value))
            else:
                self.setText(1, "")

        if not self.saved_sts:
            self.setText(2, "")  # not loaded list of saved PVs means no value
            self.setText(3, "Set of saved PVs not selected!")
            self.has_error = True
        else:
            if isinstance(self.saved_value, (numpy.ndarray)):
                self.setText(2, json.dumps(self.saved_value.tolist()))
            elif self.saved_value is not None:
                # if string do not dump it will add "" to a string
                if isinstance(self.saved_value, (str)):
                    self.setText(2, self.saved_value)
                else:
                    # dump other values
                    self.setText(2, json.dumps(self.saved_value))
            else:
                self.setText(2, "Not Saved")
                self.setText(3, "PV value not saved in this set.")
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
        ''' Controls visibility of item, depending on filter conditions. '''

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
                         (self.compare)) or ((PvCompareFilter(compare_filter) == PvCompareFilter.show_neq) and
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
        print(self.mapToGlobal(self.pos()).x)
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
        self.setWindowTitle("date")
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
        Y = int(datetime.datetime.fromtimestamp(today).strftime('%Y'))
        m = int(datetime.datetime.fromtimestamp(today).strftime('%m'))
        d = int(datetime.datetime.fromtimestamp(today).strftime('%d'))
        self.cal.setSelectedDate(QtCore.QDate(Y, m, d))
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

        return(self.date_valid)

    def apply_date(self):
        if self.date_valid:
            if self.day_end:
                time_str_full = self.date_line.text()+"/23:59:59"
            else:
                time_str_full = self.date_line.text()+"/0:0:0"
            if self.date_line.text():
                self.selected_date = time.mktime(
                    time.strptime(time_str_full, '%d.%m.%Y/%H:%M:%S'))
            else:
                self.selected_date = self.dft_date

            self.emit(SIGNAL("date_selected"))
            self.hide()

    def clear_date(self):
        # To be used from outside
        self.clear_internal()
        self.apply_date()

class SnapshotFileSelector(QtGui.QWidget):

    ''' Widget to select file with dialog box '''

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
        icon = QtGui.QIcon.fromTheme("folder")
        file_path_button.setIcon(icon)
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

    ''' Dialog window to select and apply file'''

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
        button_box.rejected.connect(self.config_rejected)

    def config_accepted(self):
        # Save to file path to local variable and emit signal
        if not self.file_selector.file_path:
            self.file_path = ""
        else:
            self.file_path = self.file_selector.file_path
        if os.path.exists(self.file_path):
            self.macros = parse_macros(self.macros_input.text())
            self.accepted.emit()
            self.close()
        else:
            warn = "File does not exist!"
            warn_window = QtGui.QMessageBox.warning(self, "Warning", warn,
                                                    QtGui.QMessageBox.Ok,
                                                    QtGui.QMessageBox.NoButton)

    def config_rejected(self):
        self.rejected.emit()
        self.close()


class SnapshotWorker(QtCore.QObject):

    '''
    This is a worker object running in separate thread. It holds core of the
    application, snapshot object, so it does all time consuming tasks such as
    saving and restoring, loading files etc.

    Its slots (methods with @pyqtSlot) can be invoked with
    QtCore.QMetaObject.invokeMethod().

    To notify GUI this worker emits following signals
    * new_snapshot(snapshot) --> new snapshot was instantiated
    * save_done(status) --> save was finished
    * restore_done(save_file_path, status) --> restore was finished
    '''

    def __init__(self, parent=None):

        QtCore.QObject.__init__(self, parent)
        # Instance of snapshot will be created with  init_snapshot() so just
        # create a placeholder
        self.snapshot = None

    @pyqtSlot(str, dict)
    def init_snapshot(self, req_file_path, req_macros=None):
        # creates new instance of snapshot loads the request file and emits
        # the signal new_snapshot to update the GUI
        self.snapshot = Snapshot(req_file_path, req_macros)
        pvs_names = self.snapshot.get_pvs_names()
        self.emit(SIGNAL("new_snapshot_loaded(PyQt_PyObject)"), pvs_names)

    @pyqtSlot(str, str, str)
    def save_pvs(self, save_file_path, keywords=None, comment=None):
        # Start saving process and notify when finished
        status = self.snapshot.save_pvs(save_file_path, keywords=keywords,
                                        comment=comment)
        self.emit(
            SIGNAL("save_done(PyQt_PyObject)"), status)

    @pyqtSlot()
    def restore_pvs(self):
        # Just calling snapshot restore.
        status = self.snapshot.restore_pvs()

        self.emit(SIGNAL("restore_done(PyQt_PyObject)"), status)

    @pyqtSlot(dict)
    def load_pvs_to_snapshot(self, saved_pvs):
        # Sets list of pvs to snapshot object

        self.snapshot.prepare_pvs_to_restore_from_list(saved_pvs)
        self.emit(SIGNAL("load_for_restore_done()"))

    @pyqtSlot(str, str, dict)
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
                    parsed_save_files[file_name][
                        "modif_time"] = os.path.getmtime(file_path)

        self.emit(
            SIGNAL("save_files_loaded(PyQt_PyObject)"), parsed_save_files)

    @pyqtSlot()
    def start_continous_compare(self):
        self.snapshot.start_continous_compare(self.process_callbacks)

    @pyqtSlot()
    def stop_continous_compare(self):
        self.snapshot.stop_continous_compare()

    def process_callbacks(self, **kw):
        self.emit(SIGNAL("pv_changed(PyQt_PyObject)"), kw)


def parse_macros(macros_str):
    ''' Comma separated macros string to dictionary'''
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
    args_pars.add_argument('-req', '-r', help='Request file')
    args_pars.add_argument('-macros', '-m',
                           help="Macros for request file e.g.: \"SYS=TEST,DEV=D1\"")
    args_pars.add_argument('-dir', '-d',
                           help="Directory for saved files")
    args = args_pars.parse_args()

    # Parse macros string if exists
    macros = parse_macros(args.macros)

    # Create application which consists of two threads. "gui" runs in main
    # GUI thread. Time consuming functions are executed in worker thread.
    app = QtGui.QApplication(sys.argv)
    worker = SnapshotWorker()  # this is working object manipulating snapshot
    worker_thread = QtCore.QThread()
    worker.moveToThread(worker_thread)
    worker_thread.start()

    gui = SnapshotGui(worker, args.req, macros, args.dir)

    sys.exit(app.exec_())

# Start program here
if __name__ == '__main__':
    main()
