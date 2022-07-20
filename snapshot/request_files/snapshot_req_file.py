import concurrent.futures
import json
import os
import re
from itertools import chain
from pathlib import Path

from snapshot.core import SnapshotPv
from snapshot.parser import MacroError, parse_macros
from snapshot.request_files.snapshot_file import ReqParseError, SnapshotFile


class SnapshotReqFile(SnapshotFile):
    def __init__(
        self,
        path: str,
        parent=None,
        macros: dict = None,
        changeable_macros: list = None,
    ):
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
            self._trace = f"{parent._trace} [line {parent._curr_line_n}: {parent._curr_line}] >> {self._path}"

        else:
            self._trace = self._path

        self._curr_line = None
        self._curr_line_n = 0
        self._curr_line_txt = ""
        self._err = []
        self._type, self._file_data = self.read_input()

    def read_input(self):
        filepath = Path(self._path)
        try:
            content = filepath.read_text()
        except Exception as e:
            raise ReqParseError(
                f'{self._path}: Could not read "{filepath}" load file.', e
            )
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
                results = executor.map(lambda f: f._read_only_self(), includes)
            old_includes = includes
            includes = []
            for result, inc in zip(results, old_includes):
                if not isinstance(result, tuple):
                    raise result
                new_pvs, new_metadata, new_includes, _ = result
                if new_metadata:
                    msg = (
                        f"Found metadata in included file {inc._path}; "
                        "metadata is only allowed in the top-level file."
                    )
                    raise ReqParseError(msg)
                pvs += new_pvs
                includes += new_includes

        # In the file, machine_params are stored as an array of
        # key-value pairs to preserve order. Here, we can rely on
        # having an ordered dict.
        try:
            metadata["machine_params"] = dict(metadata.get("machine_params", []))
            if not all(
                isinstance(x, str)
                for x in chain.from_iterable(metadata["machine_params"].items())
            ):
                raise ReqParseError
        except Exception:
            raise ReqParseError(
                "Invalid format of machine parameter list, "
                'must be a list of ["name", "pv_name"] pairs.'
            )

        forbidden_chars = " ,.()"
        if any(
            any(char in param for char in forbidden_chars)
            for param in metadata["machine_params"]
        ):
            raise ReqParseError(
                "Invalid format of machine parameter list, "
                "names must not contain space or punctuation."
            )

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
        if self._file_data.lstrip().startswith("{"):
            try:
                md = self._file_data.lstrip()
                metadata, end_of_metadata = json.JSONDecoder().raw_decode(md)
            except json.JSONDecodeError:
                msg = f"{self._path}: Could not parse JSON metadata header."
                return ReqParseError(msg)

            metadata = self.__normalize_key_values(metadata)

            # Ensure line counts make sense for error reporting.
            actual_data = md[end_of_metadata:].lstrip()
            actual_data_index = self._file_data.find(actual_data)
            self._curr_line_n = len(self._file_data[:actual_data_index].splitlines())
            self._file_data = self._file_data[actual_data_index:]
        else:
            metadata = {}
            self._curr_line_n = 0

        for self._curr_line in self._file_data.splitlines():
            self._curr_line_n += 1
            self._curr_line = self._curr_line.strip()

            # skip comments, empty lines and "data{}" stuff
            if (
                not self._curr_line.startswith(("#", "data{", "}", "!"))
                and self._curr_line.strip()
            ):
                # First replace macros, then check if any unreplaced macros
                # which are not "global"
                pvname = SnapshotPv.macros_substitution(
                    (self._curr_line.rstrip().split(",", maxsplit=1)[0]),
                    self._macros,
                )
                try:
                    # Check if any unreplaced macros
                    self._validate_macros_in_txt(pvname)
                except MacroError as e:
                    return ReqParseError(
                        self._format_err((self._curr_line_n, self._curr_line), e)
                    )
                else:
                    pvs.append(pvname)
            elif self._curr_line.startswith("!"):
                # Calling another req file
                split_line = self._curr_line[1:].split(",", maxsplit=1)
                if len(split_line) > 1:
                    macro_txt = split_line[1].strip()
                    if macro_txt.startswith(('"', "'")):
                        quote_type = macro_txt[0]
                    else:
                        return ReqFileFormatError(
                            self._format_err(
                                (self._curr_line_n, self._curr_line),
                                "Syntax error. Macro argument must be quoted",
                            )
                        )
                    if not macro_txt.endswith(quote_type):
                        return ReqFileFormatError(
                            self._format_err(
                                (self._curr_line_n, self._curr_line),
                                "Syntax error. Macro argument must be quoted",
                            )
                        )
                    macro_txt = SnapshotPv.macros_substitution(
                        macro_txt[1:-1], self._macros
                    )
                    try:
                        # Check for any unreplaced macros
                        self._validate_macros_in_txt(macro_txt)
                        macros = parse_macros(macro_txt)

                    except MacroError as e:
                        return ReqParseError(
                            self._format_err((self._curr_line_n, self._curr_line), e)
                        )
                else:
                    macros = {}
                path = os.path.join(os.path.dirname(self._path), split_line[0])
                msg = self._check_looping(path)
                if msg:
                    return ReqFileInfLoopError(
                        self._format_err((self._curr_line_n, self._curr_line), msg)
                    )
                try:
                    sub_f = SnapshotReqFile(path, parent=self, macros=macros)
                    includes.append(sub_f)

                except OSError as e:
                    return OSError(
                        self._format_err((self._curr_line, self._curr_line_n), e)
                    )
        return pvs, metadata, includes, pvs_config

    @staticmethod
    def __normalize_key_values(metadata: dict) -> dict:
        # Ensure backward compatibility - some keys previously were using "-" instead of "_"
        # To further support these keys (e.g. "rgx-filters", "force-labels"
        # we normalize them to "rgx_filters", "force_labels"
        if "labels" in metadata.keys() and "force-labels" in metadata["labels"].keys():
            metadata["labels"]["force_labels"] = metadata["labels"].pop("force-labels")
        if "filters" in metadata.keys() and "rgx-filters" in metadata["filters"].keys():
            metadata["filters"]["rgx_filters"] = metadata["filters"].pop("rgx-filters")
        return metadata

    def _extract_pvs_from_req(self):
        try:
            list_of_pvs = self._file_data.split("\n")
        except Exception as e:
            return ReqParseError(e)
        else:
            return list_of_pvs

    def _format_err(self, line: tuple, msg: str):
        return f"{self._trace} [line {line[0]}: {line[1]}]: {msg}"

    def _validate_macros_in_txt(self, txt: str):
        invalid_macros = []
        macro_rgx = re.compile(r"\$\(.*?\)")  # find all of type $()
        raw_macros = macro_rgx.findall(txt)
        for raw_macro in raw_macros:
            if (
                raw_macro not in self._macros.values()
                and raw_macro[2:-1] not in self._c_macros
            ):
                # There are unknown macros which were not substituted
                invalid_macros.append(raw_macro)

        if invalid_macros:
            raise MacroError(
                "Following macros were not defined: {}".format(
                    ", ".join(invalid_macros)
                )
            )

    def _check_looping(self, path):
        path = os.path.normpath(os.path.abspath(path))
        ancestor = self  # eventually could call self again

        while ancestor is not None:
            if os.path.normpath(os.path.abspath(ancestor._path)) == path:
                if ancestor._parent:
                    return f"Infinity loop detected. File {path} was already called from {ancestor._parent._path}"
                else:
                    return f"Infinity loop detected. File {path} was already loaded as root request file."

            else:
                ancestor = ancestor._parent


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
