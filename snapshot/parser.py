from snapshot.core import SnapshotError, SnapshotPv
import os
import re


class SnapshotReqFile(object):
    def __init__(self, path: str, parent=None, macros: dict = None, changeable_macros: list = None):
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

        self._curr_line = None
        self._curr_line_n = 0
        self._curr_line_txt = ''
        self._err = list()

    def read(self):
        """
        Parse request file and return list of pv names where changeable_macros are not replaced. ("raw" pv names).
        In case of problems raises exceptions.
                ReqParseError
                    ReqFileFormatError
                    ReqFileInfLoopError

        :return: List of PV names.
        """
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
                pvname = SnapshotPv.macros_substitution((self._curr_line.rstrip().split(',', maxsplit=1)[0]),
                                                        self._macros)

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

                    macro_txt = SnapshotPv.macros_substitution(macro_txt[1:-1], self._macros)
                    try:
                        self._validate_macros_in_txt(macro_txt)  # Check if any unreplaced macros
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
        return '{} [line {}: {}]: {}'.format(self._trace, line[0], line[1], msg)

    def _validate_macros_in_txt(self, txt: str):
        invalid_macros = list()
        macro_rgx = re.compile('\$\(.*?\)')  # find all of type $()
        raw_macros = macro_rgx.findall(txt)
        for raw_macro in raw_macros:
            if raw_macro not in self._macros.values() and raw_macro[2:-1] not in self._c_macros:
                # There are unknown macros which were not substituted
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

                return msg
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