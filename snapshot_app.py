import threading
import sys
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import pyqtSlot, Qt, SIGNAL
import time
import datetime
import threading

from snapshot import *

# close with ctrl+C
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)


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


class SnapshotSaveWidget(QtGui.QWidget):

    def __init__(self, worker, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)
        # Set file name and pass when save is pressed, pass file path to worker
        # to execute save
        # Add meta data TODO

        name_extension = datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d_%H%M')
        
        self.file_path = None
        self.worker = worker

        # Create main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        min_label_width = 120
        # Make a field to select file extension
        extension_layout = QtGui.QHBoxLayout(self)
        extension_layout.setSpacing(10)
        extension_label = QtGui.QLabel("Name extension", self)
        extension_label.setMinimumWidth(min_label_width)
        self.extension_input = QtGui.QLineEdit(name_extension, self)
        extension_layout.addWidget(extension_label)
        extension_layout.addWidget(self.extension_input)

        # Make a field to enable user adding a comment
        comment_layout = QtGui.QHBoxLayout(self)
        comment_layout.setSpacing(10)
        comment_label = QtGui.QLabel("Comment", self)
        comment_label.setMinimumWidth(min_label_width)
        self.comment_input = QtGui.QLineEdit(self)
        comment_layout.addWidget(comment_label)
        comment_layout.addWidget(self.comment_input)

        # Make field for keywords
        keyword_layout = QtGui.QHBoxLayout(self)
        keyword_layout.setSpacing(10)
        keyword_label = QtGui.QLabel("Keywords", self)
        keyword_label.setMinimumWidth(min_label_width)
        self.keyword_input = QtGui.QLineEdit(self)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)

        save_button = QtGui.QPushButton("Save", self)
        save_button.clicked.connect(self.start_save)

        layout.addItem(extension_layout)
        layout.addItem(comment_layout)
        layout.addItem(keyword_layout)
        layout.addWidget(save_button)

    def start_save(self):
        self.file_path = "RV_" + self.extension_input.text()
        QtCore.QMetaObject.invokeMethod(self.worker, "save_pvs",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(str, self.file_path),
                                        QtCore.Q_ARG(str, self.keyword_input.text()),
                                        QtCore.Q_ARG(str, self.comment_input.text()))


class SnapshotRestoreWidget(QtGui.QWidget):

    def __init__(self, worker, common_settings, parent=None, **kw):
        QtGui.QWidget.__init__(self, parent, **kw)
        # Select file and start restoring when restore button is pressed,
        # pass file path to worker
        # Add meta data TODO
        self.worker = worker
        self.common_settings = common_settings

        # Listen signals
        self.connect(self.worker, SIGNAL("save_files_loaded(PyQt_PyObject)"),
                     self.make_file_list)

        # Create main layout
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Create list of files, keywords, comments
        self.file_selector = QtGui.QTreeWidget(self)
        self.file_selector.setColumnCount(3)
        self.file_selector.setHeaderLabels(["File", "Keywords", "Comment"])

        # TODO moving throuh list should change self.common_settings["pvs_to_restore"]

        #self.file_input = SnapshotFileSelector(self)
        restore_button = QtGui.QPushButton("Restore", self)
        restore_button.clicked.connect(self.start_restore)

        #layout.addWidget(self.file_input)
        layout.addWidget(self.file_selector)
        layout.addWidget(restore_button)

    def make_file_list(self, file_list):
        for key in file_list:

            keywords = file_list[key]["meta_data"].get("keywords", "")
            comment = file_list[key]["meta_data"].get("comment", "")
            print(keywords + comment)
            save_file = QtGui.QTreeWidgetItem([key, keywords, comment])

            self.file_selector.addTopLevelItem(save_file)

    def start_restore(self):
        # Use one of the preloaded caved files
        QtCore.QMetaObject.invokeMethod(self.worker,
                                        "restore_pvs_from_obj",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(dict,
                                                     self.common_settings["pvs_to_restore"]))



class TestWidget(QtGui.QWidget):

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.thread = Worker()
        self.label = QtGui.QLabel("bla", self)
        self.connect(self.thread, SIGNAL("setPVs(PyQt_PyObject)"), self.setPVs)
        self.thread.start()

    def setPVs(self, pvs):
        self.pvs = pvs
        for key in self.pvs:
            print(key)


