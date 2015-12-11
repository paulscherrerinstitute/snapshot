#!/usr/bin/env python
from epics import *
import os

# On Python 3.5.1 :: Anaconda 2.4.1 (64-bit) with pyepics 3.2.5 there is an
# error epics.ca.ChannelAccessException: loading Epics CA DLL failed
# ../lib/libreadline.so.6: undefined symbol: PC
# Importing readline module solves the problem

import readline

# Subclass PV to be to later add info if needed
class SnapshotPv(PV):
    def __init__(self, pvname, auto_monitor=False, **kw):
        PV.__init__(self, pvname, **kw)
        self.value_to_save = None
        self.saved_value = None  # This holds value from last loaded save file
        self.callback_id = None
        self.last_compare = None
        self.last_compare_value = None


class Snapshot():
    def __init__(self, req_file_path, macros=None, **kw):
        # Hold a dictionary for each PV (key=pv_name) with reference to
        # SnapshotPv object.
        self.sr_pvs = dict()

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
            if not self.sr_pvs.get(key):
                self.sr_pvs[key] = SnapshotPv(key)  # this also open connections
                # Handle other config parameters in the future if needed
            else:
                pass  # todo warn

    def save_pvs(self, save_file_path):
        # get value of all PVs and save them to file
        for key in self.sr_pvs:
            pv_value = self.sr_pvs[key].get(count=None,
                                            as_string=True,
                                            use_monitor=False,
                                            timeout=0.1)
            self.sr_pvs[key].value_to_save = pv_value
        self.parse_to_save_file(save_file_path)

    def load_saved_pvs(self, save_file_path):
        # Parsers the file and loads value to corresponding objects
        # Can be later used for compare and restore

        saved_pvs = self.parse_from_save_file(save_file_path)
        for key in self.sr_pvs:
            if self.sr_pvs[key]:
                self.sr_pvs[key].saved_value = saved_pvs[key]['pv_value']
            else:
                # Clear PVs that are not defined in save file to avoid
                # restoring values from old file if PV was not in last file
                self.sr_pvs[key].saved_value = None

    def restore_pvs(self, save_file_path=None):
        # If file with saved values specified then read file. If no file
        # then just use last stored values
        if save_file_path:
            self.load_saved_pvs(save_file_path)

        # Compare and restore only different
        for key in self.sr_pvs:
            pv_value = self.sr_pvs[key].get(count=None,
                                            as_string=True,
                                            use_monitor=False,
                                            timeout=0.1)
            saved_value = self.sr_pvs[key].saved_value

            if (self.sr_pvs[key].connected and
               saved_value != None and
               pv_value != saved_value):
                # Convert to bytes for any string type record
                # Python3 distinguish between bytes and strings but pyepics
                # passes string without conversion since it was not needed for
                # Python2 where strings are bytes
                restore_value = self.sr_pvs[key].saved_value

                # Returned types are something like:
                #time_string
                #time_double
                #time_enum
                if "string" in self.sr_pvs[key].type:
                    restore_value = str.encode(restore_value)
                self.sr_pvs[key].put(restore_value)

    def start_continous_compare(self, callback=None, save_file_path=None):

            self.callback_func = callback
            # If file with saved values specified then read file. If no file
            # then just use last stored values
            if save_file_path:
                self.load_saved_pvs(save_file_path)

            for key in self.sr_pvs:
                pv_ref = self.sr_pvs[key]
                if self.sr_pvs[key].connected:
                    # Do first compare and report "initial" state for each PV
                    # compare char value because saved value string (from file)

                    #pv_ref.last_compare = (pv_ref.get(as_string=True) == pv_ref.saved_value)
                    # Apply monitor to the PV
                    pv_ref.auto_monitor = True
                    pv_ref.callback_id = pv_ref.add_callback(self.continous_compare)

                    # Send first callbacks for "initial" compare of each PV
                    self.continous_compare(pvname=pv_ref.pvname, value=pv_ref.value, char_value=pv_ref.char_value)

    def stop_continous_compare(self, p_var_name, stop_monitoring=False):
        for key in self.sr_pvs:
            pv_ref = self.sr_pvs[key]
            if pv_ref.callbck_id:
                pv_ref.remove_callback(pv_ref.callbck_id)
                if stop_monitoring:
                    pv_ref.auto_monitor = False

    def continous_compare(self, pvname=None, value=None, char_value=None, **kw):
        # This is callback function
        pv_ref = self.sr_pvs[pvname]
        if pv_ref:
            pv_ref.last_compare_value = value

            # compare char value because saved value string (from file)
            pv_ref.last_compare = (char_value == pv_ref.saved_value)
            if self.callback_func:
                self.callback_func(pv_name=pvname, pv_value=value,
                                   pv_saved=pv_ref.saved_value,
                                   pv_compare=pv_ref.last_compare)


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

    def parse_to_save_file(self, save_file_path):
        # This function is called at each save of PV values.
        # This is a parser which generates save file from sr_pvs
        # To support other format of file, override this method in subclass

        save_file = open(save_file_path, 'w')
        
        for key in self.sr_pvs:
            if self.sr_pvs[key].value_to_save:
                save_file.write(key + "," + self.sr_pvs[key].value_to_save + "\n")
            else:
                save_file.write(key + "\n")

        save_file.close

    def parse_from_save_file(self, save_file_path):
        # This function is called in compare function.
        # This is a parser which has a desired value fro each PV.
        # To support other format of file, override this method in subclass

        saved_pvs = dict()
        saved_file = open(save_file_path)
        for line in saved_file:
            # skip comments and empty lines
            if not line.startswith('#') or not line.strip():
                split_line = line.rstrip().split(',')
                pv_name = split_line[0]
                if len(split_line) > 1:
                    pv_value = split_line[1]
                else:
                    pv_value = None

            saved_pvs[pv_name] = dict()
            saved_pvs[pv_name]['pv_value'] = pv_value

        saved_file.close() 
        return(saved_pvs)

    def macros_substitutuion(self, string, macros):
        for key in macros:
            macro = "$(" + key + ")"
            string = string.replace(macro, macros[key])
        return string