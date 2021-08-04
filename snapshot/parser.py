import glob
import json
import logging
import os
import re
import time
from itertools import chain

import numpy
import yaml

from snapshot.core import SnapshotError, SnapshotPv, global_thread_pool, since_start

save_file_suffix = '.snap'


class SnapshotReqFile(object):
    def __init__(self, path: str, parent=None, macros: dict = None,
                 changeable_macros: list = None):
        """
        Class providing parsing methods for request files.

        :param path: Request file path.
        :param parent: SnapshotReqFile from which current file was called.
        :param macros: Dict of macros {macro: value}
        :param changeable_macros: List of "global" macros which can stay unreplaced and will be handled by
                                  Shanpshot object (enables user to change macros on the fly). This macros will be
                                  ignored in error handling.

        :return:
        """
        if macros is None:
            macros = {}
        if changeable_macros is None:
            changeable_macros = []

        self._path = os.path.abspath(path)
        self._parent = parent
        self._macros = macros
        self._c_macros = changeable_macros

        if parent:
            self._trace = '{} [line {}: {}] >> {}'.format(parent._trace, parent._curr_line_n, parent._curr_line,
                                                          self._path)
        else:
            self._trace = self._path

        self._curr_line = None
        self._curr_line_n = 0
        self._curr_line_txt = ''
        self._err = []
        self._type, self._file_data = self.read_input()

    def read_input(self):
        extension = os.path.splitext(self._path)[1].replace('.','')
        if extension == 'json':
            try:
                content = json.loads(open(self._path, 'r').read())
            except Exception as e:
                msg = f'{self._path}: Could not read load json file.'
                raise ReqParseError(msg, e)
        elif extension in ['yaml', 'yml']:
            # yaml
            try:
                content = yaml.safe_load(open(self._path, 'r'))[0]
            except Exception as e:
                msg = f'{self._path}: Could not safe_load yaml file.'
                raise ReqParseError(msg, e)
        elif extension == 'req':
            try:
                content = open(self._path, 'r').read()
            except Exception as e:
                msg = f'{self._path}: Could not read req file.'
                raise ReqParseError(msg, e)
        return (extension, content)

    def read(self):
        """
        Parse request file and return
          - a list of pv names where changeable_macros are not replaced. ("raw"
            pv names).
          - a dict with metadata from the file.

        In case of problems raises exceptions.
                OSError
                ReqParseError
                    ReqFileFormatError
                    ReqFileInfLoopError

        :return: (pv_names, metadata).
        """
        result = self._read_only_self()
        if not isinstance(result, tuple):
            raise result

        pvs, metadata, includes = result
        while includes:
            results = global_thread_pool.map(lambda f: f._read_only_self(),
                                             includes)
            old_includes = includes
            includes = []
            for result, inc in zip(results, old_includes):
                if not isinstance(result, tuple):
                    raise result
                new_pvs, new_metadata, new_includes = result
                if new_metadata:
                    msg = f"Found metadata in included file {inc._path}; " \
                        "metadata is only allowed in the top-level file."
                    raise ReqParseError(msg)
                pvs += new_pvs
                includes += new_includes

        # In the file, machine_params are stored as an array of
        # key-value pairs to preserve order. Here, we can rely on
        # having an ordered dict.
        try:
            metadata['machine_params'] = \
                dict(metadata.get('machine_params', []))
            if not all(isinstance(x, str) for x in chain.from_iterable(
                    metadata['machine_params'].items())):
                raise ReqParseError
        except Exception:
            return ReqParseError('Invalid format of machine parameter list, '
                                'must be a list of ["name", "pv_name"] pairs.')

        forbidden_chars = " ,.()"
        if any(
            any(char in param for char in forbidden_chars)
            for param in metadata['machine_params']
        ):
            raise ReqParseError('Invalid format of machine parameter list, '
                                'names must not contain space or punctuation.')

        return pvs, metadata

    def _read_only_self(self):
        """
        Parse request file and return a tuple of pvs, metadata and includes.

        In case of problems returns (but does not raise) exceptions.
                OSError
                ReqParseError
                    ReqFileFormatError
                    ReqFileInfLoopError

        :return: A tuple (pv_list, metadata, includes_list)
        """
        includes = []
        pvs = []
        
        if self._type == 'json':
            pvs = self._extract_pvs_from_json()
            try:
                with open(self._path) as f:
                        file_data = f.read()
            except OSError as e:
                return e
            try:
                md = file_data.lstrip()
                metadata, end_of_metadata = \
                    json.JSONDecoder().raw_decode(md)
            except json.JSONDecodeError:
                msg = f"{self._path}: Could not parse JSON metadata header."
                return ReqParseError(msg)
            actual_data = md[end_of_metadata:].lstrip()
            actual_data_index = file_data.find(actual_data)
            self._curr_line_n = len(file_data[:actual_data_index]
                                    .splitlines())
            file_data = file_data[actual_data_index:]
        elif self._type in ['yml', 'yaml']:
            pvs = self._extract_pvs_from_yaml()
            metadata = self._file_data
        elif self._type == 'req':
            metadata = {}
            self._curr_line_n = 0
            for self._curr_line in self._file_data.splitlines():
                self._curr_line_n += 1
                self._curr_line = self._curr_line.strip()

                # skip comments, empty lines and "data{}" stuff
                if not self._curr_line.startswith(('#', "data{", "}", "!")) \
                and self._curr_line.strip():
                    # First replace macros, then check if any unreplaced macros
                    # which are not "global"
                    pvname = SnapshotPv.macros_substitution(
                        (self._curr_line.rstrip().split(',', maxsplit=1)[0]),
                        self._macros)
                    try:
                        # Check if any unreplaced macros
                        self._validate_macros_in_txt(pvname)
                    except MacroError as e:
                        return ReqParseError(self._format_err(
                            (self._curr_line_n, self._curr_line), e))
                    else:
                        pvs.append(pvname)
                elif self._curr_line.startswith('!'):
                    # Calling another req file
                    split_line = self._curr_line[1:].split(',', maxsplit=1)
                    if len(split_line) > 1:
                        macro_txt = split_line[1].strip()
                        if macro_txt.startswith(('\"', '\'')):
                            quote_type = macro_txt[0]
                        else:
                            return ReqFileFormatError(
                                self._format_err(
                                    (self._curr_line_n, self._curr_line),
                                    'Syntax error. Macro argument must be quoted'))
                        if not macro_txt.endswith(quote_type):
                            return ReqFileFormatError(
                                self._format_err(
                                    (self._curr_line_n, self._curr_line),
                                    'Syntax error. Macro argument must be quoted'))
                        macro_txt = SnapshotPv.macros_substitution(
                            macro_txt[1:-1], self._macros)
                        try:
                            # Check for any unreplaced macros
                            self._validate_macros_in_txt(macro_txt)
                            macros = parse_macros(macro_txt)

                        except MacroError as e:
                            return ReqParseError(
                                self._format_err(
                                    (self._curr_line_n, self._curr_line), e))
                    else:
                        macros = {}
                    path = os.path.join(os.path.dirname(self._path), split_line[0])
                    msg = self._check_looping(path)
                    if msg:
                        return ReqFileInfLoopError(
                            self._format_err(
                                (self._curr_line_n, self._curr_line), msg))
                    try:
                        sub_f = SnapshotReqFile(path, parent=self, macros=macros)
                        includes.append(sub_f)

                    except OSError as e:
                        return OSError(
                            self._format_err(
                                (self._curr_line, self._curr_line_n), e))
        return (pvs, metadata, includes)

    def _extract_pvs_from_req(self):
        try:
            list_of_pvs = self._file_data.split('\n')
        except Exception as e:
            return ReqParseError(e)
        else:
            return list_of_pvs
        


    def _extract_pvs_from_yaml(self):
        try:
            list_of_pvs = []
            for ioc_name in self._file_data.keys():
                for pv_name in self._file_data[ioc_name]:
                    list_of_pvs.append(ioc_name+":"+pv_name)
            return list_of_pvs
        except Exception as e:
            msg = f"{self._path}: Could not parse YML file."
            return JsonParseError(msg)

    def _extract_pvs_from_json(self):
        try:
            list_of_pvs = []
            for ioc_name in self._file_data.keys():
                for pv_name in self._file_data[ioc_name]:
                    list_of_pvs.append(ioc_name+":"+pv_name)
            return list_of_pvs
        except Exception as e:
            msg = f"{self._path}: Could not parse Json file."
            return JsonParseError(msg)

    def _format_err(self, line: tuple, msg: str):
        return '{} [line {}: {}]: {}'.format(
            self._trace, line[0], line[1], msg)

    def _validate_macros_in_txt(self, txt: str):
        invalid_macros = []
        macro_rgx = re.compile('\$\(.*?\)')  # find all of type $()
        raw_macros = macro_rgx.findall(txt)
        for raw_macro in raw_macros:
            if raw_macro not in self._macros.values(
            ) and raw_macro[2:-1] not in self._c_macros:
                # There are unknown macros which were not substituted
                invalid_macros.append(raw_macro)

        if invalid_macros:
            raise MacroError(
                'Following macros were not defined: {}'.format(
                    ', '.join(invalid_macros)))

    def _check_looping(self, path):
        path = os.path.normpath(os.path.abspath(path))
        ancestor = self  # eventually could call self again

        while ancestor is not None:
            if os.path.normpath(os.path.abspath(ancestor._path)) == path:
                if ancestor._parent:
                    return 'Infinity loop detected. File {} was already called from {}'.format(
                        path, ancestor._parent._path
                    )
                else:
                    return 'Infinity loop detected. File {} was already loaded as root request file.'.format(
                        path
                    )
            else:
                ancestor = ancestor._parent


