import abc
import concurrent.futures
import json
import os
import re
from itertools import chain
from pathlib import Path

import yaml

from snapshot.core import SnapshotPv, SnapshotError
from snapshot.parser import MacroError, parse_macros


class SnapshotFile(abc.ABC):
    @abc.abstractmethod
    def read(self):
        pass


class SnapshotReqFile(SnapshotFile):
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
            self._trace = f'{parent._trace} [line {parent._curr_line_n}: {parent._curr_line}] >> {self._path}'

        else:
            self._trace = self._path

        self._curr_line = None
        self._curr_line_n = 0
        self._curr_line_txt = ''
        self._err = []
        self._type, self._file_data = self.read_input()

    def read_input(self):
        filepath = Path(self._path)
        try:
            content = filepath.read_text()
            if filepath.suffix == '.json':
                content = json.loads(content)
            elif filepath.suffix in ['.yaml', '.yml']:
                content = yaml.safe_load(content)
            elif filepath.suffix != '.req':
                raise ReqParseError(f"Unsupported file format for {filepath}!")
        except Exception as e:
            msg = f'{self._path}: Could not read "{filepath}" load file.'
            raise ReqParseError(msg, e)
        return filepath.suffix, content

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

        pvs, metadata, includes, pvs_config = result
        while includes:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = executor.map(lambda f: f._read_only_self(),
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
            raise ReqParseError('Invalid format of machine parameter list, '
                                'must be a list of ["name", "pv_name"] pairs.')

        forbidden_chars = " ,.()"
        if any(
                any(char in param for char in forbidden_chars)
                for param in metadata['machine_params']
        ):
            raise ReqParseError('Invalid format of machine parameter list, '
                                'names must not contain space or punctuation.')

        return pvs, metadata, pvs_config

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
        pvs_config = []
        if self._type == '.req':
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
                    path = os.path.join(
                        os.path.dirname(self._path),
                        split_line[0])
                    msg = self._check_looping(path)
                    if msg:
                        return ReqFileInfLoopError(
                            self._format_err(
                                (self._curr_line_n, self._curr_line), msg))
                    try:
                        sub_f = SnapshotReqFile(
                            path, parent=self, macros=macros)
                        includes.append(sub_f)

                    except OSError as e:
                        return OSError(
                            self._format_err(
                                (self._curr_line, self._curr_line_n), e))
        else:
            metadata, pvs, pvs_config = self._extract_meta_pvs_from_dict()
        return pvs, metadata, includes, pvs_config

    def _extract_pvs_from_req(self):
        try:
            list_of_pvs = self._file_data.split('\n')
        except Exception as e:
            return ReqParseError(e)
        else:
            return list_of_pvs

    def _extract_meta_pvs_from_dict(self):
        try:
            return self._get_pvs_list()
        except Exception:
            msg = f"{self._path}: Could not parse Json file."
            return JsonYamlParseError(msg)

    def _get_pvs_list(self):
        metadata = {'filters': {}}
        get_metadata_dict = self._file_data.get("CONFIG", {})
        # CONFIGURATIONS
        for config in get_metadata_dict.keys():
            # // test filters
            if config == 'filters':
                list_filters = list(get_metadata_dict[config])
                metadata['filters'].update(
                    {f'{config}': list_filters})
            elif config == 'rgx_filters':
                list_rgx = []
                list_rgx_names = []
                for rgx_pattern in get_metadata_dict[config]:
                    list_rgx.append(rgx_pattern[1])
                    list_rgx_names.append(rgx_pattern[0])
                metadata['filters'].update({f'{config}': list_rgx})
                metadata['filters'].update({f'{config}_names': list_rgx_names})
            elif config in ['labels', 'force_labels']:
                metadata['labels'] = {f'{config}': get_metadata_dict[config]}
            elif config == 'read_only':
                metadata['read_only'] = get_metadata_dict[config]
            elif config in ['machine_params']:
                metadata['machine_params'] = get_metadata_dict[config]

        # LIST OF PVS
        list_of_pvs = []
        list_of_pvs_config = []
        get_pvs_dict = self._file_data.get("PVS", {})
        for ioc in get_pvs_dict.keys():
            # get default configs
            default_config_dict = get_pvs_dict[ioc].get("DEFAULT_CONFIG", {})
            # default precision for this ioc (-1 = load from pv)
            default_precision = default_config_dict.get('default_precision', -1)
            for channel in get_pvs_dict[ioc].get("CHANNELS", {}):
                pv_name = channel.get('name', '')
                precision = channel.get('precision', default_precision)
                list_of_pvs.append(f'{ioc}:{pv_name}')
                list_of_pvs_config.append({f'{ioc}:{pv_name}': {
                    "precision": precision}})

        return metadata, list_of_pvs, list_of_pvs_config

    def _format_err(self, line: tuple, msg: str):
        return f'{self._trace} [line {line[0]}: {line[1]}]: {msg}'

    def _validate_macros_in_txt(self, txt: str):
        invalid_macros = []
        macro_rgx = re.compile(r'\$\(.*?\)')  # find all of type $()
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
                    return f'Infinity loop detected. File {path} was already called from {ancestor._parent._path}'
                else:
                    return f'Infinity loop detected. File {path} was already loaded as root request file.'

            else:
                ancestor = ancestor._parent


class SnapshotJsonFile(SnapshotFile):
    def __init__(self, path: str, parent=None, macros: dict = None,
                 changeable_macros: list = None):
        self._path = os.path.abspath(path)
        self._type, self._file_data = self.read_input()

    def read_input(self):
        filepath = Path(self._path)
        try:
            content = filepath.read_text()
            if filepath.suffix == '.json':
                content = json.loads(content)
            elif filepath.suffix in ['.yaml', '.yml']:
                content = yaml.safe_load(content)
        except Exception as e:
            msg = f'{self._path}: Could not read "{filepath}" load file.'
            raise ReqParseError(msg, e)
        return filepath.suffix, content

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
        metadata, pvs, pvs_config = self._extract_meta_pvs_from_dict()

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
            raise ReqParseError('Invalid format of machine parameter list, '
                                'must be a list of ["name", "pv_name"] pairs.')

        forbidden_chars = " ,.()"
        if any(
                any(char in param for char in forbidden_chars)
                for param in metadata['machine_params']
        ):
            raise ReqParseError('Invalid format of machine parameter list, '
                                'names must not contain space or punctuation.')

        return pvs, metadata, pvs_config

    def _extract_meta_pvs_from_dict(self):
        try:
            return self._get_pvs_list()
        except Exception:
            msg = f"{self._path}: Could not parse Json file."
            return JsonYamlParseError(msg)

    def _get_pvs_list(self):
        metadata = {'filters': {}}
        get_metadata_dict = self._file_data.get("CONFIG", {})
        # CONFIGURATIONS
        for config in get_metadata_dict.keys():
            # // test filters
            if config == 'filters':
                list_filters = list(get_metadata_dict[config])
                metadata['filters'].update(
                    {f'{config}': list_filters})
            elif config == 'rgx_filters':
                list_rgx = []
                list_rgx_names = []
                for rgx_pattern in get_metadata_dict[config]:
                    list_rgx.append(rgx_pattern[1])
                    list_rgx_names.append(rgx_pattern[0])
                metadata['filters'].update({f'{config}': list_rgx})
                metadata['filters'].update({f'{config}_names': list_rgx_names})
            elif config in ['labels', 'force_labels']:
                metadata['labels'] = {f'{config}': get_metadata_dict[config]}
            elif config == 'read_only':
                metadata['read_only'] = get_metadata_dict[config]
            elif config in ['machine_params']:
                metadata['machine_params'] = get_metadata_dict[config]

        # LIST OF PVS
        list_of_pvs = []
        list_of_pvs_config = []
        get_pvs_dict = self._file_data.get("PVS", {})
        for ioc in get_pvs_dict.keys():
            # get default configs
            default_config_dict = get_pvs_dict[ioc].get("DEFAULT_CONFIG", {})
            # default precision for this ioc (-1 = load from pv)
            default_precision = default_config_dict.get('default_precision', -1)
            for channel in get_pvs_dict[ioc].get("CHANNELS", {}):
                pv_name = channel.get('name', '')
                precision = channel.get('precision', default_precision)
                list_of_pvs.append(f'{ioc}:{pv_name}')
                list_of_pvs_config.append({f'{ioc}:{pv_name}': {
                    "precision": precision}})

        return metadata, list_of_pvs, list_of_pvs_config

def create_snapshot_file(path: str, changeable_macros: list = None) -> SnapshotFile:
    filepath = Path(path)
    if filepath.suffix == '.req':
        return SnapshotReqFile(path, changeable_macros=changeable_macros)
    if filepath.suffix in ('.json', '.yaml', '.yml'):
        return SnapshotJsonFile(path, changeable_macros=changeable_macros)
    else:
        raise SnapshotError(f'Snapshot file of {filepath.suffix} type is not supported.')


class ReqParseError(SnapshotError):
    """
    Parent exception class for exceptions that can happen while parsing a request file.
    """
    pass


class JsonYamlParseError(SnapshotError):
    """
    Parent exception class for exceptions that can happen while parsing a json/yaml file.
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
