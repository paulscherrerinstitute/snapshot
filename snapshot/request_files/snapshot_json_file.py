import concurrent.futures
import json
from itertools import chain, repeat
from pathlib import Path
from typing import Optional

import yaml
from PyQt5.QtWidgets import QMessageBox
from snapshot.core import SnapshotError, SnapshotPv
from snapshot.request_files.snapshot_file import ReqParseError, SnapshotFile
from snapshot.request_files.snapshot_req_file import SnapshotReqFile


class SnapshotJsonFile(SnapshotFile):
    def __init__(self, path: Path, data: str, macros: Optional[dict] = None):
        self.__path = path
        self._macros = macros if macros is not None else {}
        self._file_data = self.__read_input(data)

    def read(self):
        metadata = self.__extract_metadata()
        self.__test_machine_params(metadata)

        list_of_pvs, list_of_pvs_config = self.__extract_pv_data()
        included_pvs, included_config = self.__handle_includes()

        return (
            list_of_pvs + included_pvs,
            metadata,
            list_of_pvs_config + included_config,
        )

    def __read_input(self, data: str) -> dict:
        data_with_substituted_macros = SnapshotPv.macros_substitution(
            data, self._macros
        )
        try:
            if self.__path.suffix == ".json":
                return json.loads(data_with_substituted_macros)
            elif self.__path.suffix in [".yaml", ".yml"]:
                return yaml.safe_load(data_with_substituted_macros)
        except Exception as e:
            raise ReqParseError(f"{self.__path}: Could not read file.", e)

    def __extract_metadata(self):
        metadata = {"filters": {}, "labels": {}}
        json_data = self._file_data.get("config", {})
        metadata["filters"]["filters"] = json_data.get("filters", [])
        metadata["filters"]["rgx_filters"] = json_data.get("rgx_filters", [])
        metadata["labels"]["labels"] = json_data.get("labels", [])
        metadata["labels"]["force_labels"] = json_data.get(
            "force_labels", False)
        metadata["read_only"] = json_data.get("read_only", False)
        metadata["no_restore_all"] = json_data.get("no_restore_all", False)
        metadata["machine_params"] = json_data.get("machine_params", [])
        return metadata

    def __extract_pv_data(self):
        list_of_pvs = []
        list_of_pvs_config = []
        get_pvs_dict = self._file_data.get("pvs", {})
        default_config_dict = get_pvs_dict.get("defaults", {})
        # default precision for this ioc (-1 = load from pv)
        default_precision = default_config_dict.get("precision", -1)
        for channel in get_pvs_dict.get("list", {}):
            pv_name = channel.get("name", "")
            precision = channel.get("precision", default_precision)
            list_of_pvs.append(pv_name)
            list_of_pvs_config.append({pv_name: {"precision": precision}})
        return list_of_pvs, list_of_pvs_config

    @staticmethod
    def __test_machine_params(metadata):
        # In the file, machine_params are stored as an array of
        # key-value pairs to preserve order. Here, we can rely on
        # having an ordered dict.
        try:
            metadata["machine_params"] = dict(
                metadata.get("machine_params", []))
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

    def __handle_includes(self) -> (list, list):
        includes = self._file_data.get("include", [])
        included_pvs = []
        included_config = []

        for include in includes:
            included_file = self.__path.parent / include["name"]
            macros_list = include.get("macros", [{}])

            if included_file.suffix == ".req":
                self.__include_req_file(
                    included_config, included_file, included_pvs, macros_list
                )
            elif included_file.suffix in (".yaml", ".yml", ".json"):
                try:
                    self.__include_json_yaml_file(
                        included_config,
                        included_file,
                        included_pvs,
                        macros_list,
                    )
                except Exception as e:
                    QMessageBox.warning(
                        None,
                        "Warning",
                        "Problem with the macros/include file. The macros could not be added and are going to be ignored.",
                        QMessageBox.Ok,
                        QMessageBox.NoButton,
                    )

            else:
                raise ReqParseError(
                    f"Snapshot file of {included_file.suffix} type is not supported."
                )
        return included_pvs, included_config

    @staticmethod
    def __include_json_yaml_file(
        included_config, included_file, included_pvs, macros_list
    ):
        data = included_file.read_text()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(
                lambda i, d,
                m: SnapshotJsonFile(path=i, data=d, macros=m).read(),
                repeat(included_file),
                repeat(data),
                macros_list,)
            for pvs, _, config in results:
                included_pvs += pvs
                included_config += config

    @staticmethod
    def __include_req_file(
            included_config, included_file, included_pvs, macros_list):
        pvs = []
        for macros in macros_list:
            file = SnapshotReqFile(path=str(included_file), macros=macros)
            pvs += file.read()[0]
        included_pvs += pvs
        included_config += [{"precision": 6}] * len(pvs)


class JsonYamlParseError(SnapshotError):
    """
    Parent exception class for exceptions that can happen while parsing a json/yaml file.
    """

    pass