# Helper functions functions to support macros parsing for users of this lib
def parse_macros(macros_str):
    """
    Converting comma separated macros string to dictionary.

    :param macros_str: string of macros in style SYS=TST,D=A

    :return: dict of macros
    """

    macros = {}
    if macros_str:
        macros_list = macros_str.split(',')
        for macro in macros_list:
            split_macro = macro.strip().split('=')
            if len(split_macro) == 2:
                macros[split_macro[0]] = split_macro[1]
            else:
                raise MacroError(
                    'Following string cannot be parsed to macros: {}'.format(macros_str))
    return macros


class MacroError(SnapshotError):
    """
    Problems parsing macros (wrong syntax).
    """
    pass


class ReqParseError(SnapshotError):
    """
    Parent exception class for exceptions that can happen while parsing a request file.
    """
    pass


class JsonParseError(SnapshotError):
    """
    Parent exception class for exceptions that can happen while parsing a json file.
    """
    pass


class ReqFileFormatError(ReqParseError):
    """
    Syntax error in request file.
    """
    pass


class ReqFileInfLoopError(ReqParseError):
    """
    If request file is calling one of its ancestors.
    """
    pass


# TODO Reading filters and labels from the config file is deprecated as they
# are now part of the request file. When the transition is complete, remove
# them from this function. Also remove them from the command-line arguments.
# See also SnapshotGui.init_snapshot().
def initialize_config(config_path=None, save_dir=None, force=False,
                      default_labels=None, force_default_labels=None,
                      req_file_path=None, req_file_macros=None,
                      init_path=None, **kwargs):
    """
    Settings are a dictionary which holds common configuration of
    the application (such as directory with save files, request file
    path, etc). It is propagated to snapshot widgets.

    :param save_dir: path to the default save directory
    :param config_path: path to configuration file
    :param force: force saving on disconnected channels
    :param default_labels: list of default labels
    :param force_default_labels: whether user can only select predefined labels
    :param req_file_path: path to request file
    :param req_file_macros: macros can be as dict (key, value pairs)
                            or a string in format A=B,C=D
    :param init_path: default path to be shown on the file selector
    """
    config = {'config_ok': True, 'macros_ok': True}
    if config_path:
        # Validate configuration file
        try:
            new_settings = json.load(open(config_path))
            # force-labels must be type of bool
            if not isinstance(new_settings.get('labels', dict())
                                          .get('force-labels', False), bool):
                raise TypeError('"force-labels" must be boolean')
        except Exception as e:
            # Propagate error to the caller, but continue filling in defaults
            config['config_ok'] = False
            config['config_error'] = str(e)
            new_settings = {}
    else:
        new_settings = {}

    config['save_file_prefix'] = ''
    config['req_file_path'] = ''
    config['req_file_macros'] = {}
    config['existing_labels'] = []  # labels that are already in snap files
    config['force'] = force
    config['init_path'] = init_path or ''

    if isinstance(default_labels, str):
        default_labels = default_labels.split(',')

    elif not isinstance(default_labels, list):
        default_labels = []

    # default labels also in config file? Add them
    config['default_labels'] = \
        list(set(default_labels + (new_settings.get('labels', dict())
                                               .get('labels', list()))))

    config['force_default_labels'] = \
        new_settings.get('labels', dict()) \
                    .get('force-labels', False) or force_default_labels

    # Predefined filters. Ensure entries exist.
    config['predefined_filters'] = new_settings.get('filters', {})
    for fltype in ('filters', 'rgx-filters'):
        if fltype not in config['predefined_filters']:
            config['predefined_filters'][fltype] = []

    if req_file_macros is None:
        req_file_macros = {}
    elif isinstance(req_file_macros, str):
        # Try to parse macros. If problem, just pass to configure window
        # which will force user to do it right way.
        try:
            req_file_macros = parse_macros(req_file_macros)
        except MacroError:
            config['macros_ok'] = False
        config['req_file_macros'] = req_file_macros

    if req_file_path and config['macros_ok']:
        config['req_file_path'] = \
            os.path.abspath(os.path.join(config['init_path'], req_file_path))

    if not save_dir:
        # Default save dir (do this once we have valid req file)
        save_dir = os.path.dirname(config['req_file_path'])

    config['save_dir'] = None if not save_dir else os.path.abspath(save_dir)
    return config


