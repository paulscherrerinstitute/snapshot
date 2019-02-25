#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import json
import os
import re
import logging
import threading
from collections import deque
from enum import Enum

import numpy
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from ..ca_core import Snapshot, SnapshotPv

import time


class PvCompareFilter(Enum):
    show_all = 0
    show_neq = 1
    show_eq = 2


class SnapshotCompareWidget(QtGui.QWidget):
    pvs_filtered = QtCore.pyqtSignal(list)
    restore_requested = QtCore.pyqtSignal(list)

    def __init__(self, snapshot, common_settings, parent=None, **kw):
        super().__init__(parent, **kw)
        self.snapshot = snapshot
        self.common_settings = common_settings

        # ----------- PV Table -------------
        # PV table consist of:
        #     self.model: holding the data, values, being updated by PV callbacks, etc
        #     self._proxy: a proxy model implementing the filter functionality
        #     self.view: visual representation of the PV table

        self.view = SnapshotPvTableView(self)
        self.view.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        self.view.restore_requested.connect(self._handle_restore_request)

        self.model = SnapshotPvTableModel(snapshot, self)
        self._proxy = SnapshotPvFilterProxyModel(self)
        self._proxy.setSourceModel(self.model)
        self._proxy.filtered.connect(self._handle_filtered)

        # Build model and set default visualization on view (column widths, etc)
        self.model.add_pvs(snapshot.pvs.values())
        self.view.setModel(self._proxy)

        # ---------- Filter control elements ---------------
        # - text input to filter by name
        # - drop down to filter by compare status
        # - check box to select if showing pvs with incomplete data

        # #### PV name filter
        pv_filter_label = QtGui.QLabel("Filter:", self)
        pv_filter_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)

        # Select and prepare name filter entry widget:
        #    if predefined_filters: make a drop down menu but keep the option to enter filter (QComboBox)
        #    if not predefined_filters: create a normal QLineEdit
        predefined_filters = self.common_settings["predefined_filters"]
        if predefined_filters:
            self.pv_filter_sel = QtGui.QComboBox(self)
            self.pv_filter_sel.setEditable(True)
            self.pv_filter_sel.setIconSize(QtCore.QSize(35, 15))
            sel_layout = QtGui.QHBoxLayout()
            sel_layout.addStretch()
            self.pv_filter_sel.setLayout(sel_layout)
            self.pv_filter_inp = self.pv_filter_sel.lineEdit()
            self.pv_filter_inp.setPlaceholderText("Filter by PV name")

            # Add filters
            self.pv_filter_sel.addItem(None)
            for rgx in predefined_filters.get('rgx-filters', list()):
                self.pv_filter_sel.addItem(QtGui.QIcon(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                                    "images/rgx.png")), rgx)
            self.pv_filter_sel.addItems(predefined_filters.get('filters', list()))
            self.pv_filter_sel.currentIndexChanged.connect(self._predefined_filter_selected)

        else:
            self.pv_filter_inp = QtGui.QLineEdit(self)
            self.pv_filter_inp.setPlaceholderText("Filter by PV name")
            self.pv_filter_sel = self.pv_filter_inp

        self.pv_filter_inp.textChanged.connect(self._create_name_filter)

        # Prepare pallets to color the pv name filter input if rgx not valid
        self._inp_palette_ok = self.pv_filter_inp.palette()
        self._inp_palette_err = QtGui.QPalette()
        self._inp_palette_err.setColor(QtGui.QPalette.Base, QtGui.QColor("#F39292"))

        # Create a PV name filter layout and add items
        pv_filter_layout = QtGui.QHBoxLayout()
        pv_filter_layout.setSpacing(10)
        pv_filter_layout.addWidget(pv_filter_label)
        pv_filter_layout.addWidget(self.pv_filter_sel)

        # #### Regex selector
        self.regex = QtGui.QCheckBox("Regex", self)
        self.regex.stateChanged.connect(self._handle_regex_change)

        # #### Selector for comparison filter
        self.compare_filter_inp = QtGui.QComboBox(self)
        self.compare_filter_inp.addItems(["Show all", "Different only", "Equal only"])

        self.compare_filter_inp.currentIndexChanged.connect(self._proxy.set_eq_filter)
        self.compare_filter_inp.setMaximumWidth(200)

        # ### Show disconnected selector
        self.show_disconn_inp = QtGui.QCheckBox("Show disconnected PVs.", self)
        self.show_disconn_inp.setChecked(True)
        self.show_disconn_inp.stateChanged.connect(self._proxy.set_disconn_filter)
        self.show_disconn_inp.setMaximumWidth(500)

        # ### Put all filter selectors in one layout
        filter_layout = QtGui.QHBoxLayout()
        filter_layout.addLayout(pv_filter_layout)
        filter_layout.addWidget(self.regex)

        sep = QtGui.QFrame(self)
        sep.setFrameShape(QtGui.QFrame.VLine)
        filter_layout.addWidget(sep)

        filter_layout.addWidget(self.compare_filter_inp)

        filter_layout.addWidget(self.show_disconn_inp)
        filter_layout.setAlignment(Qt.AlignLeft)
        filter_layout.setSpacing(10)

        # ------- Build main layout ---------
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        layout.addLayout(filter_layout)
        layout.addWidget(self.view)
        self.setLayout(layout)

    def _handle_filtered(self, pvs_names_list):
        self.pvs_filtered.emit(pvs_names_list)

    def _handle_regex_change(self, state):
        txt = self.pv_filter_inp.text()
        if state and txt.strip() == '':
            self.pv_filter_inp.setText('.*')
        elif not state and txt.strip() == '.*':
            self.pv_filter_inp.setText('')
        else:
            self._create_name_filter(txt)

    def _create_name_filter(self, txt):
        if self.regex.isChecked():
            try:
                srch_filter = re.compile(txt)
                self.pv_filter_inp.setPalette(self._inp_palette_ok)
            except:
                # Syntax error (happens a lot during typing an expression). In such cases make compiler which will
                # not match any pv name
                srch_filter = re.compile("")
                self.pv_filter_inp.setPalette(self._inp_palette_err)
        else:
            srch_filter = txt
            self.pv_filter_inp.setPalette(self._inp_palette_ok)

        self._proxy.set_name_filter(srch_filter)

    def new_selected_files(self, selected_files):
        self.model.clear_snap_files()
        self.model.add_snap_files(selected_files)
        self._proxy.apply_filter()

    def update_shown_files(self, updated_files):
        self.model.update_snap_files(updated_files)
        self._proxy.apply_filter()

    def handle_new_snapshot_instance(self, snapshot):
        self.snapshot = snapshot
        self.model.snapshot = snapshot
        self.model.clear_pvs()
        self.model.add_pvs(snapshot.pvs.values())
        self.view.sortByColumn(0, Qt.AscendingOrder)  # default sorting

    def _handle_restore_request(self, pvs_list):
        self.restore_requested.emit(pvs_list)

    def _predefined_filter_selected(self, idx):
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
            # Imitate same behaviour
            self.pv_filter_sel.setCurrentIndex(0)
            self.regex.setChecked(False)
            self.pv_filter_inp.setText(txt)
            
    def filter_update(self):
        self._proxy.apply_filter()


