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
import readline


def value_to_str(value, char_value, pv_type, connected, is_array):
    # Use different string presentation that "char_value" offers  
    if value is not None:
        if "enum" in pv_type:
            # for boolean types (like "bi" record) store the numerical state
            # to avoid mismatch if string representation (ONAM, ZNAM) changes
            # existing "char_value" holds ONAM or ZNAM.
            return(str(value))
        elif is_array:
            # For arrays use json for easier formating
            return(json.dumps(value.tolist()))
        else:
            return(char_value)
    else:
        return(None)

# Subclass PV to be to later add info if needed
class SnapshotPv(PV):
    def __init__(self, pvname, **kw):
        PV.__init__(self, pvname, connection_callback=self.connection_callback_pvt, callback=self.callback_pvt, auto_monitor=True, **kw)
        self.value_to_save = None
        self.saved_value = None  # This holds value from last loaded save file
        self.callback_id = None
        self.last_compare = None
        self.last_compare_value = None
        self.is_array = False
        # String representation for snapshot (original char_value has problems)
        self.str_value = None

    def connection_callback_pvt(self, **kw):
        # PV layer of pyepics handles arrays strange. In case of having a
        # waveform with NORD field "1" it will not interpret it as array.
        # Instead of "count" (NORD) it should use "nelm", but this also acts
        # wrong. It simply does if count == 1 then nelm = 1. The true NELM info
        # can be found with ca.element_count(self.chid).
        self.is_array = (ca.element_count(self.chid) > 1)

    def callback_pvt(self, **kw):
        # On each change make a string representation of data (also arrays)
        self.str_value = value_to_str(self.value, self.char_value, self.type,
                                      self.connected, self.is_array)

    def get_snap_pv(self, **kw):
        self.get(**kw)
        return(value_to_str(self.value, self.char_value, self.type,
                            self.connected, self.is_array))

    def put_snap_pv(self, value, **kw):
        # If array, use json to decode
        if self.is_array:
            self.put(json.loads(value))
        else:
            self.put(value)


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

    def add_pvs(self, config):
        # pyepics will handle PVs to have only one connection per PV.
        # If one PV is specified more than once but with different config
        # (might be relevant in the future) only first configuration is used.
        # config must be a dict, which keys are PV names

        for key in config:
            if not self.pvs.get(key):
                self.pvs[key] = SnapshotPv(key)  # this also open connections
                # Handle other config parameters in the future if needed
            else:
                pass  # todo warn

    def save_pvs(self, save_file_path, **kw):
        # get value of all PVs and save them to file
        # All other parameters (packed in kw) are appended to file as meta data
        status = dict()
        for key in self.pvs:
            pv_status = True
            pv_value = self.pvs[key].get_snap_pv(count=None, use_monitor=False,
                                                 timeout=0.1)
            self.pvs[key].value_to_save = pv_value
            if not pv_value or not self.pvs[key].connected or \
               self.pvs[key].write_access:

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
        # Loads pvs that were previously parsed from saved file
        for key in self.pvs:
            if key in saved_pvs:
                self.pvs[key].saved_value = saved_pvs[key]['pv_value']
            else:
                # Clear PVs that are not defined in save file to avoid
                # restoring values from old file if PV was not in last file
                self.pvs[key].saved_value = None

        self.restore_values_loaded = True
        # If continuous compare is on then compare must be done and callbacks
        # must be sent TODO make a better reset of saved files
        if self.compare_state:
            self.stop_continous_compare()
            self.start_continous_compare(self.callback_func)

    def restore_pvs(self, save_file_path=None):
        # If file with saved values specified then read file. If no file
        # then just use last stored values
        status = dict()
        if save_file_path:
            self.prepare_pvs_to_restore_from_file(save_file_path)

        # Compare and restore only different
        for key in self.pvs:
            pv_status = True
            pv_value = self.pvs[key].get_snap_pv(count=None, use_monitor=False,
                                                 timeout=0.1)

            saved_value = self.pvs[key].saved_value
            if (self.pvs[key].connected and saved_value != None and
               pv_value != saved_value):
                # Convert to bytes for any string type record
                # Python3 distinguish between bytes and strings but pyepics
                # passes string without conversion since it was not needed for
                # Python2 where strings are bytes
                restore_value = saved_value
                # Returned types are something like:
                #time_string
                #time_double
                #time_enum
                if "string" in self.pvs[key].type:
                    restore_value = str.encode(restore_value)
                self.pvs[key].put_snap_pv(restore_value)
            # Error checking
            if (self.pvs[key].connected) and (self.pvs[key].write_access) and \
               (self.pvs[key].read_access):
                pv_status = False

            status[key] = pv_status
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
            if pv_ref.connected:
                # Send first callbacks for "initial" compare of each PV if
                # already connected.
                self.continous_compare(pvname=pv_ref.pvname,
                                       value=pv_ref.value,
                                       char_value=pv_ref.char_value)
        
        self.compare_state = True

    def get_clbk(self):
        for key in self.pvs:
            pv_ref = self.pvs[key]

    def stop_continous_compare(self):
        for key in self.pvs:
            pv_ref = self.pvs[key]
            if pv_ref.callback_id:
                pv_ref.remove_callback(pv_ref.callback_id)

        self.compare_state = False

    def continous_compare(self, pvname=None, value=None, char_value=None, **kw):
        # This is callback function
        status = "ok"
        pv_ref = self.pvs[pvname]

        str_value = value_to_str(value, char_value, pv_ref.type,
                                 pv_ref.connected, pv_ref.is_array)
        if pv_ref:
            pv_ref.last_compare_value = value

            if not self.restore_values_loaded:
                # nothing to compare
                pv_ref.last_compare = None
                status = "nothing_to_compare"
            elif not pv_ref.connected:
                pv_ref.last_compare = None
                status = "not_connected"
            else:
                # compare char value because saved value is string (from file)
                pv_ref.last_compare = (str_value == pv_ref.saved_value)
            
            if self.callback_func:
                self.callback_func(pv_name=pvname, pv_value=value,
                                   pv_value_str=str_value,
                                   pv_saved=pv_ref.saved_value,
                                   pv_compare=pv_ref.last_compare,
                                   pv_status=status)

    def get_pvs_names(self):
        # To access a list of all pvs that are under control of snapshot object
        return self.pvs.keys()

