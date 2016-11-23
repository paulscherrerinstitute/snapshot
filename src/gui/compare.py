#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt
from enum import Enum
import os
from ..snapshot_ca import Snapshot, SnapshotPv, macros_substitution
import json
import numpy
import re


class PvCompareFilter(Enum):
    show_all = 0
    show_neq = 1
    show_eq = 2


class SnapshotCompareWidget(QtGui.QWidget):
    pvs_filtered = QtCore.pyqtSignal(list) #TODO
    def __init__(self, snapshot, common_settings, parent=None, **kw):
        super().__init__(parent=parent, **kw)
        self.snapshot = snapshot
        self.common_settings = common_settings
        self.file_compare_struct = dict()


        # ----------- PV Table -------------
        # PV table consist of:
        #     self.model: holding the data, values, being updated by PV callbacks, etc
        #     self._proxy: a proxy model implementing the filter functionality
        #     view: visual representation of the PV table

        view = SnapshotPvTableView(self)
        view.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

        self.model = SnapshotPvTableModel(snapshot, self)
        self._proxy = SnapshotPvFilterProxyModel(self)
        self._proxy.setSourceModel(self.model)
        self._proxy.filtered.connect(self._handle_filtered)

        # Build model and set default visualization on view (column widths, etc)
        self.model.add_pvs(snapshot.pvs.values())
        view.setModel(self._proxy)
        view.set_default_visualization()

        # ---------- Filter control elements ---------------
        # - text input to filter by name
        # - drop down to filter by compare status
        # - check box to select if showing pvs with incomplete data

        ##### PV name filter
        pv_filter_label = QtGui.QLabel("Filter:", self)
        pv_filter_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)

        # Select and prepare name filter entry widget:
        #    if predefined_filters: make a drop down menu but keep the option to enter filter (QComboBox)
        #    if not predefined_filters: creat a normal QLineEdit
        predefined_filters = self.common_settings["predefined_filters"]
        if predefined_filters:
            self.pv_filter_sel = QtGui.QComboBox(self)
            self.pv_filter_sel.setEditable(True)
            self.pv_filter_sel.setIconSize(QtCore.QSize(35,15))
            sel_layout = QtGui.QHBoxLayout()
            sel_layout.addStretch()
            self.pv_filter_sel.setLayout(sel_layout)
            self.pv_filter_inp = self.pv_filter_sel.lineEdit()
            self.pv_filter_inp.setPlaceholderText("Filter by PV name")

            # Add filters
            self.pv_filter_sel.addItem(None)
            for rgx in predefined_filters.get('rgx-filters', list()):
                self.pv_filter_sel.addItem(QtGui.QIcon(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                                    "images/rgx.png")),rgx)
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

        ##### Regex selector
        self.regex = QtGui.QCheckBox("Regex", self)
        self.regex.stateChanged.connect(self._create_name_filter)

        ##### Selector for comparison filter
        self.compare_filter_inp = QtGui.QComboBox(self)
        self.compare_filter_inp.addItems(["Show all", "Different only", "Equal only"])

        self.compare_filter_inp.currentIndexChanged.connect(self._proxy.set_eq_filter)
        self.compare_filter_inp.setMaximumWidth(200)

        #### Show disconnected selector
        self.show_disconn_inp = QtGui.QCheckBox("Show disconnected PVs.", self)
        self.show_disconn_inp.setChecked(True)
        self.show_disconn_inp.stateChanged.connect(self._proxy.set_disconn_filter)
        self.show_disconn_inp.setMaximumWidth(500)

        #### Put all filter selectors in one layout
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

        #------- Build main layout ---------
        layout = QtGui.QVBoxLayout(self)
        layout.setMargin(10)
        layout.setSpacing(10)
        layout.addLayout(filter_layout)
        layout.addWidget(view)
        self.setLayout(layout)

    def _handle_filtered(self, pvs_names_list):
        self.pvs_filtered.emit(pvs_names_list)

    def _create_name_filter(self):
        txt = self.pv_filter_inp.text()
        if self.regex.isChecked():
            try:
                filter = re.compile(txt)
                self.pv_filter_inp.setPalette(self._inp_palette_ok)
            except:
                # Syntax error (happens a lot during typing an expression). In such cases make compiler which will
                # not match any pv name
                filter = re.compile("")
                self.pv_filter_inp.setPalette(self._inp_palette_err)
        else:
            filter = txt
            self.pv_filter_inp.setPalette(self._inp_palette_ok)

        self._proxy.set_name_filter(filter)

    def new_selected_files(self, selected_files):
        self.model.clear_snap_files()
        self.model.add_snap_files(selected_files)

    def update_shown_files(self, updated_files):
        self.model.update_snap_files(updated_files)

    def handle_new_snapshot_instance(self, snapshot):
        self.snapshot = snapshot
        self.model.clear_pvs()
        self.model.add_pvs(snapshot.pvs.values())

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
            #Imitate same behaviour
            self.pv_filter_sel.setCurrentIndex(0)
            self.regex.setChecked(False)
            self.pv_filter_inp.setText(txt)


