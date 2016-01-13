#!/usr/bin/env python
from epics import *
import os
import numpy
import json
from enum import Enum

# On Python 3.5.1 :: Anaconda 2.4.1 (64-bit) with pyepics 3.2.5 there is an
# error epics.ca.ChannelAccessException: loading Epics CA DLL failed
# ../lib/libreadline.so.6: undefined symbol: PC
# Importing readline module solves the problem
#import readline

#
# numpy.array_repr(ha)
# 'array([4, 6, 6], dtype=int32)'
# numpy.fromstring("1,2,4,5",dtype=float, sep=',')



# Subclass PV to be to later add info if needed
class SnapshotPv(PV):
    def __init__(self, pvname, **kw):
        PV.__init__(self, pvname,
                    connection_callback=self.connection_callback_pvt,
                    auto_monitor=True, connection_timeout=1, **kw)
        self.connection_lost = not self.connected
        self.value_to_save = None
        self.saved_value = None  # This holds value from last loaded save file
        self.callback_id = None
        self.last_compare = None
        self.is_array = False

    def connection_callback_pvt(self, conn, **kw):
        # PV layer of pyepics handles arrays strange. In case of having a
        # waveform with NORD field "1" it will not interpret it as array.
        # Instead of "count" (NORD) it should use "nelm", but this also acts
        # wrong. It simply does if count == 1 then nelm = 1. The true NELM info
        # can be found with ca.element_count(self.chid).
        self.is_array = (ca.element_count(self.chid) > 1)

        # Because snapshot, must be also updated when connection is lost,
        # and  one callback per pv is used in snapshot, lost of connection
        # must execute callbacks.
        # Callbacks need info about connection status but self.connected
        # is updated after connection callbacks are called, store it in
        # separate variable
        self.connection_lost = not conn

        if not conn:
            self.run_callbacks()


