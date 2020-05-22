#!/usr/bin/env python
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import json
import os
import re
import enum

import numpy
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSortFilterProxyModel, QItemSelectionModel, \
    QItemSelectionRange, QItemSelection
from PyQt5.QtGui import QIcon, QCursor, QPalette, QColor
from PyQt5.QtWidgets import QApplication, QHeaderView, QAbstractItemView, \
    QMenu, QTableView, QVBoxLayout, QFrame, QHBoxLayout, QCheckBox, \
    QComboBox, QLineEdit, QLabel, QSizePolicy, QWidget, QSpinBox

from ..ca_core import Snapshot
from ..core import SnapshotPv, PvUpdater, process_record
from ..parser import parse_from_save_file, save_file_suffix
from .utils import show_snapshot_parse_errors, make_separator

import time


class PvCompareFilter(enum.Enum):
    show_all = 0
    show_neq = 1
    show_eq = 2


class SnapshotCompareWidget(QWidget):
    pvs_filtered = QtCore.pyqtSignal(set)
    restore_requested = QtCore.pyqtSignal(list)
    rgx_icon = None

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
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view.restore_requested.connect(self._handle_restore_request)

        self.model = SnapshotPvTableModel(snapshot, self)
        self.model.file_parse_errors.connect(self._show_snapshot_parse_errors)
        self._proxy = SnapshotPvFilterProxyModel(self)
        self._proxy.setSourceModel(self.model)
        self._proxy.filtered.connect(self.pvs_filtered)

        # Build model and set default visualization on view (column widths, etc)
        self.model.set_pvs(snapshot.pvs.values())
        self.view.setModel(self._proxy)

        # ---------- Filter control elements ---------------
        # - text input to filter by name
        # - drop down to filter by compare status
        # - check box to select if showing pvs with incomplete data

        if SnapshotCompareWidget.rgx_icon is None:
            SnapshotCompareWidget.rgx_icon = QIcon(
                os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "images/rgx.png"))

        # #### PV name filter
        pv_filter_label = QLabel("Filter:", self)
        pv_filter_label.setAlignment(Qt.AlignCenter | Qt.AlignRight)

        self.pv_filter_sel = QComboBox(self)
        self.pv_filter_sel.setEditable(True)
        self.pv_filter_sel.setIconSize(QtCore.QSize(35, 15))
        self.pv_filter_inp = self.pv_filter_sel.lineEdit()
        self.pv_filter_inp.setPlaceholderText("Filter by PV name")

        policy = self.pv_filter_sel.sizePolicy()
        policy.setHorizontalPolicy(policy.Expanding)
        self.pv_filter_sel.setSizePolicy(policy)

        self.pv_filter_sel.currentIndexChanged.connect(
            self._predefined_filter_selected)
        self.pv_filter_inp.textChanged.connect(self._create_name_filter)

        self._populate_filter_list()

        # Prepare pallets to color the pv name filter input if rgx not valid
        self._inp_palette_ok = self.pv_filter_inp.palette()
        self._inp_palette_err = QPalette()
        self._inp_palette_err.setColor(QPalette.Base, QColor("#F39292"))

        # Create a PV name filter layout and add items
        pv_filter_layout = QHBoxLayout()
        pv_filter_layout.setSpacing(10)
        pv_filter_layout.addWidget(pv_filter_label)
        pv_filter_layout.addWidget(self.pv_filter_sel)

        # #### Regex selector
        self.regex = QCheckBox("Regex", self)
        self.regex.stateChanged.connect(self._handle_regex_change)

        # #### Selector for comparison filter
        self.compare_filter_inp = QComboBox(self)
        self.compare_filter_inp.addItems(["Show all", "Different only", "Equal only"])

        self.compare_filter_inp.currentIndexChanged.connect(self._proxy.set_eq_filter)
        self.compare_filter_inp.setMaximumWidth(200)

        # ### Show disconnected selector
        self.show_disconn_inp = QCheckBox("Show disconnected PVs.", self)
        self.show_disconn_inp.setChecked(True)
        self.show_disconn_inp.stateChanged.connect(self._proxy.set_disconn_filter)
        self.show_disconn_inp.setMaximumWidth(500)

        # Tolerance setting
        tol_label = QLabel("Tolerance:")
        tol = QSpinBox()
        tol.setRange(1, 1000000)
        tol.setValue(1)
        tol.valueChanged[int].connect(self.model.change_tolerance)
        self.model.change_tolerance(tol.value())

        # ### Put all tolerance and filter selectors in one layout
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(tol_label)
        filter_layout.addWidget(tol)
        filter_layout.addWidget(make_separator(self, 'vertical'))

        filter_layout.addLayout(pv_filter_layout)
        filter_layout.addWidget(self.regex)

        filter_layout.addWidget(make_separator(self, 'vertical'))

        filter_layout.addWidget(self.compare_filter_inp)

        filter_layout.addWidget(self.show_disconn_inp)
        filter_layout.setAlignment(Qt.AlignLeft)
        filter_layout.setSpacing(10)

        # ------- Build main layout ---------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(filter_layout)
        layout.addWidget(self.view)
        self.setLayout(layout)

    def _populate_filter_list(self):
        predefined_filters = self.common_settings['predefined_filters']
        self.pv_filter_sel.blockSignals(True)
        self.pv_filter_sel.clear()
        self.pv_filter_sel.addItem(None)
        for rgx in predefined_filters.get('rgx-filters', list()):
            self.pv_filter_sel.addItem(SnapshotCompareWidget.rgx_icon, rgx)
        self.pv_filter_sel.addItems(predefined_filters.get('filters', list()))
        self.pv_filter_sel.blockSignals(False)

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

    def _show_snapshot_parse_errors(self, errors):
        show_snapshot_parse_errors(self, errors)

    def new_selected_files(self, selected_files):
        self.model.clear_snap_files()
        self.model.add_snap_files(selected_files)
        self._proxy.apply_filter()

    def clear_snap_files(self):
        self.model.clear_snap_files()

    def handle_new_snapshot_instance(self, snapshot):
        self.snapshot = snapshot
        self.model.snapshot = snapshot
        self.model.set_pvs(snapshot.pvs.values())
        self.view.sortByColumn(0, Qt.AscendingOrder)  # default sorting
        self._populate_filter_list()

    def _handle_restore_request(self, pvs_list):
        self.restore_requested.emit(pvs_list)

    def _predefined_filter_selected(self, idx):
        txt = self.pv_filter_inp.text()
        if idx == 0:
            # First empty option; the menu is always reset to this.
            return
        if not self.pv_filter_sel.itemIcon(idx).isNull():
            # Set back to first index, to get rid of the icon. Set to regex and
            # pass text of filter to the input
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


