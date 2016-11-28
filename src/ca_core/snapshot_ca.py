#!/usr/bin/env python
#
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

from epics import *

ca.AUTO_CLEANUP = True  # For pyepics versions older than 3.2.4, this was set to True only for
# python 2 but not for python 3, which resulted in errors when closing
# the application. If true, ca.finalize_libca() is called when app is
# closed
import numpy
import json
import re
import time
import os
from enum import Enum


class PvStatus(Enum):
    access_err = 0
    ok = 1
    no_value = 2
    equal = 3


class ActionStatus(Enum):
    busy = 0
    ok = 1
    no_data = 2
    no_conn = 3
    timeout = 4


def macros_substitution(txt:str, macros):
    for key, value in macros.items():
        macro = "$(" + key + ")"
        txt = txt.replace(macro, value)

    return txt


##
# Subclass PV to be to later add info if needed
class SnapshotPv(PV):
    """
    Extended PV class with non-blocking methods to save and restore pvs.
    """

    def __init__(self, pvname, macros=None, connection_callback=None, **kw):
        # Store the origin
        self.pvname_raw = pvname
        self.macros = macros

        if macros:
            pvname = SnapshotPv.macros_substitution(pvname, macros)

        self.cnct_callback = connection_callback
        self.is_array = False

        super().__init__(pvname, connection_callback=self._internal_cnct_callback, auto_monitor=True,
                         connection_timeout=None, **kw)

    def save_pv(self):
        """
        None blocking get. Returns latest value (monitored). If not able to get value (no connection or access),
        'None' is returned.
        """
        if self.connected:
            # Must be after connection test. If checking access when not
            # connected pyepics tries to reconnect which takes some time.
            if self.read_access:
                saved_value = self.get(use_monitor=True)
                if self.is_array:
                    if numpy.size(saved_value) == 0:
                        # Empty array is equal to "None" scalar value
                        saved_value = None
                    elif numpy.size(saved_value) == 1:
                        # make scalars as arrays
                        saved_value = numpy.asarray([saved_value])

                if self.value is None:
                    return saved_value, PvStatus.no_value
                else:
                    return saved_value, PvStatus.ok
            else:
                return None, PvStatus.access_err
        else:
            return None, PvStatus.access_err

    def restore_pv(self, value, callback=None):
        """
        Executes asyn pv.put if value is different to current value. Success of put is returned in callback.
        :param value: value to be put to pv
        :param callback: callback function in which success of restoring is monitored
        :return:
        """
        if self.connected:
            # Must be after connection test. If checking access when not
            # connected pyepics tries to reconnect which takes some time.
            if self.write_access:
                if value is None:
                    callback(pvname=self.pvname, status=PvStatus.no_value)

                elif not self.compare_to_curr(value):
                    if isinstance(value, str):
                        # pyepics needs value as bytes not as string
                        value = str.encode(value)

                    self.put(value, wait=False,
                             callback=callback,
                             callback_data={"status": PvStatus.ok})
                elif callback:
                    # No need to be restored.
                    callback(pvname=self.pvname, status=PvStatus.equal)

            elif callback:
                callback(pvname=self.pvname, status=PvStatus.access_err)

        elif callback:
            callback(pvname=self.pvname, status=PvStatus.access_err)

    def compare_to_curr(self, value):
        return SnapshotPv.compare(value, self.value, self.is_array)

    @staticmethod
    def compare(value1, value2, is_array=False):
        if is_array:
            return numpy.array_equal(value1, value2)
        else:
            return value1 == value2

    def add_conn_callback(self, callback):
        self.cnct_callback = callback

    def remove_conn_callback(self):
        self.cnct_callback = None

    def _internal_cnct_callback(self, conn, **kw):
        """
        Snapshot specific handling of connection status on connection callback.
        """

        # PV layer of pyepics handles arrays strange. In case of having a
        # waveform with NORD field "1" it will not interpret it as array.
        # Instead of native "pv.count" (NORD) it should use "pv.nelm",
        # but this also acts wrong. It simply does: if count == 1, then
        # nelm = 1.) The true NELM info can be found with
        # ca.element_count(self.chid).
        self.is_array = (ca.element_count(self.chid) > 1)

        # If user specifies his own connection callback, call it here.
        if self.cnct_callback:
            self.cnct_callback(conn=conn, **kw)

    @staticmethod
    def macros_substitution(string, macros):
        for key in macros:
            macro = "$(" + key + ")"
            string = string.replace(macro, macros[key])
        return string