class SnapshotPvTableView(QtGui.QTableView):
    """
    Default visualization of the PV model.
    """

    restore_requested = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        # -------- Visualization ----------
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)  # default sorting
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setMovable(True)
        self.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft)
        self.verticalHeader().setDefaultSectionSize(20)
        self.horizontalHeader().setDefaultSectionSize(200)

        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)

        # ---------- Context menu --------
        self.customContextMenuRequested.connect(self._open_menu)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        # ------------------------------
        self._menu_click_pos = None

    def setModel(self, model):
        """
        Extend  default method to apply default column widths (all PV names should be fully visible)
        :param model:
        :return:
        """
        super().setModel(model)
        self.model().sourceModel().columnsInserted.connect(self.set_snap_visualization)
        self.model().sourceModel().columnsRemoved.connect(self.set_snap_visualization)
        self.set_default_visualization()
        self.sortByColumn(0, Qt.AscendingOrder)  # default sorting

    def dataChanged(self, mode_idx, mode_idx1):
        """
        Force update of the view on any data change in the model. If self.viewport().update() is not called here
        the view is not updated if application window is not in focus.
 
        :param mode_idx:
        :param mode_idx1:
        :return:
        """

        super().dataChanged(mode_idx, mode_idx1)
        self.viewport().update()

    def reset(self):
        super().reset()
        self.set_snap_visualization()

    def _apply_selection_to_full_row(self):
        rows = list()
        selection = QtGui.QItemSelection()
        for idx in self.selectedIndexes():
            if idx.row() not in rows:
                rows.append(idx.row())
                selection.append(QtGui.QItemSelectionRange(idx))

        self.selectionModel().select(selection,
                                     QtGui.QItemSelectionModel.Rows | QtGui.QItemSelectionModel.ClearAndSelect)

    def set_default_visualization(self):
        i = 0
        for i in range(self.model().columnCount()):
            self.setColumnWidth(i, 200)
            self.horizontalHeader().setResizeMode(i, QtGui.QHeaderView.Interactive)

        self.horizontalHeader().setResizeMode(i, QtGui.QHeaderView.Stretch)
        self.resizeColumnToContents(0)
        self.setColumnWidth(1, 200)
        self.setColumnWidth(2, 30)

        self._apply_selection_to_full_row()

    def set_snap_visualization(self):
        """
        Whenever the view is updated with new columns with snap values to 200, and extend last one
        :return:
        """
        n_columns = self.model().columnCount()
        i = 0
        if n_columns > 3:
            self.setColumnWidth(2, 30)
            self.horizontalHeader().setResizeMode(2, QtGui.QHeaderView.Interactive)
            for i in range(3, self.model().columnCount()):
                self.setColumnWidth(i, 200)
                self.horizontalHeader().setResizeMode(i, QtGui.QHeaderView.Interactive)
        else:
            i = 2

        self.horizontalHeader().setResizeMode(i, QtGui.QHeaderView.Stretch)

        self._apply_selection_to_full_row()

    def _open_menu(self, point):
        selected_rows = self.selectionModel().selectedRows()
        menu = QtGui.QMenu(self)

        if selected_rows:
            menu.addAction("Copy PV name", self._copy_pv_name)
            if len(selected_rows) == 1 and len(self.model().sourceModel().get_snap_file_names()) == 1:
                    menu.addAction("Restore selected PV", self._restore_selected_pvs)

            elif len(self.model().sourceModel().get_snap_file_names()) == 1:
                menu.addAction("Restore selected PVs", self._restore_selected_pvs)

        self._menu_click_pos = point
        menu.exec(QtGui.QCursor.pos())

    def _restore_selected_pvs(self):
        pvs = list()
        for idx in self.selectedIndexes():
            pvname = self._get_pvname_with_selection_model_idx(idx)

            if pvname not in pvs:
                pvs.append(pvname)

        # Pass restore request to main widget (window). It will use an existing mechanism in restore widget.
        # This way all buttons, statuses etc are handled same way as with "normal" restore.
        self.restore_requested.emit(pvs)

    def _copy_pv_name(self):
        cb = QtGui.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        idx = self.indexAt(self._menu_click_pos)
        cb.setText(self._get_pvname_with_selection_model_idx(idx), mode=cb.Clipboard)

    def _get_pvname_with_selection_model_idx(self, idx: QtCore.QModelIndex):
        # Map index from selection model to original model
        # Access original model through proxy model and get pv name.
        # Doing it this way is safer than just reading row content, since in future visualization can change.
        return self.model().sourceModel().get_pvname(self.selectionModel().model().mapToSource(idx).row())


