import sys
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import pyqtSlot, Qt, SIGNAL
import time
import datetime
import argparse

from snapshot import *

# close with ctrl+C
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)


class SnapshotGui(QtGui.QWidget):

    '''
    Main GUI class for Snapshot application. It needs separate working
    thread where core of the application is running
    '''

    def __init__(self, worker, req_file_name, req_file_macros=None,
                 save_dir=None, save_file_dft=None, mode=None, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.worker = worker
        self.parsed_save_files = dict()
        self.setMinimumSize(900, 500)

        # common_settings is a dictionary which holds common configuration of
        # the application (such as directory with save files, request file
        # path, etc). It is propagated to other snapshot widgets if needed

        self.common_settings = dict()
        self.common_settings["req_file_name"] = req_file_name
        self.common_settings["req_file_macros"] = req_file_macros
        if not save_dir:
            # Set current dir as save dir
            save_dir = os.path.dirname(os.path.realpath(__file__))

        self.common_settings["save_dir"] = save_dir
        self.common_settings["save_file_dft"] = save_file_dft

        # Before first interaction with the worker object list all signals
        # on which action must be taken
        self.connect(self.worker, SIGNAL("save_done(PyQt_PyObject,PyQt_PyObject)"),
                     self.save_done)
        self.connect(self.worker, SIGNAL("restore_done(PyQt_PyObject,PyQt_PyObject)"),
                     self.restore_done)

        # Before creating GUI, snapshot must be initialized. This must be
        # blocking operation. Cannot proceed without snapshot instance.
        QtCore.QMetaObject.invokeMethod(self.worker, "init_snapshot",
                                Qt.BlockingQueuedConnection,
                                QtCore.Q_ARG(str, self.common_settings["req_file_name"]),
                                QtCore.Q_ARG(dict, self.common_settings["req_file_macros"]))

        # Create snapshot GUI:
        # Snapshot gui consists of two tabs: "Save" and "Restore" default
        # is selected depending on mode parameter TODO
        main_layout = QtGui.QVBoxLayout(self)
        self.setLayout(main_layout)
        tabs = QtGui.QTabWidget(self)
        tabs.setMinimumSize(900, 450)

        # Each tab has it's own widget. Need one for save and one for restore.
        self.save_widget = SnapshotSaveWidget(self.worker,
                                              self.common_settings, tabs)
        self.restore_widget = SnapshotRestoreWidget(self.worker,
                                                    self.common_settings, tabs)

        tabs.addTab(self.save_widget, "Save")
        tabs.addTab(self.restore_widget, "Restore")

        # Show GUI and manage window properties
        self.show()
        self.setWindowTitle('Snapshot')

    def make_file_list(self, file_list):
        # Just pass data to Restore widget
        print(id(file_list))
        self.restore_widget.make_file_list(file_list)

    def save_done(self, file_path, status):
        # TODO report status, update restore widget with new file
        print("Save done")

    def restore_done(self, restored_pvs, status):
        # TODO report status
        print("Restore done")


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
        # file name is: PREFIX_YYMMDD_hhmm (holds time info)
        self.name_base = os.path.split(common_settings["req_file_name"])[1].split(".")[0] + "_"
        self.name_extension = datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d_%H%M')

        self.file_path = os.path.join(self.common_settings["save_dir"],
                                      self.name_base + self.name_extension)

        # Create layout and add GUI elements (input fields, buttons, ...)
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)
        min_label_width = 120

        # Make a field to select file extension (has a read-back)
        extension_layout = QtGui.QHBoxLayout(self)
        extension_layout.setSpacing(10)
        extension_label = QtGui.QLabel("Name extension:", self)
        extension_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        extension_label.setMinimumWidth(min_label_width)
        self.extension_input = QtGui.QLineEdit(self)
        # Monitor any changes (by user, problematical)
        self.extension_input.textChanged.connect(self.update_name)
        # Monitor just changes from the user
        self.extension_input.textChanged.connect(self.update_name)
        file_name_label = QtGui.QLabel("File name: ", self)
        self.file_name_rb = QtGui.QLabel(self)
        self.file_name_rb.setMinimumWidth(300)
        self.extension_input.setText(self.name_extension)
        extension_layout.addWidget(extension_label)
        extension_layout.addWidget(self.extension_input)
        extension_layout.addWidget(file_name_label)
        extension_layout.addWidget(self.file_name_rb)

        # Make a field to enable user adding a comment
        comment_layout = QtGui.QHBoxLayout(self)
        comment_layout.setSpacing(10)
        comment_label = QtGui.QLabel("Comment:", self)
        comment_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        comment_label.setMinimumWidth(min_label_width)
        self.comment_input = QtGui.QLineEdit(self)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Make field for keywords
        keyword_layout = QtGui.QHBoxLayout(self)
        keyword_layout.setSpacing(10)
        keyword_label = QtGui.QLabel("Keywords:", self)
        keyword_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)
        keyword_label.setMinimumWidth(min_label_width)
        self.keyword_input = QtGui.QLineEdit(self)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)

        # Make Save button
        self.save_button = QtGui.QPushButton("Save", self)
        self.save_button.clicked.connect(self.start_save)

        layout.addItem(extension_layout)
        layout.addItem(comment_layout)
        layout.addItem(keyword_layout)
        layout.addWidget(self.save_button)

        # Widget properties
        self.setMaximumHeight(180)

        # Connect to signals from working thread that are response of this
        # widget actions. If this widget must be updated by other widget
        # actions, catch appropriate signals outside and call methods from
        # outside.
        #
        # * "save_done" is response of the worker when save is finished. Returns
        #   (file_path, status).
        self.connect(self.worker, SIGNAL("save_done(PyQt_PyObject,PyQt_PyObject)"),
                     self.save_done)

    def start_save(self):
        # Disable button for the time of saving. Will be unlocked when save is
        # finished.
        self.save_button.setEnabled(False)
        QtCore.QMetaObject.invokeMethod(self.worker, "save_pvs",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(str, self.file_path),
                                        QtCore.Q_ARG(str, self.keyword_input.text()),
                                        QtCore.Q_ARG(str, self.comment_input.text()))

    def save_done(self, file_path, status):
        # Enable saving
        self.save_button.setEnabled(True)

    def update_name(self):
        self.file_path = os.path.join(self.common_settings["save_dir"],
                                      self.name_base + self.name_extension)
        self.file_name_rb.setText(self.name_base + self.name_extension)


