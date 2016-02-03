#!/usr/bin/env python
from epics import *
import os
import numpy
import json
from enum import Enum


class PvStatus(Enum):
    access_err = 0
    ok = 1
    not_saved = 2
    equal = 3


class ActionStatus(Enum):
    busy = 0
    ok = 1
    no_data = 2
    no_cnct = 3


# Subclass PV to be to later add info if needed
class SnapshotPv(PV):
    """
    Extended PV class with non-blocking methods to save and restore pvs.
    """

    def __init__(self, pvname, connection_callback=None, **kw):
        PV.__init__(self, pvname,
                    connection_callback=self.internal_cnct_callback,
                    auto_monitor=True, connection_timeout=None, **kw)
        self.cnct_lost = not self.connected
        self.saved_value = None
        self.value_to_restore = None  # This holds value from last loaded save file
        self.compare_callback_id = None
        self.last_compare = None
        self.is_array = False
        self.cnct_callback = connection_callback

    def save_pv(self):
        """
        None blocking save. Takes latest value (monitored). If no connection
        or access simply skips the saving.
        """
        pv_status = PvStatus.ok  # Will be changed if error occurs.
        if self.connected:
            # Must be after connection test. If checking access when not
            # connected pyepics tries to reconnect which takes some time.
            if self.read_access:
                self.saved_value = self.get(use_monitor=True)
                if self.is_array and numpy.size(self.saved_value) == 0:
                    # Empty array is equal to "None" scalar value
                    self.saved_value = None
                if self.value is None:
                    pv_status = PvStatus.not_saved
                else:
                    pv_status = PvStatus.ok
            else:
                pv_status = PvStatus.access_err
        else:
            self.saved_value = None
            pv_status = PvStatus.access_err
        return(pv_status)

    def restore_pv(self, callback=None):
        """
        Executes pv.put of value_to_restore. Success of put is returned
        in callback.
        """

        if self.connected:
            # Must be after connection test. If checking access when not
            # connected pyepics tries to reconnect which takes some time.
            if self.write_access:
                if self.value_to_restore is None:
                    self.verify_restore_response(PvStatus.not_saved, callback)
                else:
                    # compare  different for arrays
                    compare = self.compare(self.value)

                    if not compare:
                        if isinstance(self.value_to_restore, str):
                            # Convert to bytes any string type value.
                            # Python3 distinguish between bytes and strings but pyepics
                            # passes string without conversion since it was not needed for
                            # Python2 where strings are bytes
                            put_value = str.encode(self.value_to_restore)
                        else:
                            put_value = self.value_to_restore

                        self.put(put_value, wait=False, use_complete=True,
                                 callback=self.verify_restore_response,
                                 callback_data={"status": PvStatus.ok,
                                                "callback": callback})
                    else:
                        # No need to be restored.
                        self.verify_restore_response(PvStatus.equal, callback)
            else:
                self.verify_restore_response(PvStatus.access_err, callback)
        else:
            self.verify_restore_response(PvStatus.access_err, callback)

    def verify_restore_response(self, status, callback=None, **kw):
        """
        This method is called for each restore with appropriate status. It
        calls user specified callback.
        """
        if callback:
            callback(pv_name=self.pvname, status=status)

    def set_restore_parameters(self, pv_params):
        """
        Accepts parameters that specify restore. Currently just value in future
        possibility to add dead-band for analogue values, etc
        """
        if pv_params is not None:
            self.value_to_restore = pv_params['pv_value']
        else:
            # Clear params for PVs that is not defined to avoid restoring
            # values from old configurations
            self.value_to_restore = None

    def compare(self, value):
        if self.is_array:
            compare = numpy.array_equal(value, self.value_to_restore)
        else:
            compare = (value == self.value_to_restore)

        return compare

    def internal_cnct_callback(self, conn, **kw):
        """
        Snapshot specific handling of connection status on connection callback.
        """

        # PV layer of pyepics handles arrays strange. In case of having a
        # waveform with NORD field "1" it will not interpret it as array.
        # Instead of native "pv.count" (NORD) it should use "pv.nelm",
        # but this also acts wrong. It (simply does if count == 1, then
        # nelm = 1.) The true NELM info can be found with
        # ca.element_count(self.chid).
        self.is_array = (ca.element_count(self.chid) > 1)

        # Because snapshot must be updated also when connection is lost,
        # and one callback per pv is used in snapshot, lost of connection
        # must execute callbacks.
        # These callbacks need info about connection status but self.connected
        # is updated after connection callbacks are called. To have this info
        # before store it in self.cnct_lost
        self.cnct_lost = not conn

        # If user specifies his own connection callback, call it here.
        if self.cnct_callback:
            self.cnct_callback(conn=conn, **kw)

        # If connection is lost call all "normal" callbacks, to update
        # the status.
        if not conn:
            self.run_callbacks()