class SnapshotPvTableView(QtGui.QTableView):
    '''
    Default visualization of the PV model.
    '''
    def __init__(self, parent=None):
        super().__init__(parent)

        # -------- Visualization ----------
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder) # default sorting
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setMovable(True)
        self.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft)
        self.verticalHeader().setDefaultSectionSize(20)
        self.horizontalHeader().setDefaultSectionSize(200)

        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        # ---------- Context menu --------
        self.customContextMenuRequested.connect(self._open_menu)
        self.menu = QtGui.QMenu(self)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.menu.addAction("Copy PV name",self._copy_pv_name)

    def setModel(self, model):
        '''
        Extend  default method to apply default column widths (all PV names should be fully visible)
        :param model:
        :return:
        '''
        super().setModel(model)
        self.set_default_visualization()

    def dataChanged(self, QModelIndex, QModelIndex_1):
        '''
        Force update of the view on any data change in the model. If self.viewport().update() is not called here
        the view is not updated if application window is not in focus.

        :param QModelIndex:
        :param QModelIndex_1:
        :return:
        '''
        super().dataChanged(QModelIndex, QModelIndex_1)
        self.viewport().update()

    def reset(self):
        super().reset()
        self.set_snap_visualization()

    def set_default_visualization(self):
        for i in range(self.model().columnCount()):
            self.setColumnWidth(i, 200)
            self.horizontalHeader().setResizeMode(i, QtGui.QHeaderView.Interactive)

        self.horizontalHeader().setResizeMode(i,QtGui.QHeaderView.Stretch )
        self.resizeColumnToContents(0)
        self.setColumnWidth(1, 200)
        self.setColumnWidth(2, 30)

    def set_snap_visualization(self):
        '''
        Whenever the view is updated with new columns with snap values to 200, and extand last one
        :return:
        '''
        n_columns = self.model().columnCount()
        if n_columns > 3:
            self.setColumnWidth(2, 30)
            self.horizontalHeader().setResizeMode(2, QtGui.QHeaderView.Interactive)
            for i in range(3, self.model().columnCount()):
                self.setColumnWidth(i, 200)
                self.horizontalHeader().setResizeMode(i, QtGui.QHeaderView.Interactive)
        else:
            i = 2

        self.horizontalHeader().setResizeMode(i,QtGui.QHeaderView.Stretch )

    def _open_menu(self, point):
        self.menu.show()
        pos = self.mapToGlobal(point)
        pos += QtCore.QPoint(0, self.menu.sizeHint().height())
        self.menu.move(pos)

    def _copy_pv_name(self):
        cb = QtGui.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard )
        cb.setText(self.model().sourceModel().get_pvname(self.selectedIndexes()[0]), mode=cb.Clipboard)