class SnapshotPvTableModel(QtCore.QAbstractTableModel):
    """
    Model of the PV table. Handles adding and removing PVs (rows) and snapshot files (columns).
    Each row (PV) is represented with SnapshotPvTableLine object. It doesnt emmit dataChange() on each
    PV change, but rather 5 times per second if some PVs have changed in this time. This increases performance.
    """

    def __init__(self, snapshot: Snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self._pvs_lines = dict()
        self._data = list()
        self._headers = ['PV', 'Current value', '']
        self._some_data_changed = False

        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._push_data_to_view)
        self._timer.start(500)  # Defined GUI update rate
        self._file_names = list()

    def get_snap_file_names(self):
        return self._file_names

    def get_pvname(self, line: int):
        return self.get_pv_line_model(line).pvname

    def get_pv_line_model(self, line: int):
        return self._pvs_lines.get(self.data(self.createIndex(line, 0), QtCore.Qt.DisplayRole), None)

    def add_pvs(self, pvs: list):
        """
        Create new rows for given pvs.

        :param pvs: list of snapshot PVs
        :return:
        """
        self.beginResetModel()
        for pv in pvs:
            line = SnapshotPvTableLine(pv, self)
            self._pvs_lines[pv.pvname] = line
            self._data.append(line)
            self._data[-1].data_changed.connect(self.handle_pv_change)
        self.endResetModel()

    def add_snap_files(self, files: dict):
        """
        Add 1 column for each file in the list

        :param files: dict of files with their data
        :return:
        """
        self._file_names += list(files.keys())
        self.beginInsertColumns(QtCore.QModelIndex(), 3, len(files) + 2)
        for file_name, file_data in files.items():
            pvs_list_full_names = self._replace_macros_on_file_data(file_data)

            # To get a proper update, need to go through all existing pvs. Otherwise values of PVs listed in request
            # but not in the saved file are not cleared (value from previous file is seen on the screen)
            self._headers.append(file_name)
            for pvname, pv_line in self._pvs_lines.items():
                pv_data = pvs_list_full_names.get(pvname, {"value": None})
                pv_line.append_snap_value(pv_data.get("value", None))
        self.endInsertColumns()
        self.insertColumns(1, 1, QtCore.QModelIndex())

    def clear_snap_files(self):
        self._file_names = list()
        self.beginRemoveColumns(QtCore.QModelIndex(), 3, self.columnCount(self.createIndex(-1, -1)) - 1)
        # remove all snap files
        for pvname, pv_line in self._pvs_lines.items():  # Go through all existing pv lines
            pv_line.clear_snap_values()

        self._headers = self._headers[0:3]
        self.endRemoveColumns()

    def clear_pvs(self):
        """
        Removes all data from the model.
        :return:
        """
        self.beginResetModel()
        for line in self._pvs_lines.values():
            line.disconnect_callbacks()
        self._data = list()
        self._pvs_lines = dict()
        self.endResetModel()

    def update_snap_files(self, updated_files):
        # Check if one of updated files is currently selected, and update
        # the values if it is.
        for file_name in self._headers:
            file_data = updated_files.get(file_name, None)
            if file_data is not None:
                saved_pvs = self._replace_macros_on_file_data(file_data)
                idx = self._headers.index(file_name)
                for pvname, pv_line in self._pvs_lines.items():
                    pv_data = saved_pvs.get(pvname, {"value": None})
                    pv_line.change_snap_value(idx, pv_data.get("value", None))

    def _replace_macros_on_file_data(self, file_data):
        if self.snapshot.macros:
            macros = self.snapshot.macros
        else:
            macros = file_data["meta_data"].get("macros", dict())

        pvs_list_full_names = dict()  # PVS data mapped to real pvs names (no macros)
        for pv_name_raw, pv_data in file_data["pvs_list"].items():
            pvs_list_full_names[SnapshotPv.macros_substitution(pv_name_raw, macros)] = pv_data

        return pvs_list_full_names

    # Reimplementation of parent methods needed for visualization
    def rowCount(self, parent):
        return len(self._data)

    def columnCount(self, parent):
        return len(self._headers)

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            return self._data[index.row()].data[index.column()].get('data', '')
        elif role == QtCore.Qt.DecorationRole:
            return self._data[index.row()].data[index.column()].get('icon', None)

    def handle_pv_change(self, pv_line):
        self._some_data_changed = True

    def _push_data_to_view(self):
        """
        This function is called periodically by self._timer. It emits dataChanged() signal
        which forces views to update the whole PV table.
        """
        if self._some_data_changed:
            # Something changed. Update view.
            self._some_data_changed = False
            self.dataChanged.emit(self.createIndex(0, 0), self.createIndex(len(self._data) - 1,
                                  len(self._data[-1].data) - 1))

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            return self._headers[section]


