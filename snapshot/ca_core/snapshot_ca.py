#!/usr/bin/env python
#
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import json
import logging
import os
import time
from collections import OrderedDict
from enum import Enum

import numpy
from epics import PV, ca, dbr

from snapshot.core import PvStatus, SnapshotPv, background_workers, since_start
from snapshot.parser import SnapshotReqFile, parse_from_save_file, parse_macros, parse_to_save_file


# For pyepics versions older than 3.2.4, this was set to True only for
ca.AUTO_CLEANUP = True
# python 2 but not for python 3, which resulted in errors when closing
# the application. If true, ca.finalize_libca() is called when app is
# closed


class ActionStatus(Enum):
    """
    Returned by Snapshot methods to indicate their stressfulness. Possible states:
        busy: Returned by restore_pvs() if previous restore did not finished yet (non-blocking restore).
        ok: Action succeeded.
        no_data: Returned by restore_pvs() if no data was provided for restore.
        no_conn: Returned if one of the PVs is not connected and not in force mode.
        timeout: Returned by restore_pvs_blocking() when timeout occurs before all PVs are restored.
    """
    busy = 0
    ok = 1
    no_data = 2
    no_conn = 3
    timeout = 4
    os_error = 5


class Snapshot(object):
    def __init__(self, req_file_path=None, macros=None):
        """
        Main snapshot class. Provides methods to handle PVs from request or snapshot files and to create, delete, etc
        snap (saved) files

        :param req_file_path: Path to the request file.
        :param macros: macros to be substituted in request file (can be dict {'A': 'B', 'C': 'D'} or str "A=B,C=D").

        :return:
        """

        if isinstance(macros, str):
            # Raises MacroError in case of problems
            macros = parse_macros(macros)
        elif macros is None:
            macros = {}

        self.pvs = {}
        self.macros = macros
        self.req_file_path = ''
        self.req_file_metadata = {}

        # Other important states
        self._restore_started = False
        self._restore_blocking_done = False
        self._blocking_restore_pvs_status = {}
        self._restore_callback = None
        self._current_restore_forced = False

        self.restored_pvs_list = []
        self.restore_callback = None

        if req_file_path:
            since_start("Started parsing reqfile")
            # holds path to the req_file_path as this is sort of identifier
            self.req_file_path = \
                os.path.normpath(os.path.abspath(req_file_path))
            req_f = SnapshotReqFile(self.req_file_path,
                                    changeable_macros=list(macros.keys()))
            pvs, metadata, pvs_config = req_f.read()
            since_start("Finished parsing reqfile")

            self.req_file_metadata = metadata
            self.add_pvs(pvs, pvs_config)

    def add_pvs(self, pv_list, pv_configs):
        """
        Creates SnapshotPv objects for each PV in list.

        :param pv_list: List of PV names.

        :return:
        """

        since_start("Started adding PVs")

        # pyepics will handle PVs to have only one connection per PV.
        # If pv not yet on list add it.
        if len(pv_list) == len(pv_configs):
            for pvname_raw, pvname_config in zip(pv_list, pv_configs):
                p_name = SnapshotPv.macros_substitution(pvname_raw, self.macros)
                if not self.pvs.get(p_name):

                    pv_ref = SnapshotPv(p_name, pvname_config.get(
                        p_name, {}))

                # if not self.pvs.get(pv_ref.pvname):
                    self.pvs[pv_ref.pvname] = pv_ref
        else:
            for pvname_raw in pv_list:
                p_name = SnapshotPv.macros_substitution(pvname_raw, self.macros)
                if not self.pvs.get(p_name):

                    pv_ref = SnapshotPv(p_name)

                # if not self.pvs.get(pv_ref.pvname):
                    self.pvs[pv_ref.pvname] = pv_ref

        since_start("Finished adding PVs")

    def remove_pvs(self, pv_list):
        """
        Remove all SnapshotPv objects for PVs in list.

        :param pv_list: List of PV names.

        :return:
        """

        # Disconnect pvs from clients and remove from list of PVs.
        for pvname in pv_list:
            if self.pvs.get(pvname, None):
                pv_ref = self.pvs.pop(pvname)
                pv_ref.clear_callbacks()

    def clear_pvs(self):
        self.remove_pvs(list(self.pvs.keys()))

    def save_pvs(self, save_file_path, force=False, symlink_path=None, **kw):
        """
        Get current PV values and save them in file. can also create symlink to the file. If additional metadata should
        be saved, it can be provided as keyword arguments.

        :param save_file_path: Path to save file.
        :param force: Save if not all PVs connected? Not connected PVs values will not be saved in such case.
        :param symlink_path: Path to symlink. If symlink exists it will be replaced.
        :param kw: Will be appended to metadata.

        :return: (action_status, pvs_status)

            action_status: Status of action as ActionStatus type.

            pvs_status:
        """

        # get values of all PVs and save them to file
        # All other parameters (packed in kw) are appended to file as meta data

        pvs_status = {}
        disconn_pvs = self.get_disconnected_pvs_names()
        # At this point core can provide not connected status for PVs from
        # self.get_disconnected_pvs_names()
        for pvname in disconn_pvs:
            pvs_status[pvname] = PvStatus.access_err

        # Try to save
        if not force and disconn_pvs:
            return ActionStatus.no_conn, pvs_status

        # Update metadata
        kw["save_time"] = time.time()
        kw["req_file_name"] = os.path.basename(self.req_file_path)

        background_workers.suspend()
        pvs_data = {}
        logging.debug("Create snapshot for %d channels" %
                      len(self.pvs.items()))
        for pvname, pv_ref in self.pvs.items():
            # Get current value, status of operation.
            value, status = pv_ref.save_pv()

            # Make data structure with data to be saved
            pvs_status[pvname] = status
            pvs_data[pvname] = OrderedDict()
            pvs_data[pvname]['raw_name'] = pv_ref.pvname
            if status == PvStatus.ok or pv_ref.initialized:
                pvs_data[pvname]['val'] = value
            else:
                pvs_data[pvname]['val'] = None

        logging.debug("Writing snapshot to file")
        try:
            parse_to_save_file(
                pvs_data,
                save_file_path,
                self.macros,
                symlink_path,
                **kw)
            status = ActionStatus.ok
        except OSError:
            status = ActionStatus.os_error
        logging.debug("Snapshot done")
        background_workers.resume()

        return status, pvs_status

    def restore_pvs(self, pvs_raw, force=False,
                    callback=None, custom_macros=None):
        """
        Restore PVs form snapshot file or dictionary. If restore is successfully started (ActionStatus.ok returned),
        then restore stressfulness will be returned in callback as: status={'pvname': PvStatus}, forced=was_restore?

        :param pvs_raw: Can be a dict of {'pvname': 'saved value'} or a path to a .snap file
        :param force: Force restore if not all needed PVs are connected?
        :param callback: Callback which will be called when all PVs are restored.
        :param custom_macros: This macros are used only if there is no self.macros and not a .snap file.

        :return: (action_status, pvs_status)

            action_status: Status of action as ActionStatus type.

            pvs_status: Dict of {'pvname': PvStatus}. Has meaningful content only in case of action_status == no_conn.
                        In other cases, pvs_status is returned in callback.
        """
        # Check if busy
        if self._restore_started:
            # Cannot do a restore, previous not finished
            return ActionStatus.busy

        self._restore_started = True
        self._current_restore_forced = force

        # Prepare restore data
        if custom_macros is None:
            custom_macros = {}

        if isinstance(pvs_raw, str):
            pvs_raw, meta_data, err = parse_from_save_file(pvs_raw)
            # if no self.macros use ones from file
            custom_macros = meta_data.get('macros', dict())

        pvs = {}

        macros = self.macros or custom_macros
        if macros:
            # Replace macros
            for pvname_raw, pv_data in pvs_raw.items():
                pvs[SnapshotPv.macros_substitution(
                    pvname_raw, macros)] = pv_data
        else:
            pvs = pvs_raw

        # Do restore
        if not pvs:
            # Nothing to restore
            self._restore_started = False
            return ActionStatus.no_data, dict()

        # Standard restore (restore all)
        # If force=True, then do restore even if not all PVs are connected.

        disconn_pvs = self.get_disconnected_pvs_names(pvs)
        # At this point core can provide not connected status for PVs from self.get_disconnected_pvs_names()
        # Should be dict to follow the same format of error reporting ass
        # save_pvs
        pvs_status = {pvname: PvStatus.access_err for pvname in disconn_pvs}
        if not force and disconn_pvs:
            self._restore_started = False
            return ActionStatus.no_conn, pvs_status

        # Do a restore. It is started here, but is completed
        # in _check_restore_complete()
        background_workers.suspend()
        self.restored_pvs_list = []
        self.restore_callback = callback
        for pvname, pv_ref in self.pvs.items():
            save_data = pvs.get(pvname)  # Check if this pv is to be restored
            if save_data:
                pv_ref.restore_pv(save_data.get('value', None),
                                  callback=self._check_restore_complete)
            else:
                # pv is not in subset in the "selected only" mode checking
                # algorithm should think this one was successfully restored
                self._check_restore_complete(pvname, PvStatus.ok)

        # PVs status will be returned in callback
        return ActionStatus.ok, dict()

    def _check_restore_complete(self, pvname, status, **kw):
        # Collect all results and proceed when everything is done
        self.restored_pvs_list.append((pvname, status))
        if len(self.restored_pvs_list) == len(self.pvs):
            if self.restore_callback:
                self.restore_callback(status=dict(self.restored_pvs_list),
                                      forced=self._current_restore_forced)
                self.restore_callback = None
            self._restore_started = False
            background_workers.resume()

    def restore_pvs_blocking(
            self, pvs_raw=None, force=False, timeout=10, custom_macros=None):
        """
        Similar as restore_pvs, but block until restore finished or timeout.

        :param pvs_raw: Can be a dict of {'pvname': 'saved value'} or a path to a .snap file
        :param force: Force restore if not all needed PVs are connected?
        :param custom_macros: This macros are used only if there is no self.macros and not a .snap file.
        :param timeout: Timeout in seconds.

        :return: (action_status, pvs_status)

            action_status: Status of action as ActionStatus type.

            pvs_status: Dict of {'pvname': PvStatus}.

        """
        self._restore_blocking_done = False
        self._blocking_restore_pvs_status = {}
        status, pvs_status = self.restore_pvs(
            pvs_raw, force=force, custom_macros=custom_macros,
            callback=self._set_restore_blocking_done)
        if status != ActionStatus.ok:
            return status, pvs_status

        end_time = time.time() + timeout
        while not self._restore_blocking_done and time.time() < end_time:
            time.sleep(0.2)

        if self._restore_blocking_done:
            return ActionStatus.ok, self._blocking_restore_pvs_status
        else:
            return ActionStatus.timeout, pvs_status

    def _set_restore_blocking_done(self, status, forced):
        # If this was called, then restore is done
        self._restore_blocking_done = True
        self._blocking_restore_pvs_status = status

    def get_pvs_names(self):
        """
        Get list of SnapshotPvs

        :return: List of SnapshotPvs.
        """
        # To access a list of all pvs that are under control of snapshot object
        return list(self.pvs.keys())

    def get_disconnected_pvs_names(self, selected=None):
        """
        Get list off all currently disconnected PVs from all snapshot PVs (default) or from list of "selected" PVs.

        :param selected: List of PVs to check.

        :return: List of not connected PV names.
        """
        if selected is None:
            selected = []

        not_connected_list = []
        for pvname, pv_ref in self.pvs.items():
            if not pv_ref.connected and ((pvname in selected) or not selected):
                # Need to check only subset (selected) of pvs?
                not_connected_list.append(pvname)
        return not_connected_list

    def replace_metadata(self, save_file_path, metadata):
        """
        Reopen save data and replace meta data.

        :param save_file_path: Path to save file.
        :param metadata: Dict with new metadata.

        :return:
        """
        # Will replace metadata in the save file with the provided one

        with open(save_file_path, 'r') as save_file:
            lines = save_file.readlines()
            if lines[0].startswith('#'):
                lines[0] = "#" + json.dumps(metadata) + "\n"
            else:
                lines.insert(0, "#" + json.dumps(metadata) + "\n")

            with open(save_file_path, 'w') as save_file_write:
                save_file_write.writelines(lines)