## Parsers

    def parse_req_file(self, req_file_path, macros=None):
        # This function is called at each initialization.
        # This is a parser for a simple request file which supports macro
        # substitution. Macros are defined as dictionary
        # {'SYS': 'MY-SYS'} will change all $(SYS) macros with MY-SYS
        req_pvs = dict()
        req_file = open(req_file_path)
        for line in req_file:
            # skip comments and empty lines
            if not line.startswith('#') or not line.strip():
                pv_name = line.rstrip().split(',')[0]
                # Do a macro substitution if macros exist.
                if macros:
                    pv_name = self.macros_substitutuion(pv_name, macros)

                # For each pv_name create empty dict(). In future more powerful
                # req files might be supported, and parameters will be then
                # packed as dictionary for each PV
                req_pv = dict()
                req_pvs[pv_name] = req_pv

        req_file.close()
        return(req_pvs)

    #def parse_to_save_file(self, save_file_path, **kw):
    #    # This function is called at each save of PV values.
    #    # This is a parser which generates save file from pvs
    #    # All parameters in **kw are packed as meta data
    #    # To support other format of file, override this method in subclass
    #
    #    save_file = open(save_file_path, 'w')
    #    
    #    # Meta data
    #    for key in kw:
    #        save_file.write("#" + key + ":" + kw[key] + "\n")
    #
    #    # PVs
    #    for key in self.pvs:
    #       if self.pvs[key].value_to_save:
    #           save_file.write(key + "," + self.pvs[key].value_to_save + "\n")
    #       else:
    #           save_file.write(key + "\n")
    #
    #    save_file.close


    def parse_to_save_file(self, save_file_path, **kw):
        # This function is called at each save of PV values.
        # This is a parser which generates save file from pvs
        # All parameters in **kw are packed as meta data
        # To support other format of file, override this method in subclass
    
        save_file = open(save_file_path, 'w')
        
        file_content = dict()
        # Meta data is everything in kw
        file_content["metadata"] = kw
        
    
        # PVs
        pvs_to_file = dict()
        for key in self.pvs:
            pvs_to_file[key] = self.pvs[key].value_to_save

        file_content["data"] = pvs_to_file
        json.dump(file_content, save_file)
        save_file.close

    #def parse_from_save_file(self, save_file_path):
    #    # This function is called in compare function.
    #    # This is a parser which has a desired value fro each PV.
    #    # To support other format of file, override this method in subclass

    #    saved_pvs = dict()
    #    meta_data = dict()
    #    saved_file = open(save_file_path)
    #    for line in saved_file:
    #        if line.startswith('#'):
    #            split_line = line.rstrip().split(':')
    #            meta_data[split_line[0].split("#")[1]] = split_line[1]
    #        # skip empty lines
    #        elif line.strip():
    #            split_line = line.rstrip().split(',')
    #            pv_name = split_line[0]
    #            if len(split_line) > 1:
    #                pv_value = split_line[1]
    #            else:
    #                pv_value = None

    #            saved_pvs[pv_name] = dict()
    #            saved_pvs[pv_name]['pv_value'] = pv_value

    #    saved_file.close() 
    #    return(saved_pvs, meta_data)

    def parse_from_save_file(self, save_file_path):
        # This function is called in compare function.
        # This is a parser which has a desired value fro each PV.
        # To support other format of file, override this method in subclass

        saved_pvs = dict()
        meta_data = dict()
        saved_file = open(save_file_path)
        file_content = json.load(saved_file)
        
        meta_data = file_content["metadata"]

        for key in file_content["data"]:
            saved_pvs[key] = dict()
            saved_pvs[key]['pv_value'] = file_content["data"][key]

        saved_file.close() 
        return(saved_pvs, meta_data)

    def macros_substitutuion(self, string, macros):
        for key in macros:
            macro = "$(" + key + ")"
            string = string.replace(macro, macros[key])
        return string