class PvTableColumns(enum.IntEnum):
    name = 0
    unit = enum.auto()
    value = enum.auto()
    snapshots = enum.auto()

    @staticmethod
    def snap_index(idx):
        return PvTableColumns.snapshots + idx


class SnapshotPvTableView(QTableView):
    """
    Default visualization of the PV model.
    """

    restore_requested = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Apply fixed default sizes to columns. Autoresizing should not be used
        # for performance reasons. It is done once when the model is reset, and
        # once per snapshot column when it is added.
        self.setSortingEnabled(True)
        self.sortByColumn(PvTableColumns.name, Qt.AscendingOrder)  # default sorting
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(20)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft)
        self.horizontalHeader().setDefaultSectionSize(200)
        self.horizontalHeader().setStretchLastSection(True)

        # Comparison doesn't make sense if columns are moved.
        self.horizontalHeader().setSectionsMovable(False)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)

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
        source = self.model().sourceModel()
        source.columnsInserted.connect(self._set_single_column_width)
        source.columnsRemoved.connect(self._apply_selection_to_full_row)
        source.modelReset.connect(self._set_columns_width)
        self.sortByColumn(PvTableColumns.name, Qt.AscendingOrder)  # default sorting


    def dataChanged(self, mode_idx, mode_idx1, roles):
        """
        Force update of the view on any data change in the model. If self.viewport().update() is not called here
        the view is not updated if application window is not in focus.
 
        :param mode_idx:
        :param mode_idx1:
        :return:
        """

        super().dataChanged(mode_idx, mode_idx1, roles)
        self.viewport().update()

    def reset(self):
        super().reset()
        self._apply_selection_to_full_row()

    def _apply_selection_to_full_row(self):
        rows = list()
        selection = QItemSelection()
        for idx in self.selectedIndexes():
            if idx.row() not in rows:
                rows.append(idx.row())
                selection.append(QItemSelectionRange(idx))

        self.selectionModel().select(selection,
                                     QItemSelectionModel.Rows | QItemSelectionModel.ClearAndSelect)

    def _set_columns_width(self):
        self.resizeColumnsToContents()
        self._apply_selection_to_full_row()

    def _set_single_column_width(self, _, first_column, last_column):
        for col in range(first_column, last_column + 1):
            self.resizeColumnToContents(col)
        self._apply_selection_to_full_row()

    def _open_menu(self, point):
        selected_rows = self.selectionModel().selectedRows()
        menu = QMenu(self)

        if selected_rows:
            menu.addAction("Copy PV name", self._copy_pv_name)
            if len(selected_rows) == 1 and len(self.model().sourceModel().get_snap_file_names()) == 1:
                    menu.addAction("Restore selected PV", self._restore_selected_pvs)

            elif len(self.model().sourceModel().get_snap_file_names()) == 1:
                menu.addAction("Restore selected PVs", self._restore_selected_pvs)

            menu.addAction("Process records of selected PVs",
                           self._process_selected_records)

        self._menu_click_pos = point
        menu.exec(QCursor.pos())
        menu.deleteLater()

    def _restore_selected_pvs(self):
        # Pass restore request to main widget (window). It will use an existing
        # mechanism in restore widget. This way all buttons, statuses etc are
        # handled same way as with "normal" restore.
        self.restore_requested.emit(self._selected_pvnames())

    def _copy_pv_name(self):
        cb = QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        idx = self.indexAt(self._menu_click_pos)
        cb.setText(self._get_pvname_with_selection_model_idx(idx), mode=cb.Clipboard)

    def _selected_pvnames(self):
        names = (self._get_pvname_with_selection_model_idx(idx)
                 for idx in self.selectedIndexes())
        return list(set(names))

    def _get_pvname_with_selection_model_idx(self, idx: QtCore.QModelIndex):
        # Map index from selection model to original model
        # Access original model through proxy model and get pv name.
        # Doing it this way is safer than just reading row content, since in future visualization can change.
        return self.model().sourceModel().get_pvname(self.selectionModel().model().mapToSource(idx).row())

    def _process_selected_records(self):
        for pvname in self._selected_pvnames():
            process_record(pvname)


