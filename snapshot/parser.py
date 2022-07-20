import concurrent.futures
import glob
import json
import logging
import os
import time
from itertools import chain
from pathlib import Path

import numpy

from snapshot.core import SnapshotError, since_start

save_file_suffix = ".snap"


# Helper functions to support macros parsing for users of this lib
def parse_macros(macros_str):
    """
    Converting comma separated macros string to dictionary.

    :param macros_str: string of macros in style SYS=TST,D=A

    :return: dict of macros
    """

    macros = {}
    if macros_str:
        macros_list = macros_str.split(",")
        for macro in macros_list:
            split_macro = macro.strip().split("=")
            if len(split_macro) == 2:
                macros[split_macro[0]] = split_macro[1]
            else:
                raise MacroError(
                    f"Following string cannot be parsed to macros: {macros_str}"
                )
    return macros


class MacroError(SnapshotError):
    """
    Problems parsing macros (wrong syntax).
    """

    pass


# TODO Reading filters and labels from the config file is deprecated as they
# are now part of the request file. When the transition is complete, remove
# them from this function. Also remove them from the command-line arguments.
# See also SnapshotGui.init_snapshot().
def initialize_config(
    config_path=None,
    save_dir=None,
    force=False,
    default_labels=None,
    force_default_labels=None,
    req_file_path=None,
    req_file_macros=None,
    init_path=None,
    read_only=False,
    **kwargs,
):
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
    :param read_only: disable the restore button on the UI to a 'read only' snapshot mode
    """
    config = {"config_ok": True, "macros_ok": True}
    if config_path:
        # Validate configuration file
        try:
            new_settings = json.load(open(config_path))
            # force_labels must be type of bool
            if not isinstance(
                new_settings.get("labels", dict()).get("force_labels", False),
                bool,
            ):
                raise TypeError('"force_labels" must be boolean')
        except Exception as e:
            # Propagate error to the caller, but continue filling in defaults
            config["config_ok"] = False
            config["config_error"] = str(e)
            new_settings = {}
    else:
        new_settings = {}

    config["save_file_prefix"] = ""
    config["req_file_path"] = ""
    config["req_file_macros"] = {}
    config["existing_labels"] = []  # labels that are already in snap files
    config["force"] = force
    config["init_path"] = init_path or ""

    if isinstance(default_labels, str):
        default_labels = default_labels.split(",")

    elif not isinstance(default_labels, list):
        default_labels = []

    # default labels also in config file? Add them
    config["default_labels"] = list(
        set(default_labels + (new_settings.get("labels", dict()).get("labels", list())))
    )

    config["force_default_labels"] = (
        new_settings.get("labels", dict()).get("force_labels", False)
        or force_default_labels
    )

    # Predefined filters. Ensure entries exist.
    config["predefined_filters"] = new_settings.get("filters", {})
    for fltype in ("filters", "rgx_filters", "rgx_filters_names"):
        if fltype not in config["predefined_filters"]:
            config["predefined_filters"][fltype] = []

    if isinstance(req_file_macros, str):
        # Try to parse macros. If problem, just pass to configure window
        # which will force user to do it right way.
        try:
            req_file_macros = parse_macros(req_file_macros)
        except MacroError:
            config["macros_ok"] = False
        config["req_file_macros"] = req_file_macros

    if req_file_path and config["macros_ok"]:
        config["req_file_path"] = os.path.abspath(
            os.path.join(config["init_path"], req_file_path)
        )

    if not save_dir:
        # Default save dir (do this once we have valid req file)
        save_dir = os.path.dirname(config["req_file_path"])

    # read only mode
    config["read_only"] = read_only

    config["save_dir"] = os.path.abspath(save_dir) if save_dir else None
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
        if line.startswith("#") and not meta_loaded:
            line = line[1:]
            try:
                meta_data = json.loads(line)
            except json.JSONDecodeError:
                # Problem reading metadata
                err.append("Meta data could not be decoded. " "Must be in JSON format.")
            meta_loaded = True
            if metadata_only:
                break
        # skip empty lines and all rest with #
        elif not metadata_only and line.strip() and not line.startswith("#"):

            split_line = line.strip().split(",", 1)
            pvname = split_line[0]

            try:
                if len(split_line) < 2:
                    pv_value = None
                elif split_line[1].startswith("{"):
                    # The new JSON value format
                    data = json.loads(split_line[1])
                    pv_value = data["val"]
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
                        err.append(
                            f"Value of '{pvname}' contains nested "
                            "lists; only one-dimensional arrays "
                            "are supported."
                        )
                    else:
                        # arrays as numpy array, because pyepics returns
                        # as numpy array
                        pv_value = numpy.asarray(pv_value)

            except json.JSONDecodeError:
                pv_value = None
                err.append(f"Value of '{pvname}' cannot be decoded, ignored.")

            saved_pvs[pvname] = {"value": pv_value}

    if not meta_loaded:
        err.insert(0, "No meta data in the file.")
    else:
        # Check that the snapshot has machine parameters with metadata; at some
        # point, only values were being saved.
        for p, v in meta_data.get("machine_params", {}).items():
            if not isinstance(v, dict):
                meta_data["machine_params"][p] = {
                    "value": v,
                    "units": None,
                    "precision": None,
                }

    saved_file.close()
    return saved_pvs, meta_data, err


def parse_to_save_file(pvs, save_file_path, macros=None, symlink_path=None, **kw):
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
    with open(save_file_path, "w") as save_file:
        # Save meta data
        if macros:
            kw["macros"] = macros
        save_file.write("#" + json.dumps(kw) + "\n")

        for pvname, data in pvs.items():
            save_file.write(data.get("raw_name"))
            value = data.get("val")
            if value is not None:
                save_file.write(",")
                if isinstance(value, numpy.ndarray):
                    data["val"] = value.tolist()
                del data["raw_name"]  # do not duplicate
                json.dump(data, save_file)
            save_file.write("\n")

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
    """Returns a list of save files and a list of their modification times."""

    req_file_name = os.path.basename(req_file_path)
    file_dir = os.path.join(save_dir, os.path.splitext(req_file_name)[0])
    file_paths = [
        path
        for path in glob.glob(f"{file_dir}*{save_file_suffix}")
        if os.path.isfile(path)
    ]

    modif_times = [os.path.getmtime(path) for path in file_paths]
    return req_file_name, file_paths, modif_times


def get_save_files(save_dir, req_file_path):
    """
    Parses all new or modified files. Parsed files are returned as a
    dictionary.
    """
    since_start("Started parsing snaps")
    req_file_name, file_paths, modif_times = list_save_files(save_dir, req_file_path)

    def process_file(file_path, modif_time):
        file_name = os.path.basename(file_path)
        if os.path.isfile(file_path):
            _, meta_data, err = parse_from_save_file(file_path, metadata_only=True)

            # Check if we have req_file metadata. This is used to determine
            # which request file the save file belongs to. If there is no
            # metadata (or no req_file specified in the metadata) we search
            # using a prefix of the request file. The latter is less
            # robust, but is backwards compatible.
            have_metadata = (
                "req_file_name" in meta_data
                and meta_data["req_file_name"] == req_file_name
            )
            prefix_matches = file_name.startswith(req_file_name.split(".")[0] + "_")
            if have_metadata or prefix_matches:
                # we really should have basic meta data
                # (or filters and some other stuff will silently fail)
                if "comment" not in meta_data:
                    meta_data["comment"] = ""
                if "labels" not in meta_data:
                    meta_data["labels"] = []
                if "machine_params" not in meta_data:
                    meta_data["machine_params"] = {}

                return (
                    file_name,
                    {
                        "file_name": file_name,
                        "file_path": file_path,
                        "meta_data": meta_data,
                        "modif_time": modif_time,
                    },
                    err,
                )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(process_file, file_paths, modif_times)
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