class Snapshot:
    def __init__(self, req_file_path, macros=None, **kw):
        """
        Main snapshot class. Provides methods to handle PVs from request or snapshot files and to create, delete, etc
        snap (saved) files

        :param req_file_path: path to the request file
        :param macros: macros to be substituted in request file (can be dict or str "A=B,C=D")
        :param snap_file_dir: directory with snapshot files (if snap file is relative, it will be relative to this
        :return:
        """

        if isinstance(macros, str):
            macros = parse_macros(macros) # Raises MacroError in case of problems
        elif macros is None:
            macros = dict()

        # holds path to the req_file_path as this is sort of identifier
        self.req_file_path = os.path.normpath(os.path.abspath(req_file_path))

        self.pvs = dict()
        self.macros = macros

        # Other important states
        self.all_connected = False
        self._restore_started = False
        self._restore_blocking_done = False
        self._restore_callback = None
        self._current_restore_forced = False

        req_f = SnapshotReqFile(self.req_file_path, changeable_macros=macros.keys())
        pvs =  req_f.read()

        self.add_pvs(pvs)

    def add_pvs(self, pv_list):
        # pyepics will handle PVs to have only one connection per PV.
        # If pv not yet on list add it

        for pvname_raw in pv_list:
            pv_ref = SnapshotPv(pvname_raw, self.macros, connection_callback=self.update_all_connected_status)

            if not self.pvs.get(pv_ref.pvname):
                self.pvs[pv_ref.pvname] = pv_ref

    def remove_pvs(self, pv_list):
        # disconnect pvs to avoid unneeded connections
        # and remove from list of pvs

        for pvname in pv_list:
            if self.pvs.get(pvname, None):
                pv_ref = self.pvs.pop(pvname)
                pv_ref.disconnect()

    def change_macros(self, macros=None, **kw):
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

            self.update_all_connected_status()

    def save_pvs(self, save_file_path, force=False, symlink_path=None, **kw):
        # get values of all PVs and save them to file
        # All other parameters (packed in kw) are appended to file as meta data
        pvs_status = dict()
        if not force and not self.all_connected:
            return ActionStatus.no_conn, pvs_status

        # Update metadata
        kw["save_time"] = time.time()
        kw["req_file_name"] = os.path.basename(self.req_file_path)

        pvs_data = dict()
        for pvname, pv_ref in self.pvs.items():
            # Get current value, status of operation
            value, pvs_status[pvname] = pv_ref.save_pv()

            # Make data structure with data to be saved
            pvs_data[pvname] = dict()
            pvs_data[pvname]['value'] = value
            pvs_data[pvname]['raw_name'] = pv_ref.pvname_raw

        self.parse_to_save_file(pvs_data, save_file_path, self.macros, symlink_path, **kw)

        return ActionStatus.ok, pvs_status

    def restore_pvs(self, pvs_raw, force=False, callback=None, custom_macros=None):
        """

        :param pvs_raw: can be a dict of pvs with saved values or a path to a .snap file
        :param force: force restore if not all needed PVs are connected
        :param callback: callback fnc
        :param custom_macros: used only if there is no self.macros and not a .snap file
        :return:
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
            return ActionStatus.no_data

        # Standard restore (restore all)
        # If force=True, then do restore even if not all PVs are connected.
        # If only few PVs are selected, check if needed PVs are connected
        # Default is to abort restore if one is missing

        if not force and (not self.check_pvs_connected_status(pvs)):
            self._restore_started = False
            return ActionStatus.no_conn

        # Do a restore
        self.restored_pvs_list = list()
        self.restore_callback = callback
        for pvname, pv_ref in self.pvs.items():
            save_data = pvs.get(pvname)  # Check if this pv is to be restored
            if save_data:
                pv_ref.restore_pv(save_data.get('value', None), callback=self.check_restore_complete)
            else:
                # pv is not in subset in the "selected only" mode
                # checking algorithm should think this one was successfully restored
                self.check_restore_complete(pvname, PvStatus.ok)
        return ActionStatus.ok

    def check_restore_complete(self, pvname, status, **kw):
        self.restored_pvs_list.append((pvname, status))
        if len(self.restored_pvs_list) == len(self.pvs) and self.restore_callback:
            self._restore_started = False
            self.restore_callback(status=dict(self.restored_pvs_list), forced=self._current_restore_forced)
            self.restore_callback = None

    def restore_pvs_blocking(self, save_file_path=None, force=False, timeout=10):
        self._restore_blocking_done = False
        status = self.restore_pvs(save_file_path, force=force, callback=self.set_restore_blocking_done)
        if status == ActionStatus.ok:
            end_time = time.time() + timeout
            while not self._restore_blocking_done and time.time() < end_time:
                time.sleep(0.2)

            if self._restore_blocking_done:
                return ActionStatus.ok
            else:
                return ActionStatus.timeout
        else:
            return status

    def set_restore_blocking_done(self, status, forced):
        # If this was called, then restore is done
        self._restore_blocking_done = True

    def update_all_connected_status(self, pvname=None, **kw):
        check_all = False
        pv_ref = self.pvs.get(pvname, None)

        if pv_ref is not None:
            if not pv_ref.connected:
                self.all_connected = False
            elif not self.all_connected:
                # One of the PVs was reconnected, check if all are connected now.
                check_all = True
        else:
            check_all = True

        if check_all:
            self.all_connected = self.check_pvs_connected_status()

    def check_pvs_connected_status(self, pvs=None):
        # If not specific list of pvs is given, then check all
        if pvs is None:
            pvs = self.pvs.keys()

        for pv in pvs:
            pv_ref = self.pvs.get(pv)
            if not pv_ref.connected:
                return False

        # If here then all connected
        return True

    def get_pvs_names(self):
        # To access a list of all pvs that are under control of snapshot object
        return list(self.pvs.keys())

    def get_not_connected_pvs_names(self, selected=None):
        if selected is None:
            selected = list()
        if self.all_connected:
            return list()
        else:
            not_connected_list = list()
            for pvname, pv_ref in self.pvs.items():
                if not pv_ref.connected and ((pvname in selected) or not selected):
                    not_connected_list.append(pvname)  # Need to check only subset (selected) of pvs?
            return not_connected_list

    def replace_metadata(self, save_file_path, metadata):
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
        # This function is called at each save of PV values.
        # This is a parser which generates save file from pvs
        # All parameters in **kw are packed as meta data
        # To support other format of file, override this method in subclass
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

            os.symlink(save_file_path, symlink_path)

    @staticmethod
    def parse_from_save_file(save_file_path):
        # This function is called in compare function.
        # This is a parser which has a desired value for each PV.
        # To support other format of file, override this method in subclass
        # Note: This function does not detect if we have a valid save file,
        # or just something that was successfuly parsed

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
                except json.decoder.JSONDecodeError:
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
                    except json.decoder.JSONDecodeError:
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


class SnapshotReqFile(object):
    def __init__(self, path: str, parent=None, macros:dict = None, changeable_macros:list = None):
        '''

        :param path: file path
        :param parent: SnapshotReqFile from which current file was called
        :param macros: dict of macros (keys) and values
        :param changeable_macros: list of "global" macros which can stay unreplaced and will be handled by
                                  Shanpshot object. This macros will be ignored in error handling.
        :return:
        '''
        if macros is None:
            macros = dict()
        if changeable_macros is None:
            changeable_macros = list()

        self._path = os.path.abspath(path)
        self._parent = parent
        self._macros = macros
        self._c_macros = changeable_macros

        if parent:
            self._trace = '{} [line {}: {}] >> {}'.format(parent._trace, parent._curr_line_n, parent._curr_line,
                                                          self._path)
        else:
            self._trace = self._path

        self._curr_line_n = 0
        self._curr_line_txt = ''
        self._err = list()

    def read(self):
        f = open(self._path)

        pvs = list()
        err = list()

        self._curr_line_n = 0
        for self._curr_line in f:
            self._curr_line_n += 1
            self._curr_line = self._curr_line.strip()

            # skip comments and empty lines
            if not self._curr_line.startswith(('#', "data{", "}", "!")) and self._curr_line.strip():
                    # First replace macros, then check if any unreplaced macros which are not "global"
                    pvname = macros_substitution((self._curr_line.rstrip().split(',', maxsplit=1)[0]), self._macros)

                    try:
                        # Check if any unreplaced macros
                        self._validate_macros_in_txt(pvname)
                    except MacroError as e:
                        f.close()
                        raise ReqParseError(self._format_err((self._curr_line_n, self._curr_line), e))

                    pvs.append(pvname)

            elif self._curr_line.startswith('!'):
                # Calling another req file
                split_line = self._curr_line[1:].split(',', maxsplit=1)

                if len(split_line) > 1:
                    macro_txt = split_line[1].strip()
                    if not macro_txt.startswith(('\"', '\'')):
                        f.close()
                        raise ReqFileFormatError(self._format_err((self._curr_line_n, self._curr_line),
                                                                  'Syntax error. Macros argument must be quoted.'))
                    else:
                        quote_type = macro_txt[0]

                    if not macro_txt.endswith(quote_type):
                        f.close()
                        raise ReqFileFormatError(self._format_err((self._curr_line_n, self._curr_line),
                                                                  'Syntax error. Macros argument must be quoted.'))

                    macro_txt = macros_substitution(macro_txt[1:-1], self._macros)
                    try:
                        self._validate_macros_in_txt(macro_txt) # Check if any unreplaced macros
                        macros = parse_macros(macro_txt)

                    except MacroError as e:
                        f.close()
                        raise ReqParseError(self._format_err((self._curr_line_n, self._curr_line), e))

                else:
                    macros = dict()

                path = os.path.join(os.path.dirname(self._path), split_line[0])
                msg = self._check_looping(path)
                if msg:
                    f.close()
                    raise ReqFileInfLoopError(self._format_err((self._curr_line_n, self._curr_line), msg))

                try:
                    sub_f = SnapshotReqFile(path, parent=self, macros=macros)
                    sub_pvs = sub_f.read()
                    pvs += sub_pvs

                except IOError as e:
                    f.close()
                    raise IOError(self._format_err((self._curr_line, self._curr_line_n), e))
        f.close()
        return pvs

    def _format_err(self, line: tuple, msg: str):
        return('{} [line {}: {}]: {}'.format(self._trace, line[0], line[1], msg))

    def _validate_macros_in_txt(self, txt: str):
        invalid_macros = list()
        macro_rgx = re.compile('\$\(.*?\)')  # find all of type $()
        raw_macros = macro_rgx.findall(txt)
        for raw_macro in raw_macros:
            if raw_macro not in self._macros.values() and raw_macro[2:-1] not in self._c_macros:
                #There are unknown macros which were not substituted
                invalid_macros.append(raw_macro)

        if invalid_macros:
            raise MacroError('Following macros were not defined: {}'.format(', '.join(invalid_macros)))

    def _check_looping(self, path):
        path = os.path.normpath(os.path.abspath(path))
        ancestor = self  # eventually could call self again

        while ancestor is not None:
            if os.path.normpath(os.path.abspath(ancestor._path)) == path:
                if ancestor._parent:
                    msg = 'Infinity loop detected. File {} was already called from {}'.format(path,
                                                                                              ancestor._parent._path)
                else:
                    msg = 'Infinity loop detected. File {} was already loaded as root request file.'.format(path)

                return(msg)
            else:
                ancestor = ancestor._parent


# Helper functions functions to support macros parsing for users of this lib
def parse_macros(macros_str):
    """
    Converting comma separated macros string to dictionary.

    :param macros_str: string of macros in style SYS=TST,D=A
    :return: dict of macros
    """

    macros = dict()
    if macros_str:
        macros_list = macros_str.split(',')
        for macro in macros_list:
            split_macro = macro.strip().split('=')
            if len(split_macro) == 2:
                macros[split_macro[0]] = split_macro[1]
            else:
                raise MacroError('Following string cannot be parsed to macros: {}'.format(macros_str))
    return macros


def parse_dict_macros_to_text(macros):
    """
    Converting dict() separated macros string to comma separated.

    :param macros: dict of macros, substitutions
    :return: macro string
    """

    macros_str = ""
    for macro, subs in macros.items():
        macros_str += macro + "=" + subs + ","

    if macros_str:
        # Clear last comma
        macros_str = macros_str[0:-1]

    return macros_str


# Exceptions
class SnapshotError(Exception):
    pass

class MacroError(SnapshotError):
    pass

class ReqParseError(SnapshotError):
    pass

class ReqFileFormatError(ReqParseError):
    pass

class ReqFileInfLoopError(ReqParseError):
    pass