def parse_from_save_file(save_file_path, metadata_only=False):
    """
    Parses save file to dict {'pvname': {'data': {'value': <value>, 'raw_name': <name_with_macros>}}}

    :param save_file_path: Path to save file.

    :return: (saved_pvs, meta_data, err)

        saved_pvs: in format {'pvname': {'data': {'value': <value>, 'raw_name': <name_with_macros>}}}

        meta_data: as dictionary

        err: list of strings (each entry one error)
    """

    saved_pvs = {}
    meta_data = {}  # If macros were used they will be saved in meta_data
    err = []
    meta_loaded = False

    try:
        saved_file = open(save_file_path)
    except OSError:
        err.append("File cannot be opened for reading.")
        return saved_pvs, meta_data, err

    for line in saved_file:
        # first line with # is metadata (as json dump of dict)
        if line.startswith('#') and not meta_loaded:
            line = line[1:]
            try:
                meta_data = json.loads(line)
            except json.JSONDecodeError:
                # Problem reading metadata
                err.append('Meta data could not be decoded. '
                           'Must be in JSON format.')
            meta_loaded = True
            if metadata_only:
                break
        # skip empty lines and all rest with #
        elif (not metadata_only
                and line.strip()
                and not line.startswith('#')):

            split_line = line.strip().split(',', 1)
            pvname = split_line[0]

            try:
                if len(split_line) < 2:
                    pv_value = None
                elif split_line[1].startswith('{'):
                    # The new JSON value format
                    data = json.loads(split_line[1])
                    pv_value = data['val']
                    # EGU and PREC are ignored, only stored for information.
                else:
                    # The legacy "name,value" format
                    pv_value_str = split_line[1]
                    pv_value = json.loads(pv_value_str)

                if isinstance(pv_value, list):
                    if any(isinstance(x, list) for x in pv_value):
                        # A version of this tool incorrectly wrote
                        # one-element arrays, and we shouldn't crash if we
                        # read such a snapshot.
                        pv_value = None
                        err.append(f"Value of '{pvname}' contains nested "
                                   "lists; only one-dimensional arrays "
                                   "are supported.")
                    else:
                        # arrays as numpy array, because pyepics returns
                        # as numpy array
                        pv_value = numpy.asarray(pv_value)

            except json.JSONDecodeError:
                pv_value = None
                err.append(f"Value of '{pvname}' cannot be decoded, ignored.")

            saved_pvs[pvname] = {'value': pv_value}

    if not meta_loaded:
        err.insert(0, 'No meta data in the file.')
    else:
        # Check that the snapshot has machine parameters with metadata; at some
        # point, only values were being saved.
        for p, v in meta_data.get('machine_params', {}).items():
            if not isinstance(v, dict):
                meta_data['machine_params'][p] = {
                    'value': v,
                    'units': None,
                    'precision': None
                }

    saved_file.close()
    return saved_pvs, meta_data, err