class Snapshot:
    def __init__(self, req_file_path, macros=None, **kw):
        # Hold a dictionary for each PV (key=pv_name) with reference to
        # SnapshotPv object.
        self.pvs = dict()
        self.compare_state = False
        self.restore_values_loaded = False
        self.restore_started = False
        self.all_connected = False
        self.compare_callback = None
        self.restore_callback = None

        # Uses default parsing method. If other format is needed, subclass
        # and re implement parse_req_file method. It must return list of
        # PV names.
        self.add_pvs(self.parse_req_file(req_file_path, macros))

    def add_pvs(self, file_list):
        # pyepics will handle PVs to have only one connection per PV.

        for pv_name in file_list:
            if not self.pvs.get(pv_name):
                self.pvs[pv_name] = SnapshotPv(pv_name,
                                               connection_callback=self.update_all_connected_status)

    def save_pvs(self, save_file_path, force=False, **kw):
        # get value of all PVs and save them to file
        # All other parameters (packed in kw) are appended to file as meta data
        pvs_status = dict()
        if not force and not self.all_connected:
            return(ActionStatus.no_cnct, pvs_status)

        kw["save_time"] = time.time()
        for key in self.pvs:
            pvs_status[key] = self.pvs[key].save_pv()
        self.parse_to_save_file(save_file_path, **kw)
        return(ActionStatus.ok, pvs_status)

    def prepare_pvs_to_restore_from_file(self, save_file_path):
        # Parsers the file and loads value to corresponding objects
        # Can be later used for compare and restore

        saved_pvs, meta_data = self.parse_from_save_file(save_file_path)
        self.prepare_pvs_to_restore_from_list(saved_pvs)

    def prepare_pvs_to_restore_from_list(self, saved_pvs):
        # Disable compare for the time of loading new restore value
        if self.compare_state:
            callback = self.compare_callback
            self.stop_continuous_compare()
            self.compare_state = True  # keep old info to restart at the end

        # Loads pvs that were previously parsed from saved file
        for key in self.pvs:
            pv_ref = self.pvs[key]
            pv_ref.set_restore_parameters(saved_pvs.get(key, None))

        self.restore_values_loaded = True

        # run compare again and do initial compare
        if self.compare_state:
            self.start_continuous_compare(callback)

    def restore_pvs(self, save_file_path=None, force=False, callback=None):
        time.sleep(2)
        # If file with saved values specified then read file. If no file
        # then just use last stored values
        if self.restore_started:
            # Cannot do a restore, previous not finished
            return(ActionStatus.busy)

        self.restore_started = True
        if save_file_path:
            self.prepare_pvs_to_restore_from_file(save_file_path)

        if not self.restore_values_loaded:
            # Nothing to restore
            self.restore_started = False
            return(ActionStatus.no_data)

        # If force=True, then do restore even if not all PVs are connected.
        # Default is to abort restore if one is missing

        if not force and not self.all_connected:
            self.restore_started = False
            return(ActionStatus.no_cnct)

        # Do a restore
        self.restored_pvs_list = list()
        self.restore_callback = callback
        for key in self.pvs:
            pv_ref = self.pvs[key]
            pv_ref.restore_pv(callback=self.check_restore_complete)
        return(ActionStatus.ok)

    def check_restore_complete(self, pv_name, status, **kw):
        self.restored_pvs_list.append((pv_name, status))
        if len(self.restored_pvs_list) == len(self.pvs) and self.restore_callback:
            self.restore_started = False
            self.restore_callback(status=dict(self.restored_pvs_list))
            self.restore_callback = None

    def start_continuous_compare(self, callback=None, save_file_path=None):
        self.compare_callback = callback

        # If file with saved values specified then read file. If no file
        # then just use last stored values
        if save_file_path:
            self.load_saved_pvs(save_file_path)

        for key in self.pvs:
            pv_ref = self.pvs[key]
            pv_ref.compare_callback_id = pv_ref.add_callback(self.continuous_compare)
            # if pv_ref.connected:
            #     # Send first callbacks for "initial" compare of each PV if
            #      already connected.
            if pv_ref.connected:
                self.continuous_compare(pvname=pv_ref.pvname,
                                        value=pv_ref.value)
        self.compare_state = True

    def stop_continuous_compare(self):
        self.compare_callback = None
        for key in self.pvs:
            pv_ref = self.pvs[key]
            if pv_ref.compare_callback_id:
                pv_ref.remove_callback(pv_ref.compare_callback_id)

        self.compare_state = False

    def continuous_compare(self, pvname=None, value=None, **kw):
        # This is callback function
        # Uses "cnct_lost" instead of "connected", because it is updated
        # earlier (to get proper value in case of connection lost)
        pv_ref = self.pvs.get(pvname, None)

        # In case of empty array pyepics does not return
        # numpy.ndarray but instance of
        # <class 'epics.dbr.c_int_Array_0'>
        # Check if in this case saved value is None (empty array)
        if pv_ref.is_array and not isinstance(value, numpy.ndarray):
            value = None  # return None in callback
        if pv_ref:
            if not self.restore_values_loaded:
                # no old data was loaded clear compare
                pv_ref.last_compare = None
            elif pv_ref.cnct_lost:
                pv_ref.last_compare = None
                value = None
            else:
                # compare  value (different for arrays)
                pv_ref.last_compare = pv_ref.compare(value)

            if self.compare_callback:
                self.compare_callback(pv_name=pvname, pv_value=value,
                                      pv_saved=pv_ref.value_to_restore,
                                      pv_compare=pv_ref.last_compare,
                                      pv_cnct_sts=not pv_ref.cnct_lost,
                                      saved_sts=self.restore_values_loaded)

    def update_all_connected_status(self, pvname=None, **kw):
        if self.pvs[pvname].cnct_lost:
            self.all_connected = False
        elif not self.all_connected:
            # One of the PVs was reconnected, check if all are connected now.
            connections_ok = True
            for key, pv_ref in self.pvs.items():
                if pv_ref.cnct_lost:
                    connections_ok = False
                    break
            self.all_connected = connections_ok

    def get_pvs_names(self):
        # To access a list of all pvs that are under control of snapshot object
        return list(self.pvs.keys())

    # Parser functions

    def parse_req_file(self, req_file_path, macros=None):
        # This function is called at each initialization.
        # This is a parser for a simple request file which supports macro
        # substitution. Macros are defined as dictionary
        # {'SYS': 'MY-SYS'} will change all $(SYS) macros with MY-SYS
        req_pvs = list()
        req_file = open(req_file_path)
        for line in req_file:
            # skip comments and empty lines
            if not line.startswith('#') and line.strip():
                pv_name = line.rstrip().split(',')[0]
                # Do a macro substitution if macros exist.
                if macros:
                    pv_name = self.macros_substitution(pv_name, macros)

                req_pvs.append(pv_name)

        req_file.close()
        return req_pvs

    def parse_to_save_file(self, save_file_path, **kw):
        # This function is called at each save of PV values.
        # This is a parser which generates save file from pvs
        # All parameters in **kw are packed as meta data
        # To support other format of file, override this method in subclass
        save_file = open(save_file_path, 'w')

        # Save meta data
        save_file.write("#" + json.dumps(kw) + "\n")

        # PVs
        for key in self.pvs:
            pv_ref = self.pvs[key]
            if pv_ref.saved_value is not None:
                if pv_ref.is_array:
                    save_file.write(key + "," + json.dumps(pv_ref.saved_value.tolist()) + "\n")
                else:
                    save_file.write(key + "," + json.dumps(pv_ref.saved_value) + "\n")
            else:
                save_file.write(key + "\n")
        save_file.close

    def parse_from_save_file(self, save_file_path):
        # This function is called in compare function.
        # This is a parser which has a desired value fro each PV.
        # To support other format of file, override this method in subclass

        saved_pvs = dict()
        meta_data = dict()
        saved_file = open(save_file_path)
        meta_loaded = False
        for line in saved_file:
            # first line with # is metadata (as json dump of dict)
            if line.startswith('#') and not meta_loaded:
                line = line[1:]
                meta_data = json.loads(line)
                meta_loaded = True
            # skip empty lines and all rest with #
            elif line.strip() and not line.startswith('#'):
                split_line = line.strip().split(',')
                pv_name = split_line[0]
                if len(split_line) > 1:
                    pv_value_str = split_line[1]
                    # In case of array it will return a list, otherwise value
                    # of proper type
                    pv_value = json.loads(pv_value_str)

                    if isinstance(pv_value, list):
                        # arrays as numpy array, because pyepics returns
                        # as numpy array
                        pv_value = numpy.asarray(pv_value)
                else:
                    pv_value = None

                saved_pvs[pv_name] = dict()
                saved_pvs[pv_name]['pv_value'] = pv_value
        saved_file.close()
        return(saved_pvs, meta_data)

    def macros_substitution(self, string, macros):
        for key in macros:
            macro = "$(" + key + ")"
            string = string.replace(macro, macros[key])
        return string