class SnapshotGui(QtGui.QWidget):

    '''
    Main GUI class for Snapshot application. It needs separate working
    thread where core application is running
    '''

    def __init__(self, worker, req_file_name, req_file_macros=None,
                 save_dir=None, save_file_dft=None, mode=None, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.worker = worker
        self.parsed_save_files = dict()
        self.setMinimumSize(650, 500)

        # common_settings is a dictionary which holds common configuration of
        # the application (such as directory with save files, request file
        # path, etc). It is propagated to other snapshot widgets if needed

        self.common_settings = dict()
        self.common_settings["req_file_name"] = "../RV.req"#req_file_name
        self.common_settings["req_file_macros"] = req_file_macros
        self.common_settings["save_dir"] ="." #save_dir TODO
        self.common_settings["save_file_dft"] = save_file_dft

        # Snapshot gui consists of two tabs: "Save" and "Restore" default
        # is selected depending on mode parameter

        main_layout = QtGui.QVBoxLayout(self)
        self.setLayout(main_layout)

        # Tab widget. Each tab has it's own widget. Need one for save 
        # and one for Restore
        tabs = QtGui.QTabWidget(self)
        tabs.setMinimumSize(600, 450)

        save_widget = SnapshotSaveWidget(self.worker, tabs)
        restore_widget = SnapshotRestoreWidget(self.worker,
                                               self.common_settings, tabs)

        tabs.addTab(save_widget, "Save")
        tabs.addTab(restore_widget, "Restore")

        self.start_gui()
        self.show() # TODO check why it waits for end of get_save_files method
        self.setWindowTitle('Snapshot')
        self.get_save_files()


    def start_gui(self):
        if not self.common_settings["req_file_name"]:
            # TODO request dialog to select request file
            pass
        else:
            # initialize snapshot and show the gui in proper mode 
            # TODO (select tab)
            self.worker.init_snapshot(self.common_settings["req_file_name"],
                                             self.common_settings["req_file_macros"])
               
    def get_save_files(self):
        prefix = os.path.split(self.common_settings["req_file_name"])[1].split(".")[0]
        QtCore.QMetaObject.invokeMethod(self.worker, "get_save_files",
                                        Qt.QueuedConnection,
                                        QtCore.Q_ARG(str, self.common_settings["save_dir"]),
                                        QtCore.Q_ARG(str, prefix))


class SnapshotWorker(QtCore.QObject):
    # This worker object running in separate thread

    def __init__(self, parent=None):

        QtCore.QObject.__init__(self, parent)
        # Instance of snapshot will be created with  init_snapshot(), which
        self.snapshot = None

    def init_snapshot(self, req_file_path, req_macros=None):
        # creates new instance of snapshot and loads the request file and
        # emit signal new_snapshot to update GUI

        self.snapshot = Snapshot(req_file_path, req_macros)
        self.emit(SIGNAL("new_snapshot(PyQt_PyObject)"), self.snapshot.pvs)

    @pyqtSlot(str, str, str)
    def save_pvs(self, save_file_path, keywords=None, comment=None):
        tatus = self.snapshot.save_pvs(save_file_path, keywords=keywords,
                                       comment=comment)
    @pyqtSlot(str, str)
    def get_save_files(self, save_dir, name_prefix):
        parsed_save_files = dict()

        for file_name in os.listdir(save_dir):
            if os.path.isfile(file_name) and file_name.startswith(name_prefix):
                new_path = os.path.join(save_dir, file_name)
                pvs_list, meta_data = self.snapshot.parse_from_save_file(new_path)

                # save data (no need to open file again later))
                parsed_save_files[file_name] = dict()
                parsed_save_files[file_name]["pvs_list"] = pvs_list
                parsed_save_files[file_name]["meta_data"] = meta_data
        
        self.emit(SIGNAL("save_files_loaded(PyQt_PyObject)"), parsed_save_files)


    @pyqtSlot(dict)
    def restore_pvs_from_obj(self, saved_pvs):
        # All files are already parsed. Just need to load selected one
        # and do parse
        self.snapshot.load_saved_pvs_from_obj(saved_pvs)
        self.snapshot.restore_pvs()
        # TODO return status

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
    #save_rest = Snapshot("../RV.req")


    app = QtGui.QApplication(sys.argv)
    worker = SnapshotWorker(app)
    worker_thread = threading.Thread(target=worker)

    gui = SnapshotGui(worker, "../RV.req", {"SYS": "rvintarHost", "NAME": "b1"})
    

    sys.exit(app.exec_())

# Start program here
if __name__ == '__main__':
    main()


kkkk
