import json
from itertools import chain
from pathlib import Path

import yaml

from snapshot.core import SnapshotError
from snapshot.request_files.snapshot_file import SnapshotFile, ReqParseError


class SnapshotJsonFile(SnapshotFile):
    def __init__(self, path: str):
        self.__path = Path(path)
        self._file_data = self.__read_input()

    def read(self):
        metadata = self.__extract_metadata()
        self.__test_machine_params(metadata)
        list_of_pvs, list_of_pvs_config = self.__extract_pv_data()
        return list_of_pvs, metadata, list_of_pvs_config

    def __read_input(self) -> dict:
        try:
            content = self.__path.read_text()
            if self.__path.suffix == '.json':
                return json.loads(content)
            elif self.__path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(content)
        except Exception as e:
            raise ReqParseError(f'{self.__path}: Could not read file.', e)

    def __extract_metadata(self):
        metadata = {'filters': {}, 'labels': {}}
        json_data = self._file_data.get("config", {})
        metadata['filters']['filters'] = json_data.get('filters', [])
        metadata['filters']['rgx_filters'] = json_data.get('rgx_filters', [])
        metadata['labels']['labels'] = json_data.get('labels', [])
        metadata['labels']['force_labels'] = json_data.get('force_labels', False)
        metadata['read_only'] = json_data.get('read_only', False)
        metadata['machine_params'] = json_data.get('machine_params', [])
        return metadata

    def __extract_pv_data(self):
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
        return list_of_pvs, list_of_pvs_config

    @staticmethod
    def __test_machine_params(metadata):
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


class JsonYamlParseError(SnapshotError):
    """
    Parent exception class for exceptions that can happen while parsing a json/yaml file.
    """
    pass