class Snapshot():
    def __init__(self, req_file_path, macros=None, **kw):
        # Hold a dictionary for each PV (key=pv_name) with reference to
        # SnapshotPv object.
        self.pvs = dict()
        self.compare_state = False
        self.restore_values_loaded = False

        # Uses default parsing method. If other format is needed, subclass
        # and re implement parse_req_file method. It must return list of
        # PV names.
        self.add_pvs(self.parse_req_file(req_file_path, macros))

    def add_pvs(self, file_list):
        # pyepics will handle PVs to have only one connection per PV.

        for pv_name in file_list:
            if not self.pvs.get(pv_name):
                self.pvs[pv_name] = SnapshotPv(pv_name)

    def save_pvs(self, save_file_path, **kw):
        # get value of all PVs and save them to file
        # All other parameters (packed in kw) are appended to file as meta data
        status = dict()
        kw["save_time"] = time.time()
        for key in self.pvs:
            pv_ref = self.pvs[key]
            pv_status = True
            # If connected get value. Do not wait for a connection if not
            if pv_ref.connected:
                pv_ref.value_to_save = pv_ref.get(use_monitor=True)
                if pv_ref.is_array and numpy.size(pv_ref.value_to_save) == 0:
                    # If empty array is equal to None scalar value
                    pv_ref.value_to_save = None

                if (pv_ref.value is not None) or (not pv_ref.write_access):
                    pv_status = False
                else:
                    pv_status = True
            else:
                pv_ref.value_to_save = None
                pv_status = False

            status[key] = pv_status
        self.parse_to_save_file(save_file_path, **kw)
        return(status)

    def prepare_pvs_to_restore_from_file(self, save_file_path):
        # Parsers the file and loads value to corresponding objects
        # Can be later used for compare and restore

        saved_pvs, meta_data = self.parse_from_save_file(save_file_path)
        self.prepare_pvs_to_restore_from_list(saved_pvs)

    def prepare_pvs_to_restore_from_list(self, saved_pvs):
        if self.compare_state:
            self.stop_continous_compare()
            self.compare_state = True  # keep old info to start at the end

        # Loads pvs that were previously parsed from saved file
        for key in self.pvs:
            pv_ref = self.pvs[key]
            saved_pv = saved_pvs.get(key, None)
            if saved_pv is not None:
                    pv_ref.saved_value = saved_pv['pv_value']
            else:
                # Clear PVs that are not defined in save file to avoid
                # restoring values from old file if PV was not in last file
                pv_ref.saved_value = None

        self.restore_values_loaded = True

        # run compare again and do initial compare
        if self.compare_state:
            self.start_continous_compare(self.callback_func)

    def restore_pvs(self, save_file_path=None):
        # If file with saved values specified then read file. If no file
        # then just use last stored values
        status = dict()
        if save_file_path:
            self.prepare_pvs_to_restore_from_file(save_file_path)

        # Compare and restore only different
        put_started = list()
        for key in self.pvs:
            pv_status = True
            pv_ref = self.pvs[key]

            saved_value = self.pvs[key].saved_value

            if pv_ref.connected and (pv_ref.saved_value is not None):
                # compare  different for arrays)
                if pv_ref.is_array:
                    compare = numpy.array_equal(pv_ref.value, pv_ref.saved_value)
                else:
                    compare = (pv_ref.value == pv_ref.saved_value)

                if not compare:
                    if isinstance(pv_ref.saved_value, (str)):
                        # Convert to bytes any string type value.
                        # Python3 distinguish between bytes and strings but pyepics
                        # passes string without conversion since it was not needed for
                        # Python2 where strings are bytes
                        pv_ref.put(str.encode(pv_ref.saved_value),
                                   wait=False, use_complete=True)
                    else:
                        pv_ref.put(pv_ref.saved_value,
                                   wait=False, use_complete=True)
                    put_started.append(pv_ref)
            # Make all Flase, when put done it will be set to true
            status[key] = False

        waiting = True
        while waiting:
            # waiting for puts
            time.sleep(0.001)
            for pv in put_started:
                waiting = not all([pv.put_complete for pv in put_started])

        return(status)

    def start_continous_compare(self, callback=None, save_file_path=None):
        self.callback_func = callback

        # If file with saved values specified then read file. If no file
        # then just use last stored values
        if save_file_path:
            self.load_saved_pvs(save_file_path)

        for key in self.pvs:
            pv_ref = self.pvs[key]
            pv_ref.callback_id = pv_ref.add_callback(self.continous_compare)
            #if pv_ref.connected:
                # Send first callbacks for "initial" compare of each PV if
                # already connected.
            self.continous_compare(pvname=pv_ref.pvname, value=pv_ref.value)
        
        self.compare_state = True

    def stop_continous_compare(self):
        for key in self.pvs:
            pv_ref = self.pvs[key]
            if pv_ref.callback_id:
                pv_ref.remove_callback(pv_ref.callback_id)

        self.compare_state = False

    def continous_compare(self, pvname=None, value=None, **kw):
        # This is callback function
        # Use "connection_lost" instead of "connected", because it is
        # updated before (to get proper value in case of connection lost)
        pv_ref = self.pvs.get(pvname, None)

        # in case of empty array pyepics does not return
        # numpy.ndarray but instance of
        # <class 'epics.dbr.c_int_Array_0'>
        # Check if in this case saved value is None (empty array)
        if pv_ref.is_array and not isinstance(value, (numpy.ndarray)):
            value = None  # return None in callback

        if pv_ref:
            if not self.restore_values_loaded:
                # no old data was loaded clear compare
                pv_ref.last_compare = None
            elif pv_ref.connection_lost:
                pv_ref.last_compare = None
                value = None
            else:
                # compare  value (different for arrays)
                if pv_ref.is_array:
                    compare = numpy.array_equal(value, pv_ref.saved_value)
                else:
                    compare = (value == pv_ref.saved_value)

                pv_ref.last_compare = compare
                
            if self.callback_func:
                self.callback_func(pv_name=pvname, pv_value=value,
                                   pv_saved=pv_ref.saved_value,
                                   pv_compare=pv_ref.last_compare,
                                   pv_cnct_sts=not pv_ref.connection_lost,
                                   saved_sts=self.restore_values_loaded)

    def get_pvs_names(self):
        # To access a list of all pvs that are under control of snapshot object
        return self.pvs.keys()

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
                    pv_name = self.macros_substitutuion(pv_name, macros)

                req_pvs.append(pv_name)

        req_file.close()
        return(req_pvs)

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
            if pv_ref.value_to_save is not None:
                if pv_ref.is_array:
                    save_file.write(key + ";" + json.dumps(pv_ref.value_to_save.tolist()) + "\n")
                else:
                    save_file.write(key + ";" + json.dumps(pv_ref.value_to_save) + "\n")
            else:
                save_file.write(key + "\n")
        save_file.close

    def parse_from_save_file(self, save_file_path):
    #    # This function is called in compare function.
    #    # This is a parser which has a desired value fro each PV.
    #    # To support other format of file, override this method in subclass

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
                split_line = line.strip().split(';')
                pv_name = split_line[0]
                if len(split_line) > 1:
                    pv_value_str = split_line[1]
                    # In case of array it will return a list, otherwise value
                    # of proper type
                    pv_value = json.loads(pv_value_str)

                    if isinstance(pv_value, (list)):
                        # arrays as numpy array, because pyepics returns
                        # as numpy array
                        pv_value = numpy.asarray(pv_value)
                else:
                    pv_value = None

                saved_pvs[pv_name] = dict()
                saved_pvs[pv_name]['pv_value'] = pv_value
        saved_file.close() 
        return(saved_pvs, meta_data)

    def macros_substitutuion(self, string, macros):
        for key in macros:
            macro = "$(" + key + ")"
            string = string.replace(macro, macros[key])
        return string