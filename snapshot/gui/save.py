#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import datetime
import os
import time

from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLineEdit, QLabel, QHBoxLayout, QVBoxLayout, QFrame, QGroupBox, QMessageBox, QPushButton, \
    QWidget

from ..core import get_pv_values
from ..ca_core import PvStatus, ActionStatus
from ..parser import save_file_suffix
from .utils import SnapshotKeywordSelectorWidget, DetailedMsgBox


class SnapshotSaveWidget(QWidget):
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
        QWidget.__init__(self, parent, **kw)

        self.common_settings = common_settings
        self.snapshot = snapshot
        self.file_path = None

        # Default saved file name: If req file name is PREFIX.req, then saved
        # file name is: PREFIX_YYMMDD_hhmmss (holds time info)
        # Get the prefix ... use update_name() later

        # Create layout and add GUI elements (input fields, buttons, ...)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(layout)
        min_label_width = 120

        # "Monitor" any name changes (by user, or by other methods)
        filename_layout = QHBoxLayout()
        filename_layout.setSpacing(10)

        file_name_label = QLabel("File name: ", self)
        file_name_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        file_name_label.setMinimumWidth(min_label_width)
        self.file_name_rb = QLabel(self)

        # Create collapsible group with advanced options,
        # then update output file name and finish adding widgets to layout
        self.advanced = SnapshotAdvancedSaveSettings(self.common_settings, self)

        self.name_extension = ''
        self.update_name()

        filename_layout.addWidget(file_name_label)
        filename_layout.addWidget(self.file_name_rb)
        filename_layout.addStretch()

        # Make Save button
        save_layout = QHBoxLayout()
        save_layout.setSpacing(10)
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.start_save)

        save_layout.addWidget(self.save_button)

        # Status widgets
        self.sts_log = self.common_settings["sts_log"]
        self.sts_info = self.common_settings["sts_info"]

        # Add to main layout
        layout.addLayout(filename_layout)
        layout.addWidget(self.advanced)
        layout.addLayout(save_layout)
        layout.addStretch()

    def handle_new_snapshot_instance(self, snapshot):
        self.snapshot = snapshot
        self.update_name()
        self.update_labels()
        self.advanced.labels_input.clear_keywords()
        self.advanced.comment_input.setText('')

    def start_save(self):
        # Update file name and chek if exists. Then disable button for the time
        # of saving. Will be unlocked when save is finished.

        #  Update name with latest timestamp and file prefix.
        self.update_name()

        if self.check_file_name_available():
            self.save_button.setEnabled(False)
            self.sts_log.log_msgs("Save started.", time.time())
            self.sts_info.set_status("Saving ...", 0, "orange")

            labels = self.advanced.labels_input.get_keywords()
            comment = self.advanced.comment_input.text()

            machine_params = self.common_settings['machine_params']
            params = {p: v for p, v in zip(machine_params.keys(),
                                           get_pv_values(machine_params.values()))}

            invalid_params = {p: v for p, v in params.items()
                              if type(v) not in (float, int, str)}
            if invalid_params:
                msg = "Some machine parameters have invalid values " \
                    "(see details). Do you want to save anyway?\n"
                msg_window = DetailedMsgBox(
                    msg, '\n'.join(
                        [f"{p} ({machine_params[p]}) has no value" if v is None
                         else f"{p} ({machine_params[p]}) has unsupported "
                         f"type {type(v)}"
                         for p, v in invalid_params.items()]),
                    "Warning", self)
                reply = msg_window.exec_()
                if reply == QMessageBox.No:
                    self.sts_info.clear_status()
                    return
                for p in invalid_params:
                    params[p] = None

            force = self.common_settings["force"]
            # Start saving process with default "force" flag and notify when finished
            status, pvs_status = self.snapshot.save_pvs(self.file_path,
                                                        force=force,
                                                        labels=labels,
                                                        comment=comment,
                                                        machine_params=params,
                                                        symlink_path=os.path.join(
                                                            self.common_settings["save_dir"],
                                                            self.common_settings["save_file_prefix"] +
                                                            'latest' + save_file_suffix))

            if status == ActionStatus.no_conn:
                # Prompt user and ask if he wants to save in force mode
                msg = "Some PVs are not connected (see details). " \
                    "Do you want to save anyway?\n"

                msg_window = DetailedMsgBox(
                    msg, "\n".join(list(pvs_status.keys())), "Warning", self)
                reply = msg_window.exec_()

                if reply != QMessageBox.No:
                    # Start saving process in forced mode and notify when finished
                    status, pvs_status = self.snapshot.save_pvs(self.file_path,
                                                                force=True,
                                                                labels=labels,
                                                                comment=comment,
                                                                machine_params=params,
                                                                symlink_path=os.path.join(
                                                                    self.common_settings["save_dir"],
                                                                    self.common_settings["save_file_prefix"] +
                                                                    'latest' + save_file_suffix))

                    # finished in forced mode
                    self.save_done(pvs_status, True)
                else:
                    # User rejected saving with unconnected PVs. Not an error state.
                    self.sts_log.log_msgs("Save rejected by user.", time.time())
                    self.sts_info.clear_status()
                    self.save_button.setEnabled(True)

            elif status == ActionStatus.ok:
                # Save done in "default force mode"
                self.save_done(pvs_status, force)

            elif status == ActionStatus.os_error:
                msg = f"Could not write to file {self.file_path}."
                QMessageBox.warning(self, "Warning", msg,
                                    QMessageBox.Ok, QMessageBox.NoButton)

            else:
                msg = f"Error occurred with code {status}."
                QMessageBox.warning(self, "Warning", msg,
                                    QMessageBox.Ok, QMessageBox.NoButton)

        else:
            # User rejected saving into existing file.
            # Not an error state.
            self.sts_info.clear_status()

    def save_done(self, status, forced):
        # Enable save button, and update status widgets
        success = True
        msgs = list()
        msg_times = list()
        status_txt = ""
        status_background = ""
        for pvname, sts in status.items():
            if sts != PvStatus.ok:
                if sts == PvStatus.access_err:
                    # if here and not in force mode, then this is error state
                    success = success and not forced
                    msgs.append("WARNING: {}: Not saved (no connection or no read access)".format(pvname))
                else:
                    success = False
                    msgs.append("WARNING: {}: Not saved, error status {}."
                                .format(pvname, sts))
                msg_times.append(time.time())
                status_txt = "Save error"
                status_background = "#F06464"
        self.sts_log.log_msgs(msgs, msg_times)

        if success:
            self.sts_log.log_msgs("Save finished.", time.time())
            status_txt = "Save done"
            status_background = "#64C864"

        self.save_button.setEnabled(True)

        if status_txt:
            self.sts_info.set_status(status_txt, 3000, status_background)

        self.saved.emit()

    def update_name(self):
        name_extension_rb = "{TIMESTAMP}" + save_file_suffix
        self.name_extension = datetime.datetime.fromtimestamp(
            time.time()).strftime('%Y%m%d_%H%M%S')

        self.common_settings["save_file_prefix"] = os.path.split(
            self.common_settings["req_file_path"])[1].split(".")[0] + "_"

        self.file_path = os.path.join(self.common_settings["save_dir"],
                                      self.common_settings["save_file_prefix"]
                                      + self.name_extension + save_file_suffix)
        self.file_name_rb.setText(self.common_settings["save_file_prefix"]
                                  + name_extension_rb)

    def check_file_name_available(self):
        # If file exists, user must decide whether to overwrite it or not
        if os.path.exists(self.file_path):
            msg = "File already exists. Do you want to overwrite it?\n" + \
                  self.file_path
            reply = QMessageBox.question(self, 'Message', msg,
                                               QMessageBox.Yes,
                                               QMessageBox.No)

            if reply == QMessageBox.No:
                return False
        return True

    def update_labels(self):
        self.advanced.update_labels()


class SnapshotAdvancedSaveSettings(QWidget):
    def __init__(self, common_settings, parent=None):
        super().__init__(parent)

        min_label_width = 120

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Make a field to enable user adding a comment
        comment_layout = QHBoxLayout()
        comment_layout.setSpacing(10)
        comment_label = QLabel("Comment:")
        comment_label.setStyleSheet("background-color: None")
        comment_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        comment_label.setMinimumWidth(min_label_width)
        self.comment_input = QLineEdit()
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Make field for labels
        labels_layout = QHBoxLayout()
        labels_layout.setSpacing(10)
        labels_label = QLabel("Labels:")
        labels_label.setStyleSheet("background-color: None")
        labels_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        labels_label.setMinimumWidth(min_label_width)
        # If default labels are defined, then force default labels
        self.labels_input = SnapshotKeywordSelectorWidget(common_settings,
                                                          defaults_only=common_settings['force_default_labels'],
                                                          parent=self)
        labels_layout.addWidget(labels_label)
        labels_layout.addWidget(self.labels_input)

        layout.addLayout(comment_layout)
        layout.addLayout(labels_layout)

    def update_labels(self):
        self.labels_input.update_suggested_keywords()