class SnapshotRestoreWidget(QtGui.QWidget):

    '''
    restore widget is a widget that enables user to restore saved state of PVs
    listed in request file from one of the saved files.
    Save widget consists of:
     - file selector (tree of all files)
     - restore button
     TODO add meta data searcher/filter

    Data about current app state (such as request file) must be provided as
    part of the structure "common_settings".

    '''

    def __init__(self, worker, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)

        self.worker = worker
        self.common_settings = common_settings
        # dict of available files to avoid multiple openings of one file when
        # not needed. It is shared with worker thread. Use mutex to synchronize.
        self.file_list = dict()

        # Create main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Create list with: file names, keywords, comments
        self.file_selector = QtGui.QTreeWidget(self)
        self.file_selector.setColumnCount(3)
        self.file_selector.setHeaderLabels(["File", "Keywords", "Comment"])
        self.file_selector.header().resizeSection(0, 300)
        self.file_selector.header().resizeSection(1, 300)
        self.file_selector.itemSelectionChanged.connect(self.choose_file)

        # Restore button
        self.restore_button = QtGui.QPushButton("Restore", self)
        self.restore_button.clicked.connect(self.start_restore)

        # Add all widgets to main layout
        layout.addWidget(self.file_selector)
        layout.addWidget(self.restore_button)

        # Create file list for first time (this is done  by worker)
        self.update_file_list()

        # Connect to signals from working thread that are response of this
        # widget actions. If this widget must be updated by other widget
        # actions, catch appropriate signals outside and call methods from
        # outside.
        #
        # * "restore_done" is response of the worker when restore is finished.
        #   Returns (file_path, status)
        # * "save_files_loaded" response of the worker when file parsing done.
        #   Returns (file_list)
        self.connect(self.worker, SIGNAL("restore_done(PyQt_PyObject,PyQt_PyObject)"),
                     self.restore_done)
        self.connect(self.worker, SIGNAL("save_files_loaded(PyQt_PyObject)"),
                     self.update_file_selector)

    def start_restore(self):
        # First disable restore button (will be enabled when finished)
        # Then Use one of the preloaded saved files to restore
        self.restore_button.setEnabled(False)
        QtCore.QMetaObject.invokeMethod(self.worker,
                                        "restore_pvs_from_obj",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(dict,
                                                     self.common_settings["pvs_to_restore"]))

    def restore_done(self, restored_pvs, status):
        # Enable button when restore is finished (worker notifies)
        self.restore_button.setEnabled(True)

    def update_file_list(self):
        # Rescans directory and adds new/modified files and removes none
        # existing ones from the list.

        # set prefix of the files (do outside invokeMethod because looks less
        # ugly :D)
        file_prefix = os.path.split(self.common_settings["req_file_name"])[1].split(".")[0] + "_"

        QtCore.QMetaObject.invokeMethod(self.worker, "get_save_files",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(str, self.common_settings["save_dir"]),
                                        QtCore.Q_ARG(str, file_prefix),
                                        QtCore.Q_ARG(dict, self.file_list))

    def choose_file(self):
        pvs = self.file_list[self.file_selector.selectedItems()[0].text(0)]["pvs_list"]
        self.common_settings["pvs_to_restore"] = pvs

    def update_file_selector(self, file_list):
        self.file_list = file_list
        for key in file_list:

            keywords = file_list[key]["meta_data"].get("keywords", "")
            comment = file_list[key]["meta_data"].get("comment", "")
            save_file = QtGui.QTreeWidgetItem([key, keywords, comment])

            self.file_selector.addTopLevelItem(save_file)

        # Sort by file name (alphabetical order)
        self.file_selector.sortItems(0, Qt.AscendingOrder)