# Wrap PvUpdater into QObject for threadsafe signalling
class ModelUpdater(QtCore.QObject, PvUpdater):
    update_complete = QtCore.pyqtSignal(list)
    _internal_update = QtCore.pyqtSignal(list)

    def __init__(self, parent):
        super().__init__(parent=parent, callback=self._callback)

        # Use a blocking connection to throttle the thread.
        self._internal_update.connect(self.update_complete,
                                      QtCore.Qt.BlockingQueuedConnection)

    def _callback(self, pvs):
        self._internal_update.emit(pvs)

    def stop(self):
        # The connection is blocking, so disconnect to prevent deadlock
        # while waiting for thread to finish.
        self._internal_update.disconnect()
        PvUpdater.stop(self)


class SnapshotPvTableModel(QtCore.QAbstractTableModel):
    """
    Model of the PV table. Handles adding and removing PVs (rows)
    and snapshot files (columns). Each row (PV) is represented with
    SnapshotPvTableLine object.
    """

    file_parse_errors = QtCore.pyqtSignal(list)

    def __init__(self, snapshot: Snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self._data = list()
        self._file_names = list()
        self._tolerance_f = 1

        self._headers = [''] * PvTableColumns.snapshots
        self._headers[PvTableColumns.name] = 'PV'
        self._headers[PvTableColumns.unit] = 'Unit'
        self._headers[PvTableColumns.value] = 'Current value'

        self._updater = ModelUpdater(self)
        self._updater.update_complete.connect(self._handle_pv_update)

        # Tie starting and stopping the worker thread to starting and
        # stopping of the application.
        app = QtCore.QCoreApplication.instance()
        app.aboutToQuit.connect(self._updater.stop)
        QtCore.QTimer.singleShot(0, self._updater.start)

    def get_snap_file_names(self):
        return self._file_names

    def get_pvname(self, line: int):
        return self.get_pv_line_model(line).pvname

    def get_pv_line_model(self, line: int):
        return self._data[line]

    def set_pvs(self, pvs: list):
        """
        Clear the rows and create new rows for given pvs.

        :param pvs: list of snapshot PVs
        :return:
        """
        self._updater.set_pvs(pvs)
        self.beginResetModel()
        for line in self._data:
            line.disconnect_callbacks()
        self._data = [SnapshotPvTableLine(pv, self._tolerance_f, self)
                      for pv in pvs]
        self.endResetModel()

    def add_snap_files(self, files: dict):
        """
        Add 1 column for each file in the list

        :param files: dict of files with their data
        :return:
        """
        if not files:
            return
        self._file_names += list(files.keys())
        parent_idx = QtCore.QModelIndex()
        self.beginInsertColumns(parent_idx, self.columnCount(parent_idx),
                                len(files) + self.columnCount(parent_idx) - 1)
        errors = []
        for file_name, file_data in files.items():
            pvs_list_full_names, err = \
                self._replace_macros_on_file_data(file_data)
            if err:
                errors.append((file_data['file_name'], err))

            # To get a proper update, need to go through all existing pvs.
            # Otherwise values of PVs listed in request but not in the saved
            # file are not cleared (value from previous file is seen on the
            # screen)
            prefix = self.parent().common_settings['save_file_prefix']
            short_name = file_name.lstrip(prefix).rstrip(save_file_suffix)
            self._headers.append(short_name)
            for pv_line in self._data:
                pvname = pv_line.pvname
                pv_data = pvs_list_full_names.get(pvname, {"value": None})
                pv_line.append_snap_value(pv_data.get("value", None))
        self.endInsertColumns()
        if errors:
            self.file_parse_errors.emit(errors)

    def clear_snap_files(self):
        self._file_names = list()
        self.beginRemoveColumns(QtCore.QModelIndex(), PvTableColumns.snapshots,
                                self.columnCount(self.createIndex(-1, -1)) - 1)
        # remove all snap files
        for pv_line in self._data:
            pv_line.clear_snap_values()

        self._headers = self._headers[0:PvTableColumns.snapshots]
        self.endRemoveColumns()

    def _replace_macros_on_file_data(self, file_data):
        if self.snapshot.macros:
            macros = self.snapshot.macros
        else:
            macros = file_data["meta_data"].get("macros", dict())

        pvs_list_full_names = dict()  # PVS data mapped to real pvs names (no macros)
        pvs_list, _, errors = parse_from_save_file(file_data['file_path'])

        for pv_name_raw, pv_data in pvs_list.items():
            pvs_list_full_names[SnapshotPv.macros_substitution(pv_name_raw, macros)] = pv_data

        return pvs_list_full_names, errors

    # Reimplementation of parent methods needed for visualization
    def rowCount(self, parent):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._headers)

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            return self._data[index.row()].data[index.column()].get('data', '')
        elif role == QtCore.Qt.DecorationRole:
            return self._data[index.row()].data[index.column()].get('icon', None)

    def _handle_pv_update(self, new_values):
        for value, line in zip(new_values, self._data):
            # PvUpdater may reconnect faster, so if we are not connected yet,
            # ignore the update.
            if line.conn:
                line.update_pv_value(value)

        self._emit_dataChanged()

    def _emit_dataChanged(self):
        # No need to update PV names and units.
        self.dataChanged.emit(self.createIndex(0, PvTableColumns.value),
                              self.createIndex(len(self._data),
                                               self.columnCount() - 1))

    def handle_pv_connection_status(self, line_model):
        row = self._data.index(line_model)
        last_column = len(line_model.data) - 1
        self.dataChanged.emit(self.createIndex(row, 0),
                              self.createIndex(row, last_column))

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole \
           and orientation == QtCore.Qt.Horizontal:
            return self._headers[section]

        return super().headerData(section, orientation, role)

    def change_tolerance(self, tol_f):
        self._tolerance_f = tol_f
        for line in self._data:
            line.change_tolerance(tol_f)

        self._emit_dataChanged()


