#!/usr/bin/env python
#
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

import numpy
import json
import os
import time
from enum import Enum

from epics import PV, ca, dbr

from snapshot.core import SnapshotPv, PvStatus
from snapshot.parser import SnapshotReqFile, parse_macros

import logging

ca.AUTO_CLEANUP = True  # For pyepics versions older than 3.2.4, this was set to True only for
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


class Snapshot(object):
    def __init__(self, req_file_path, macros=None):
        """
        Main snapshot class. Provides methods to handle PVs from request or snapshot files and to create, delete, etc
        snap (saved) files

        :param req_file_path: Path to the request file.
        :param macros: macros to be substituted in request file (can be dict {'A': 'B', 'C': 'D'} or str "A=B,C=D").

        :return:
        """

        if isinstance(macros, str):
            macros = parse_macros(macros)  # Raises MacroError in case of problems
        elif macros is None:
            macros = dict()

        # holds path to the req_file_path as this is sort of identifier
        self.req_file_path = os.path.normpath(os.path.abspath(req_file_path))

        self.pvs = dict()
        self.macros = macros

        # Other important states
        self._restore_started = False
        self._restore_blocking_done = False
        self._blocking_restore_pvs_status = dict()
        self._restore_callback = None
        self._current_restore_forced = False

        self.restored_pvs_list = list()
        self.restore_callback = None

        req_f = SnapshotReqFile(self.req_file_path, changeable_macros=list(macros.keys()))
        pvs = req_f.read()

        self.add_pvs(pvs)

    def add_pvs(self, pv_list):
        """
        Creates SnapshotPv objects for each PV in list.

        :param pv_list: List of PV names.

        :return:
        """

        # pyepics will handle PVs to have only one connection per PV.
        # If pv not yet on list add it.
        for pvname_raw in pv_list:

            p_name = SnapshotPv.macros_substitution(pvname_raw, self.macros)
            if not self.pvs.get(p_name):

                pv_ref = SnapshotPv(p_name)

            # if not self.pvs.get(pv_ref.pvname):
                self.pvs[pv_ref.pvname] = pv_ref

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

    def change_macros(self, macros=None):
        """
        Check existing PVs if they have macros in their "raw name". If macros to be replaced remove existing PVs and
        create new PVs.

        :param macros: Dictionary of macros {'macro': 'value' }

        :return:
        """
        macros = macros or {}
        if self.macros != macros:
            self.macros = macros
            pvs_to_change = list()
            pvs_to_remove = list()
            for pvname, pv_ref in self.pvs.items():
                if "$" in pv_ref.pvname_raw:
                    pvs_to_change.append(pv_ref.pvname_raw)
                    pvs_to_remove.append(pvname)

            self.remove_pvs(pvs_to_remove)
            self.add_pvs(pvs_to_change)

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

        pvs_status = dict()
        disconn_pvs = self.get_disconnected_pvs_names()
        # At this point core can provide not connected status for PVs from self.get_disconnected_pvs_names()
        for pvname in disconn_pvs:
            pvs_status[pvname] = PvStatus.access_err

        # Try to save
        if not force and disconn_pvs:
            return ActionStatus.no_conn, pvs_status

        # Update metadata
        kw["save_time"] = time.time()
        kw["req_file_name"] = os.path.basename(self.req_file_path)

        pvs_data = dict()
        logging.debug("Create snapshot for %d channels" % len(self.pvs.items()))
        for pvname, pv_ref in self.pvs.items():
            # Get current value, status of operation.
            value, pvs_status[pvname] = pv_ref.save_pv()

            # Make data structure with data to be saved
            pvs_data[pvname] = dict()
            pvs_data[pvname]['value'] = value
            pvs_data[pvname]['raw_name'] = pv_ref.pvname

        logging.debug("Writing snapshot to file")
        self.parse_to_save_file(pvs_data, save_file_path, self.macros, symlink_path, **kw)
        logging.debug("Snapshot done")

        return ActionStatus.ok, pvs_status

    def restore_pvs(self, pvs_raw, force=False, callback=None, custom_macros=None):
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
            custom_macros = dict()

        if isinstance(pvs_raw, str):
            pvs_raw, meta_data, err = self.parse_from_save_file(pvs_raw)
            custom_macros = meta_data.get('macros', dict())  # if no self.macros use ones from file

        pvs = dict()

        if self.macros:
            macros = self.macros
        else:
            macros = custom_macros

        if macros:
            # Replace macros
            for pvname_raw, pv_data in pvs_raw.items():
                pvs[SnapshotPv.macros_substitution(pvname_raw, macros)] = pv_data
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
        # Should be dict to follow the same format of error reporting ass save_pvs
        pvs_status = dict()
        for pvname in disconn_pvs:
            pvs_status[pvname] = PvStatus.access_err

        if not force and disconn_pvs:
            self._restore_started = False
            return ActionStatus.no_conn, pvs_status

        # Do a restore
        self.restored_pvs_list = list()
        self.restore_callback = callback
        for pvname, pv_ref in self.pvs.items():
            save_data = pvs.get(pvname)  # Check if this pv is to be restored
            if save_data:
                pv_ref.restore_pv(save_data.get('value', None), callback=self._check_restore_complete)
            else:
                # pv is not in subset in the "selected only" mode
                # checking algorithm should think this one was successfully restored
                self._check_restore_complete(pvname, PvStatus.ok)

        # PVs status will be returned in callback
        return ActionStatus.ok, dict()

    def _check_restore_complete(self, pvname, status, **kw):
        self.restored_pvs_list.append((pvname, status))
        if len(self.restored_pvs_list) == len(self.pvs) and self.restore_callback:
            self._restore_started = False
            self.restore_callback(status=dict(self.restored_pvs_list), forced=self._current_restore_forced)
            self.restore_callback = None

    def restore_pvs_blocking(self, pvs_raw=None, force=False, timeout=10, custom_macros=None):
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
        self._blocking_restore_pvs_status = dict()
        status, pvs_status = self.restore_pvs(pvs_raw, force=force, custom_macros=custom_macros,
                                              callback=self._set_restore_blocking_done)
        if status == ActionStatus.ok:
            end_time = time.time() + timeout
            while not self._restore_blocking_done and time.time() < end_time:
                time.sleep(0.2)

            if self._restore_blocking_done:
                return ActionStatus.ok, self._blocking_restore_pvs_status
            else:
                return ActionStatus.timeout, pvs_status
        else:
            return status, pvs_status

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
            selected = list()

        not_connected_list = list()
        for pvname, pv_ref in self.pvs.items():
            if not pv_ref.connected and ((pvname in selected) or not selected):
                not_connected_list.append(pvname)  # Need to check only subset (selected) of pvs?
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

    # Parser functions

    def parse_to_save_file(self, pvs, save_file_path, macros=None, symlink_path=None, **kw):
        """
        This function is called at each save of PV values. This is a parser which generates save file from pvs. All
        parameters in **kw are packed as meta data

        :param pvs: Dict with pvs data to be saved. pvs = {pvname: {'value': value}}
        :param save_file_path: Path of the saved file.
        :param macros: Macros
        :param symlink_path: Optional path to the symlink to be created.
        :param kw: Additional meta data.

        :return:
        """
        # This function is called at each save of PV values.
        # This is a parser which generates save file from pvs
        # All parameters in **kw are packed as meta data

        save_file_path = os.path.abspath(save_file_path)
        save_file = open(save_file_path, 'w')

        # Save meta data
        if macros:
            kw['macros'] = macros
        save_file.write("#" + json.dumps(kw) + "\n")

        for pvname, data in pvs.items():
            value = data.get("value")
            pvname_raw = data.get("raw_name")
            if value is not None:
                if isinstance(value, numpy.ndarray):
                    save_file.write("{},{}\n".format(pvname_raw, json.dumps(value.tolist())))
                else:
                    save_file.write("{},{}\n".format(pvname_raw, json.dumps(value)))
            else:
                save_file.write("{}\n".format(pvname_raw))

        save_file.close()

        # Create symlink _latest.snap
        if symlink_path:
            if os.path.isfile(symlink_path):
                os.remove(symlink_path)

            counter = 5
            while counter > 0:
                no_error = True
                try:
                    os.symlink(save_file_path, symlink_path)
                except:
                    logging.warning("unable to create link")
                    no_error = False

                if no_error:
                    break

                time.sleep(0.5)

                counter -= 1



    @staticmethod
    def parse_from_save_file(save_file_path):
        """
        Parses save file to dict {'pvname': {'data': {'value': <value>, 'raw_name': <name_with_macros>}}}

        :param save_file_path: Path to save file.

        :return: (saved_pvs, meta_data, err)

            saved_pvs: in format {'pvname': {'data': {'value': <value>, 'raw_name': <name_with_macros>}}}

            meta_data: as dictionary

            err: list of strings (each entry one error)
        """

        saved_pvs = dict()
        meta_data = dict()  # If macros were used they will be saved in meta_data
        err = list()
        saved_file = open(save_file_path)
        meta_loaded = False

        for line in saved_file:
            # first line with # is metadata (as json dump of dict)
            if line.startswith('#') and not meta_loaded:
                line = line[1:]
                try:
                    meta_data = json.loads(line)
                except json.JSONDecodeError:
                    # Problem reading metadata
                    err.append('Meta data could not be decoded. Must be in JSON format.')
                meta_loaded = True
            # skip empty lines and all rest with #
            elif line.strip() and not line.startswith('#'):
                split_line = line.strip().split(',', 1)
                pvname = split_line[0]
                if len(split_line) > 1:
                    pv_value_str = split_line[1]
                    # In case of array it will return a list, otherwise value
                    # of proper type
                    try:
                        pv_value = json.loads(pv_value_str)
                    except json.JSONDecodeError:
                        pv_value = None
                        err.append('Value of \'{}\' cannot be decoded. Will be ignored.'.format(pvname))

                    if isinstance(pv_value, list):
                        # arrays as numpy array, because pyepics returns
                        # as numpy array
                        pv_value = numpy.asarray(pv_value)
                else:
                    pv_value = None

                saved_pvs[pvname] = dict()
                saved_pvs[pvname]['value'] = pv_value

        if not meta_loaded:
            err.insert(0, 'No meta data in the file.')

        saved_file.close()
        return saved_pvs, meta_data, err