class SnapshotFileSelector(QtGui.QWidget):

    ''' Widget to select file with dialog box '''

    def __init__(self, parent=None, label_text="File", button_text="Browse",
                 init_path=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)
        self.setMinimumSize(550, 50)
        self.file_path = init_path

        # Create main layout
        layout = QtGui.QHBoxLayout(self)
        layout.setMargin(0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # Create file dialog box. When file is selected set file path to be
        # shown in input field (can be then edited manually)
        self.req_file_dialog = QtGui.QFileDialog(self)
        self.req_file_dialog.fileSelected.connect(self.set_file_input_text)

        # This widget has 3 parts:
        #   label
        #   input field (when value of input is changed, it is stored locally)
        #   icon button to open file dialog
        label = QtGui.QLabel(label_text, self)
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
        self.file_path = None
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # This Dialog consists of file selector and buttons to apply
        # or cancel the file selection
        self.file_selector = SnapshotFileSelector(self)
        self.setMinimumSize(600, 50)

        layout.addWidget(self.file_selector)

        button_box = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        button_box.accepted.connect(self.config_accepted)
        button_box.rejected.connect(self.config_rejected)

    def config_accepted(self):
        # Save to file path to local variable and emit signal
        self.file_path = self.file_selector.file_path
        self.accepted.emit()
        self.close()

    def config_rejected(self):
        self.rejected.emmit()
        self.close()


class SnapshotWorker(QtCore.QObject):
    '''
    This is a worker object running in separate thread. It holds core of the
    application, snapshot object, so it does all time consuming tasks such as
    saving and restoring, loading files etc.

    Its slots (methods with @pyqtSlot) can be invoked with
    QtCore.QMetaObject.invokeMethod().

    To notify GUI this worker emits following signals:
    * new_snapshot(snapshot) --> new snapshot was instantiated
    * save_done(save_file_path, status) --> save was finished
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
        self.emit(SIGNAL("new_snapshot(PyQt_PyObject)"), self.snapshot.pvs)

    @pyqtSlot(str, str, str)
    def save_pvs(self, save_file_path, keywords=None, comment=None):
        # Start saving process and notify when finished
        status = self.snapshot.save_pvs(save_file_path, keywords=keywords,
                                        comment=comment)
        self.emit(SIGNAL("save_done(PyQt_PyObject, PyQt_PyObject)"), save_file_path, status)

    @pyqtSlot(dict)
    def restore_pvs_from_obj(self, saved_pvs):
        # All files were already parsed when loaded. Just need to load files
        # list of pvs and do restore. Notifies when finished.
        self.snapshot.prepare_pvs_to_restore_from_list(saved_pvs)
        status = self.snapshot.restore_pvs()

        self.emit(SIGNAL("restore_done(PyQt_PyObject, PyQt_PyObject)"), saved_pvs, status)

    @pyqtSlot(str, str, dict)
    def get_save_files(self, save_dir, name_prefix, current_files):
        parsed_save_files = dict()
        # Check if any file added or modified (time of modification)
        for file_name in os.listdir(save_dir):
            file_path = os.path.join(save_dir, file_name)
            if os.path.isfile(file_path) and file_name.startswith(name_prefix):
                if file_name not in current_files:
                    pvs_list, meta_data = self.snapshot.parse_from_save_file(file_path)

                    # save data (no need to open file again later))
                    parsed_save_files[file_name] = dict()
                    parsed_save_files[file_name]["pvs_list"] = pvs_list
                    parsed_save_files[file_name]["meta_data"] = meta_data
                    parsed_save_files[file_name]["modif_time"] = os.path.getmtime(file_path)

                elif current_files[file_name]["modif_time"] != os.path.getmtime(file_path):
                    pvs_list, meta_data = self.snapshot.parse_from_save_file(file_path)
                    parsed_save_files[file_name]["pvs_list"] = pvs_list
                    parsed_save_files[file_name]["meta_data"] = meta_data
                    parsed_save_files[file_name]["modif_time"] = os.path.getmtime(file_path)

        self.emit(SIGNAL("save_files_loaded(PyQt_PyObject)"), parsed_save_files)

    def start_continous_compare(self):
        self.snapshot.start_continous_compare(self.process_callbacks)

    def stop_continous_compare(self):
        self.snapshot.stop_continous_compare()

    def process_callbacks(self, **kw):
        pass
        # TODO here raise signals data is packed in kw

    def check_status(self, status):
        report = ""
        for key in status:
            if not status[key]:
                pass  # TODO status checking


def main():
    """ Main logic """

    args_pars = argparse.ArgumentParser()
    args_pars.add_argument('req_file', help='Request file')
    args_pars.add_argument('-macros',
                           help="Macros for request file e.g.: \"SYS=TEST,DEV=D1\"")
    args_pars.add_argument('-dir',
                           help="Directory for saved files")
    args = args_pars.parse_args()

    #Parse macros string if exists
    macros = dict()
    if args.macros:
        macros_list = args.macros.split(',')
        for macro in macros_list:
            split_macro = macro.split('=')
            macros[split_macro[0]] = split_macro[1]

    # Create application which consists of two threads. "gui" runs in main
    # GUI thread. Time consuming functions are executed in worker thread.
    app = QtGui.QApplication(sys.argv)
    worker = SnapshotWorker()  # this is working object manipulating snapshot
    worker_thread = QtCore.QThread()
    worker.moveToThread(worker_thread)
    worker_thread.start()

    gui = SnapshotGui(worker, args.req_file, macros, args.dir)

    sys.exit(app.exec_())

# Start program here
if __name__ == '__main__':
    main()