class SnapshotPvTableLine(QtCore.QObject):
    """
    Model of row in the PV table. Uses SnapshotPv callbacks to update its
    visualization of the PV state. The value is updated by the parent (i.e.
    SnapshotPvTableModel).
    """
    connectionStatusChanged = QtCore.pyqtSignal('PyQt_PyObject')
    _pv_conn_changed = QtCore.pyqtSignal(dict)
    _DIR_PATH = os.path.dirname(os.path.realpath(__file__))
    _WARN_ICON = None
    _NEQ_ICON = None
    _EQ_ICON = None

    def __init__(self, pv_ref, tolerance_f, parent=None):
        super().__init__(parent)

        if SnapshotPvTableLine._WARN_ICON is None:
            SnapshotPvTableLine._WARN_ICON = \
                QIcon(os.path.join(self._DIR_PATH, "images/warn.png"))
            SnapshotPvTableLine._NEQ_ICON = \
                QIcon(os.path.join(self._DIR_PATH, "images/neq.png"))
            SnapshotPvTableLine._EQ_ICON = \
                QIcon(os.path.join(self._DIR_PATH, "images/eq.png"))

        self._tolerance_f = tolerance_f
        self._pv_ref = pv_ref
        self.pvname = pv_ref.pvname

        # Prepare to cache some values, calling into pv_ref takes longer.
        # These values are read when the first value update comes in or when
        # first needed. They are exposed as properties.
        self._is_array = None
        self._precision = None

        self.data = [None] * PvTableColumns.snapshots
        self.data[PvTableColumns.name] = {'data': pv_ref.pvname}
        self.data[PvTableColumns.unit] = {'data': 'UNDEF', 'icon': None}
        self.data[PvTableColumns.value] = {'data': 'PV disconnected',
                                           'icon': self._WARN_ICON}

        self.connectionStatusChanged \
            .connect(parent.handle_pv_connection_status)
        self._conn_clb_id = pv_ref.add_conn_callback(self._conn_callback)

        # Internal signal
        self._pv_conn_changed.connect(self._handle_conn_callback)

        if pv_ref.connected:
            self.conn = pv_ref.connected
            self.data[PvTableColumns.value]['data'] = ''
            self.data[PvTableColumns.value]['icon'] = None

        else:
            self.conn = False

    @property
    def is_array(self):
        if self._is_array is None and self._pv_ref.connected:
            self._is_array = self._pv_ref.is_array
            self._precision = self._pv_ref.precision
        return self._is_array

    @property
    def precision(self):
        self.is_array  # precision is cached by is_array
        return self._precision

    def disconnect_callbacks(self):
        """
        Disconnect from SnapshotPv object. Should be called before removing line from model.
        :return:
        """
        self._pv_ref.remove_conn_callback(self._conn_clb_id)

    def change_tolerance(self, tol_f):
        self._tolerance_f = tol_f
        self._compare()

    def append_snap_value(self, value):
        if value is not None:
            sval = SnapshotPvTableLine.string_repr_snap_value(value,
                                                              self.precision)
            self.data.append({'data': sval, 'raw_value': value})
        else:
            self.data.append({'data': '', 'raw_value': None})

        # Do compare
        self._compare()

    def change_snap_value(self, column_idx, value):
        if value is not None:
            sval = SnapshotPvTableLine.string_repr_snap_value(value,
                                                              self.precision)
            self.data[column_idx]['data'] = sval
            self.data[column_idx]['raw_value'] = value
        else:
            self.data[column_idx]['data'] = ''
            self.data[column_idx]['raw_value'] = value

        # Do compare
        self._compare()

    def clear_snap_values(self):
        self.data = self.data[0:PvTableColumns.snapshots]
        self._compare()

    def are_snap_values_eq(self):
        n_files = self.get_snap_count()
        if n_files < 2:
            return True
        else:
            first_data = self.data[PvTableColumns.snapshots]['raw_value']
            for data in self.data[PvTableColumns.snapshots + 1:]:
                if not SnapshotPv.compare(first_data, data['raw_value'],
                                          self.tolerance_from_precision()):
                    return False
            return True

    def is_snap_eq_to_pv(self, idx):
        idx = PvTableColumns.snap_index(idx)
        if self._pv_ref.connected:
            return SnapshotPv.compare(self._pv_ref.value,
                                      self.data[idx]['raw_value'],
                                      self.tolerance_from_precision())
        else:
            return False

    def get_snap_count(self):
        return len(self.data[PvTableColumns.snapshots:])

    def _compare(self, pv_value=None, get_missing=True):
        if pv_value is None and self._pv_ref.connected and get_missing:
            pv_value = self._pv_ref.value

        # Compare each snapshot to the one on its left (or the PV value in the
        # case of the leftmost snapshot).
        n_files = self.get_snap_count()
        if n_files > 0:
            values = [pv_value] + [x['raw_value'] for x in
                                   self.data[PvTableColumns.snapshots:]]
            tolerance = self.tolerance_from_precision()
            connected = self._pv_ref.connected
            for i in range(1, len(values)):
                comparison = SnapshotPv.compare(values[i-1], values[i],
                                                tolerance)
                snap = self.data[PvTableColumns.snapshots + i - 1]
                if i == 1 and not connected:
                    snap['icon'] = self._WARN_ICON
                elif not comparison:
                    snap['icon'] = self._NEQ_ICON
                else:
                    snap['icon'] = self._EQ_ICON

    def tolerance_from_precision(self):
        prec = self.precision
        if not prec or prec < 0:
            # The default precision is 6, which matches string formatting
            # behaviour. It makes no sense to do comparison to a higher
            # precision than what the user can see.
            prec = 6
        return self._tolerance_f * 10**(-prec)

    @staticmethod
    def string_repr_snap_value(value, precision):
        if isinstance(value, str):
            # If string do not dump it will add "" to a string
            return value
        else:
            # dump other values
            return SnapshotPv.value_to_display_str(value, precision)

    def update_pv_value(self, pv_value):
        value_col = self.data[PvTableColumns.value]
        unit_col = self.data[PvTableColumns.unit]

        if pv_value is None:
            value_col['data'] = ''
            self._compare(None, get_missing=False)
            return True

        new_value = SnapshotPv.value_to_display_str(pv_value, self.precision)

        if unit_col['data'] == 'UNDEF':
            unit_col['data'] = self._pv_ref.units

        if value_col['data'] == new_value:
            return False

        value_col['data'] = new_value
        self._compare(pv_value)
        return True

    def _conn_callback(self, **kwargs):
        self._pv_conn_changed.emit(kwargs)

    def _handle_conn_callback(self, data):
        self.conn = data.get('conn')
        if not self.conn:
            self.data[PvTableColumns.value] = {'data': 'PV disconnected',
                                               'icon': self._WARN_ICON}
        else:
            self.data[PvTableColumns.value] = {'data': '', 'icon': None}
        self.connectionStatusChanged.emit(self)


class SnapshotPvFilterProxyModel(QSortFilterProxyModel):
    """
    Proxy model providing a custom filtering functionality for PV table
    """
    filtered = QtCore.pyqtSignal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._disconn_filter = True  # show disconnected?
        self._name_filter = ''  # string or regex object
        self._eq_filter = PvCompareFilter.show_all
        self._filtered_pvs = set()

    def setSourceModel(self, model):
        super().setSourceModel(model)
        self.sourceModel().modelReset.connect(self.apply_filter)

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
        self.invalidateFilter()

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
            self._filtered_pvs.add(row_model.pvname)
        else:
            self._filtered_pvs.discard(row_model.pvname)

        self.filtered.emit(self._filtered_pvs)
        return result
