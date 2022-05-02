import json
import re
import sys
from pathlib import Path

import yaml
from typing import Tuple


class ConversionError(ValueError):
    """
    Parent exception class for exceptions that can happen while conversion from request file to yaml/json.
    """
    pass


def convert_req_to_dict(request_file_content: str, include_extension: str = '.req') -> dict:
    raw_metadata, rest_of_content = __extract_metadata(request_file_content.lstrip())
    metadata = __adapt_metadata(raw_metadata)

    stripped_lines = [line.strip() for line in rest_of_content.splitlines() if line.strip()]
    raw_pvs = __extract_pvs(stripped_lines)
    parsed_includes = __parse_includes(stripped_lines, include_extension)

    return {'pvs': {'list': raw_pvs}, 'config': metadata, 'include': parsed_includes}


def convert_req_to_yaml(request_file_content: str, include_extension: str = '.req') -> str:
    return yaml.dump(convert_req_to_dict(request_file_content, include_extension))


def convert_req_to_json(request_file_content: str, include_extension: str = '.req') -> str:
    return json.dumps(convert_req_to_dict(request_file_content, include_extension), indent=4)


def __adapt_metadata(raw_metadata: dict) -> dict:
    metadata = raw_metadata.copy()
    metadata['rgx_filters'] = raw_metadata.get('filters', {}).get('rgx-filters', [])
    metadata['filters'] = raw_metadata.get('filters', {}).get('filters', [])
    metadata['labels'] = raw_metadata.get('labels', {}).get('labels', [])
    metadata['force_labels'] = raw_metadata.get('labels', {}).get('force-labels', False)
    return metadata


def __parse_includes(stripped_lines: list, include_extension: str) -> list:
    intermediate_includes = {}
    for include in __extract_includes(stripped_lines):
        arguments = include[1:].split(',', maxsplit=1)
        filename = arguments[0].replace('.req', include_extension)
        if filename in intermediate_includes.keys():
            intermediate_includes[filename].append(__get_macros_for_includes(arguments)[0])
        else:
            intermediate_includes[filename] = __get_macros_for_includes(arguments)

    parsed_includes = [{'name': name, 'macros': macros} for name, macros in intermediate_includes.items()]
    __remove_empty_macros(parsed_includes)
    return parsed_includes


def __remove_empty_macros(parsed_includes: list) -> None:
    for include in parsed_includes:
        if len(include['macros']) == 0:
            del include['macros']


def __get_macros_for_includes(arguments: list) -> list:
    if len(arguments) == 2:
        raw_macro = re.split(r'[,=]', arguments[1].strip()[1:-1])
        return [{raw_macro[i]: raw_macro[i + 1] for i in range(0, len(raw_macro), 2)}]
    return []


def __extract_includes(stripped_lines: list) -> list:
    return [line for line in stripped_lines if line.startswith('!')]


def __extract_pvs(stripped_lines: list) -> list:
    return [line for line in stripped_lines if not line.startswith(('#', 'data{', '}', '!'))]


def __extract_metadata(md: str) -> Tuple[dict, str]:
    if not md.startswith('{'):
        return {}, md
    try:
        metadata, end_of_metadata = json.JSONDecoder().raw_decode(md)
        return metadata, md[end_of_metadata:]
    except json.JSONDecodeError:
        raise ConversionError('Could not decode request file metadata')


if __name__ == "__main__":
    args = sys.argv[1:]
    path = Path(args[0])
    data = convert_req_to_yaml(path.read_text(), '.yaml')
    print(data)
    data = convert_req_to_json(path.read_text(), '.json')
    print(data)