class SnapshotPvTableModel(QtCore.QAbstractTableModel):
    '''
    Model of the PV table. Handles adding and removing PVs (rows) and snapshot files (columns).
    Each row (PV) is represented with SnapshotPvTableLine object.
    '''
    def __init__(self, snapshot: Snapshot, parent = None):
        super().__init__(parent)
        self.snapshot = snapshot
        self._pvs_lines = dict()
        self._data = list()
        self._headers = ['PV', 'Current value', '']

    def get_pvname(self, idx: QtCore.QModelIndex):
        return(self.data(idx, QtCore.Qt.DisplayRole))

    def get_pv_line_model(self, line: int):
        return(self._pvs_lines.get(self.get_pvname(self.createIndex(line, 0)), None))

    def add_pvs(self, pvs: list):
        '''
        Create new rows for given pvs.

        :param pvs: list of snapshot PVs
        :return:
        '''
        self.beginResetModel()
        for pv in pvs:
            line = SnapshotPvTableLine(pv, self)
            self._pvs_lines[pv.pvname] = line
            self._data.append(line)
            self._data[-1].data_changed.connect(self.handle_pv_change)
        self.endResetModel()

    def add_snap_files(self, files: list):
        '''
        Add 1 column for each file in the list

        :param files: dict of files with their data
        :return:
        '''
        self.beginInsertColumns(QtCore.QModelIndex(), 3, len(files)+2)
        self.file_compare_struct = dict()
        for file_name, file_data in files.items():
            pvs_list_full_names = self._replace_macros_on_file_data(file_data)

            # To get a proper update, need to go through all existing pvs. Otherwise values of PVs listed in request
            # but not in the saved file are not cleared (value from previous file is seen on the screen)
            self._headers.append(file_name)
            for pvname, pv_line in self._pvs_lines.items():
                pv_data = pvs_list_full_names.get(pvname, {"value": None})
                pv_line.append_snap_value(pv_data.get("value", None))
        self.endInsertColumns()

    def clear_snap_files(self):
        self.beginRemoveColumns(QtCore.QModelIndex(), 3, self.columnCount(self.createIndex(-1, -1))-1)
        # remove all snap files
        for pvname, pv_line in self._pvs_lines.items(): # Go through all existing pv lines
            pv_line.clear_snap_values()

        self._headers = self._headers[0:3]
        self.endRemoveColumns()

    def clear_pvs(self):
        '''
        Removes all data from the model.
        :return:
        '''
        self.beginResetModel()
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
                    pv_line.change_snap_value(idx ,pv_data.get("value", None))

    def _replace_macros_on_file_data(self, file_data):
        if self.snapshot.macros:
            macros = self.snapshot.macros
        else:
            macros = file_data["meta_data"].get("macros", dict())

        pvs_list_full_names = dict()  # PVS data mapped to real pvs names (no macros)
        for pv_name_raw, pv_data in file_data["pvs_list"].items():
            pvs_list_full_names[macros_substitution(pv_name_raw, macros)] = pv_data # snapshot_ca.py function

        return pvs_list_full_names

    # Reimplementation of parent methods needed for visualization
    def rowCount(self, parent):
        return(len(self._data))

    def columnCount(self, parent):
        return(len(self._headers))

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            return(self._data[index.row()].data[index.column()].get('data', ''))
        elif role == QtCore.Qt.DecorationRole:
            return(self._data[index.row()].data[index.column()].get('icon', None))

    def handle_pv_change(self, pv_line):
        self.dataChanged.emit(self.createIndex(self._data.index(pv_line), 0),
                              self.createIndex(self._data.index(pv_line), len(pv_line.data)))

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            return(self._headers[section])


