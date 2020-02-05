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

from ..ca_core import PvStatus, ActionStatus
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
        self.save_file_sufix = ".snap"

        # Create layout and add GUI elements (input fields, buttons, ...)
        layout = QVBoxLayout(self)
        # layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)
        min_label_width = 120

        # Make a field to select file extension (has a read-back)
        extension_layout = QHBoxLayout()
        extension_layout.setSpacing(10)
        extension_label = QLabel("Name extension:", self)
        extension_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        extension_label.setMinimumWidth(min_label_width)
        self.extension_input = QLineEdit(self)
        extension_layout.addWidget(extension_label)
        extension_layout.addWidget(self.extension_input)

        # "Monitor" any name changes (by user, or by other methods)
        extension_rb_layout = QHBoxLayout()
        extension_rb_layout.setSpacing(10)
        self.extension_input.textChanged.connect(self.update_name)

        file_name_label = QLabel("File name: ", self)
        file_name_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        file_name_label.setMinimumWidth(min_label_width)
        self.file_name_rb = QLabel(self)

        # Create collapsible group with advanced options,
        # then update output file name and finish adding widgets to layout
        self.advanced = SnapshotAdvancedSaveSettings("Advanced", self.common_settings, self)

        self.name_extension = ''
        self.update_name()

        extension_rb_layout.addWidget(file_name_label)
        extension_rb_layout.addWidget(self.file_name_rb)
        extension_rb_layout.addStretch()

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
        # Update file name and chek if exists. Then disable button for the time
        # of saving. Will be unlocked when save is finished.

        #  Update name with latest timestamp and file prefix.
        self.update_name()

        if self.check_file_name_available():
            self.save_button.setEnabled(False)
            self.sts_log.log_msgs("Save started.", time.time())
            self.sts_info.set_status("Saving ...", 0, "orange")

            # Use advanced settings only if selected
            if self.advanced.isChecked():
                labels = self.advanced.labels_input.get_keywords()
                comment = self.advanced.comment_input.text()
            else:
                labels = list()
                comment = ""

            force = self.common_settings["force"]
            # Start saving process with default "force" flag and notify when finished
            status, pvs_status = self.snapshot.save_pvs(self.file_path,
                                                        force=force,
                                                        labels=labels,
                                                        comment=comment,
                                                        symlink_path=os.path.join(
                                                            self.common_settings["save_dir"],
                                                            self.common_settings["save_file_prefix"] +
                                                            'latest' + self.save_file_sufix))

            if status == ActionStatus.no_conn:
                # Prompt user and ask if he wants to save in force mode
                msg = "Some PVs are not connected (see details). Do you want to save anyway?\n"

                msg_window = DetailedMsgBox(msg, "\n".join(list(pvs_status.keys())), "Warning", self)
                reply = msg_window.exec_()

                if reply != QMessageBox.No:
                    # Start saving process in forced mode and notify when finished
                    status, pvs_status = self.snapshot.save_pvs(self.file_path,
                                                                force=True,
                                                                labels=labels,
                                                                comment=comment,
                                                                symlink_path=os.path.join(
                                                                    self.common_settings["save_dir"],
                                                                    self.common_settings["save_file_prefix"] +
                                                                    'latest' + self.save_file_sufix))

                    # finished in forced mode
                    self.save_done(pvs_status, True)
                else:
                    # User rejected saving with unconnected PVs. Not an error state.
                    self.sts_log.log_msgs("Save rejected by user.", time.time())
                    self.sts_info.clear_status()
                    self.save_button.setEnabled(True)

            else:
                # Save done in "default force mode"
                self.save_done(pvs_status, force)

        else:
            # User rejected saving into existing file.
            # Not an error state.
            self.sts_info.clear_status()

    def save_done(self, status, forced):
        # Enable save button, and update status widgets
        error = False
        msgs = list()
        msg_times = list()
        status_txt = ""
        status_background = ""
        for pvname, sts in status.items():
            if sts == PvStatus.access_err:
                error = not forced  # if here and not in force mode, then this is error state
                msgs.append("WARNING: {}: Not saved (no connection or no read access)".format(pvname))
                msg_times.append(time.time())
                status_txt = "Save error"
                status_background = "#F06464"
        self.sts_log.log_msgs(msgs, msg_times)

        if not error:
            self.sts_log.log_msgs("Save finished.", time.time())
            status_txt = "Save done"
            status_background = "#64C864"

        self.save_button.setEnabled(True)

        if status_txt:
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


class SnapshotAdvancedSaveSettings(QGroupBox):
    def __init__(self, text, common_settings, parent=None):
        self.parent = parent

        QGroupBox.__init__(self, text, parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 15)")
        min_label_width = 120
        # frame is a container with all widgets, tat should be collapsed
        self.frame = QFrame(self)
        self.frame.setContentsMargins(0, 20, 0, 0)
        self.frame.setStyleSheet("background-color: None")
        self.setCheckable(True)
        self.frame.setVisible(False)
        self.setChecked(False)
        self.toggled.connect(self.toggle)

        layout = QVBoxLayout()
        # layout.setMargin(0)
        layout.addWidget(self.frame)
        self.setLayout(layout)

        self.frame_layout = QVBoxLayout()
        # self.frame_layout.setMargin(0)
        self.frame.setLayout(self.frame_layout)

        # Make a field to enable user adding a comment
        comment_layout = QHBoxLayout()
        comment_layout.setSpacing(10)
        comment_label = QLabel("Comment:", self.frame)
        comment_label.setStyleSheet("background-color: None")
        comment_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        comment_label.setMinimumWidth(min_label_width)
        self.comment_input = QLineEdit(self.frame)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Make field for labels
        labels_layout = QHBoxLayout()
        labels_layout.setSpacing(10)
        labels_label = QLabel("Labels:", self.frame)
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
        file_prefix_layout = QHBoxLayout()
        file_prefix_layout.setSpacing(10)
        file_prefix_label = QLabel("File name prefix:", self.frame)
        file_prefix_label.setStyleSheet("background-color: None")
        file_prefix_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        file_prefix_label.setMinimumWidth(min_label_width)
        self.file_prefix_input = QLineEdit(self.frame)
        file_prefix_layout.addWidget(file_prefix_label)
        file_prefix_layout.addWidget(self.file_prefix_input)
        self.file_prefix_input.textChanged.connect(
            self.parent.update_name)

        # self.frame_layout.addStretch()
        self.frame_layout.addLayout(comment_layout)
        self.frame_layout.addLayout(labels_layout)
        self.frame_layout.addLayout(file_prefix_layout)

    def update_labels(self):
        self.labels_input.update_suggested_keywords()

    def toggle(self):
        self.frame.setVisible(self.isChecked())
        self.parent.update_name()