def parse_to_save_file(pvs, save_file_path, macros=None,
                       symlink_path=None, **kw):
    """
    This function is called at each save of PV values. This is a parser
    which generates save file from pvs. All parameters in **kw are packed
    as meta data

    :param pvs: Dict with pvs data to be saved. pvs = {pvname: {'value': value, ...}}
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
    with open(save_file_path, 'w') as save_file:
        # Save meta data
        if macros:
            kw['macros'] = macros
        save_file.write("#" + json.dumps(kw) + "\n")

        for pvname, data in pvs.items():
            save_file.write(data.get('raw_name'))
            value = data.get('val')
            if value is not None:
                save_file.write(',')
                if isinstance(value, numpy.ndarray):
                    data['val'] = value.tolist()
                del data['raw_name']  # do not duplicate
                json.dump(data, save_file)
            save_file.write('\n')

    # Create symlink _latest.snap
    if symlink_path:
        if os.path.isfile(symlink_path):
            os.remove(symlink_path)

        counter = 5
        while counter > 0:
            no_error = True
            try:
                os.symlink(save_file_path, symlink_path)
            except BaseException:
                logging.warning("unable to create link")
                no_error = False

            if no_error:
                break

            time.sleep(0.5)

            counter -= 1


def list_save_files(save_dir, req_file_path):
    "Returns a list of save files and a list of their modification times."

    req_file_name = os.path.basename(req_file_path)
    file_dir = os.path.join(save_dir, os.path.splitext(req_file_name)[0])
    file_paths = [path for path in glob.glob(file_dir + '*' + save_file_suffix)
                  if os.path.isfile(path)]
    modif_times = [os.path.getmtime(path) for path in file_paths]
    return file_paths, modif_times


def get_save_files(save_dir, req_file_path):
    """
    Parses all new or modified files. Parsed files are returned as a
    dictionary.
    """

    since_start("Started parsing snaps")
    file_paths, modif_times = list_save_files(save_dir, req_file_path)
    req_file_name = os.path.basename(req_file_path)

    def process_file(file_path, modif_time):
        file_name = os.path.basename(file_path)
        if os.path.isfile(file_path):
            _, meta_data, err = parse_from_save_file(file_path,
                                                     metadata_only=True)

            # Check if we have req_file metadata. This is used to determine
            # which request file the save file belongs to. If there is no
            # metadata (or no req_file specified in the metadata) we search
            # using a prefix of the request file. The latter is less
            # robust, but is backwards compatible.
            have_metadata = "req_file_name" in meta_data \
                and meta_data["req_file_name"] == req_file_name
            prefix_matches = \
                file_name.startswith(req_file_name.split(".")[0] + "_")
            if have_metadata or prefix_matches:
                # we really should have basic meta data
                # (or filters and some other stuff will silently fail)
                if "comment" not in meta_data:
                    meta_data["comment"] = ""
                if "labels" not in meta_data:
                    meta_data["labels"] = []
                if "machine_params" not in meta_data:
                    meta_data["machine_params"] = {}

                return (file_name,
                        {'file_name': file_name,
                            'file_path': file_path,
                            'meta_data': meta_data,
                            'modif_time': modif_time},
                        err)

    results = global_thread_pool.map(process_file, file_paths, modif_times)
    err_to_report = []
    parsed_save_files = {}
    for r in results:
        if r is not None:
            file_name, info, err = r
            parsed_save_files[file_name] = info
            if err:
                err_to_report.append((file_name, err))

    since_start("Finished parsing snaps")
    return parsed_save_files, err_to_report