class SnapshotPvTableLine(QtCore.QObject):
    """
    Model of row in the PV table. Uses SnapshotPv callbacks to update its
    visualization of the PV state.
    """
    _pv_changed = QtCore.pyqtSignal(dict)
    _pv_conn_changed = QtCore.pyqtSignal(dict)
    data_changed = QtCore.pyqtSignal(QtCore.QObject)
    _DIR_PATH = os.path.dirname(os.path.realpath(__file__))

    def __init__(self, pv_ref, parent=None):
        super().__init__(parent)
        self._last_update = time.time()
        self._WARN_ICON = QtGui.QIcon(os.path.join(self._DIR_PATH, "images/warn.png"))
        self._NEQ_ICON = QtGui.QIcon(os.path.join(self._DIR_PATH, "images/neq.png"))

        self._pv_ref = pv_ref
        self.pvname = pv_ref.pvname
        self.data = [{'data': pv_ref.pvname},
                     {'data': 'PV disconnected', 'icon': self._WARN_ICON},  # current value
                     {'icon': None}]  # Compare result

        self._clb_id = None
        self._conn_clb_id = pv_ref.add_conn_callback(self._conn_callback)
        self._clb_id = pv_ref.add_callback(self._callback, with_ctrlvars=False)

        # Internal signal
        self._pv_conn_changed.connect(self._handle_conn_callback)
        self._pv_changed.connect(self._handle_callback)

        # If connected take current value (might missed first callbacks)
        if pv_ref.connected:
            self.conn = pv_ref.connected
            self.data[1]['data'] = pv_ref.value_as_str()
            self.data[1]['icon'] = None

        else:
            self.conn = False

        self._signal_emitted = False

        self._reattacher_cv = threading.Condition()
        self._reattacher = threading.Thread(target=self._reattacher_run)
        self._reattacher.start()

    def _reattacher_run(self):
        logger = logging.getLogger(__name__)
        while True:
            with self._reattacher_cv:
                while not self._signal_emitted:
                    #logger.info("Was notified")
                    self._reattacher_cv.wait()
                #logger.info("reattaching callback")
                self._signal_emitted = False
                time.sleep(1)
                self._clb_id = self._pv_ref.add_callback(self._callback, with_ctrlvars=False)

    def disconnect_callbacks(self):
        """
        Disconnect from SnapshotPv object. Should be called before removing line from model.
        :return:
        """
        self._pv_ref.remove_conn_callback(self._conn_clb_id)
        if self._clb_id is not None:
            self._pv_ref.remove_callback(self._clb_id)

    def append_snap_value(self, value):
        if value is not None:
            self.data.append({'data': SnapshotPvTableLine.string_repr_snap_value(value), 'raw_value': value})
        else:
            self.data.append({'data': '', 'raw_value': None})

        # Do compare
        self._compare()

    def change_snap_value(self, idx, value):
        if value is not None:
            self.data[idx]['data'] = SnapshotPvTableLine.string_repr_snap_value(value)
            self.data[idx]['raw_value'] = value
        else:
            self.data[idx]['data'] = ''
            self.data[idx]['raw_value'] = value

        # Do compare
        self._compare()

    def clear_snap_values(self):
        self.data = self.data[0:3]
        self._compare()

    def are_snap_values_eq(self):
        n_files = len(self.data) - 3  # 3 "fixed columns"
        if n_files < 2:
            return True
        else:
            first_data = self.data[3]['raw_value']
            for data in self.data[4:]:
                if not SnapshotPv.compare(first_data, data['raw_value'], self._pv_ref.is_array):
                    return False
            return True

    def is_snap_eq_to_pv(self, idx):
        idx += 3
        if self._pv_ref.connected:
            return SnapshotPv.compare(self._pv_ref.value, self.data[idx]['raw_value'], self._pv_ref.is_array)
        else:
            return False

    def get_snap_count(self):
        return len(self.data) - 3

    def _compare(self, pv_value=None):
        if pv_value is None and self._pv_ref.connected:
            pv_value = self._pv_ref.value

        n_files = self.get_snap_count()

        if n_files == 1 and self._pv_ref.connected and \
                not SnapshotPv.compare(pv_value, self.data[-1]['raw_value'], self._pv_ref.is_array):
            self.data[2]['icon'] = self._NEQ_ICON
        else:
            self.data[2]['icon'] = None

    @staticmethod
    def string_repr_snap_value(value):
        if isinstance(value, numpy.ndarray):
            # Handle arrays
            return json.dumps(value.tolist())
        elif isinstance(value, str):
            # If string do not dump it will add "" to a string
            return value
        else:
            # dump other values
            return json.dumps(value)

    def _callback(self, **kwargs):
        if self._clb_id is not None:
            self._pv_ref.remove_callback(self._clb_id)
            self._clb_id = None
        self._pv_changed.emit(kwargs)

    def _handle_callback(self, data):

        pv_value = data.get('value', '')
        self.data[1]['data'] = SnapshotPv.value_to_str(pv_value, self._pv_ref.is_array)
        self._compare(pv_value)
        self._last_update = time.time()

        self.data_changed.emit(self)
        with self._reattacher_cv:
            self._signal_emitted = True
            self._reattacher_cv.notify_all()

    def _conn_callback(self, **kwargs):
        self._pv_conn_changed.emit(kwargs)

    def _handle_conn_callback(self, data):
        self.conn = data.get('conn')
        if not self.conn:
            self.data[1] = {'data': 'PV disconnected', 'icon': self._WARN_ICON}
            self.data[2]['icon'] = None
        else:
            self.data[1] = {'data': '', 'icon': None}

        self._compare()
        self.data_changed.emit(self)