class SnapshotPvTableLine(QtCore.QObject):
    '''
    Model of row in the PV table. Uses SnapshotPv callbacks to update its
    visualization of the PV state.
    '''
    _pv_changed = QtCore.pyqtSignal(dict)
    _pv_conn_changed = QtCore.pyqtSignal(dict)
    data_changed = QtCore.pyqtSignal(QtCore.QObject)

    def __init__(self, pv_ref, parent = None):
        super().__init__(parent)
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self._WARN_ICON = QtGui.QIcon(os.path.join(dir_path, "images/warn.png"))
        self._NEQ_ICON = QtGui.QIcon(os.path.join(dir_path, "images/neq.png"))

        self._pv_ref = pv_ref
        self.pvname = pv_ref.pvname
        self.data = [{'data': pv_ref.pvname},
                     {'data': 'PV disconnected', 'icon': self._WARN_ICON}, # current value
                     {'icon': None}] # Compare result

        # If connected take current value
        if pv_ref.connected:
            self.conn = pv_ref.connected
            self.data[1]['data'] = SnapshotPvTableLine.string_repr(pv_ref.value)
            self.data[1]['icon'] = None

        else:
            self.conn = False

        pv_ref.add_conn_callback(self._conn_callback)
        pv_ref.add_callback(self._callback)

        # Internal signal
        self._pv_conn_changed.connect(self._handle_conn_callback)
        self._pv_changed.connect(self._handle_callback)

    def append_snap_value(self, value):
        if value is not None:
            self.data.append({'data': SnapshotPvTableLine.string_repr(value), 'raw_value': value})
        else:
            self.data.append({'data': '', 'raw_value': None})

        # Do compare
        self._compare()

    def change_snap_value(self, idx, value):
        if value is not None:
            self.data[idx]['data'] = SnapshotPvTableLine.string_repr(value)
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
        n_files = len(self.data)-3  # 3 "fixed columns"
        if n_files < 2:
            return(True)
        else:
            first_data = self.data[3]['raw_value']
            for data in self.data[4:]:
                if not SnapshotPv.compare(first_data, data['raw_value'], self._pv_ref.is_array):
                    return(False)
            return(True)

    def is_snap_eq_to_pv(self, idx):
        idx += 3
        if self._pv_ref.connected:
            return(SnapshotPv.compare(self._pv_ref.value, self.data[idx]['raw_value'], self._pv_ref.is_array))
        else:
            return(False)

    def get_snap_count(self):
        return(len(self.data)-3)

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
    def string_repr(value):
        if isinstance(value, numpy.ndarray):
            # Handle arrays
            return(json.dumps(value.tolist()))
        elif isinstance(value, str):
            # If string do not dump it will add "" to a string
            return(value)
        else:
            # dump other values
            return(json.dumps(value))

    def _callback(self, **kwargs):
        self._pv_changed.emit(kwargs)

    def _handle_callback(self, data):
        pv_value = data.get('value', '')
        self.data[1]['data'] = SnapshotPvTableLine.string_repr(pv_value)
        self._compare(pv_value)
        self.data_changed.emit(self)

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
    '''
    Proxy model providing a custom filtering functionality for PV table
    '''
    filtered = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._disconn_filter = True # show disconnected?
        self._name_filter = '' # string or regex object
        self._eq_filter = PvCompareFilter.show_all
        self._filtered_pvs = list()

    def set_name_filter(self, filter):
        self._name_filter = filter
        self._apply_filter()


    def set_eq_filter(self, mode):
        self._eq_filter = PvCompareFilter(mode)
        self._apply_filter()

    def set_disconn_filter(self, state):
        self._disconn_filter = state
        self._apply_filter()

    def _apply_filter(self):
        # during invalidateFilter(), filterAcceptsRow() is called for each row
        self._filtered_pvs = list()
        self.invalidateFilter()
        self.filtered.emit(self._filtered_pvs)

    def filterAcceptsRow(self, idx: int, source_parent: QtCore.QModelIndex):
        '''
        Reimplemented parent method, to define a PV table filtering.

        :param idx: index of the table line
        :param source_parent:
        :return: visible (True), hidden(False)
        '''

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
                                 ((self._eq_filter == PvCompareFilter.show_neq) and  not files_equal) or
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

        return(result)