class SnapshotPvFilterProxyModel(QtGui.QSortFilterProxyModel):
    """
    Proxy model providing a custom filtering functionality for PV table
    """
    filtered = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._disconn_filter = True  # show disconnected?
        self._name_filter = ''  # string or regex object
        self._eq_filter = PvCompareFilter.show_all
        self._filtered_pvs = list()
    
    def setSourceModel(self, model):
        super().setSourceModel(model)
        self.sourceModel().dataChanged.connect(self.apply_filter)

    def set_name_filter(self, srch_filter):
        self._name_filter = srch_filter
        self.apply_filter()

    def set_eq_filter(self, mode):
        self._eq_filter = PvCompareFilter(mode)
        self.apply_filter()

    def set_disconn_filter(self, state):
        self._disconn_filter = state
        self.apply_filter()

    def apply_filter(self):
        # during invalidateFilter(), filterAcceptsRow() is called for each row
        self._filtered_pvs = list()
        self.invalidate()
        self.filtered.emit(self._filtered_pvs)

    def filterAcceptsRow(self, idx: int, source_parent: QtCore.QModelIndex):
        """
        Reimplemented parent method, to define a PV table filtering.

        :param idx: index of the table line
        :param source_parent:
        :return: visible (True), hidden(False)
        """

        row_model = self.sourceModel().get_pv_line_model(idx)
        result = False
        if row_model:
            n_files = row_model.get_snap_count()

            if isinstance(self._name_filter, str):
                name_match = self._name_filter in row_model.pvname
            else:
                # regex parser
                name_match = (self._name_filter.fullmatch(row_model.pvname) is not None)

            # Connected is shown in both cases, disconnected only if in show all mode
            connected_match = row_model.conn or self._disconn_filter

            if n_files > 1:  # multi-file mode
                files_equal = row_model.are_snap_values_eq()
                compare_match = (((self._eq_filter == PvCompareFilter.show_eq) and files_equal) or
                                 ((self._eq_filter == PvCompareFilter.show_neq) and not files_equal) or
                                 (self._eq_filter == PvCompareFilter.show_all))

                result = name_match and ((row_model.conn and compare_match) or (not row_model.conn and connected_match))

            elif n_files == 1:  # "pv-compare" mode
                compare = row_model.is_snap_eq_to_pv(0)
                compare_match = (((self._eq_filter == PvCompareFilter.show_eq) and compare) or
                                 ((self._eq_filter == PvCompareFilter.show_neq) and not compare) or
                                 (self._eq_filter == PvCompareFilter.show_all))

                result = name_match and ((row_model.conn and compare_match) or (not row_model.conn and connected_match))
            else:
                # Only name and connection filters apply
                result = name_match and connected_match

        if result:
            self._filtered_pvs.append(row_model.pvname)

        return result
