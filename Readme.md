# Overview


[![Conda](https://anaconda.org/paulscherrerinstitute/snapshot/badges/version.svg
)](https://anaconda.org/paulscherrerinstitute/snapshot) [![GitHub Release Date](https://img.shields.io/github/release-date/paulscherrerinstitute/snapshot)](https://github.com/paulscherrerinstitute/snapshot/releases) [![GitHub](https://img.shields.io/github/license/paulscherrerinstitute/snapshot)](https://github.com/paulscherrerinstitute/snapshot/blob/main/LICENSE)[![Lint](https://github.com/paulscherrerinstitute/snapshot/actions/workflows/lint.yml/badge.svg)](https://github.com/paulscherrerinstitute/snapshot/actions/workflows/lint.yml) [![Conda_publish](https://github.com/paulscherrerinstitute/snapshot/actions/workflows/conda_publish.yaml/badge.svg)](https://github.com/paulscherrerinstitute/snapshot/actions/workflows/conda_publish.yaml)



Snapshot is Python based tool with a graphical user interface which enables users to view, save, restore and compare values of Channel Access process variables (PVs). It can be conveniently loaded and used by sourcing the python environments, as in:

```bash
source /opt/gfa/python NNN
```

> **_Note:_**  NNN is the Python version: 3.8 or 3.10

# Usage

Snapshot includes multiple commands: gui, save, restore, convert. Which are intended to different usages and purposes, please find more details on each command section.

```bash
usage: snapshot [-h] {gui,save,restore,convert} ...

Tool for saving and restoring snapshots of EPICS process variables (PVs).
Can be used as graphical interface tool or a command line tool.

positional arguments:
  {gui,save,restore,convert}
                        modes of work (if not specified "gui" will be used)
    gui                 open graphical interface (default)
    save                save current state of PVs to file without using GUI
    restore             restore saved state of PVs from file without using GUI
    convert             convert ".req" file to json/yaml format

options:
  -h, --help            show this help message and exit
```

## Gui

Snapshot graphical interface is built using [PyQT5](https://pypi.org/project/PyQt5/). The GUI is composed of 3 main widgets: PVs list, save, restore and compare.

The PVs list is where the pvs will be presented, including its name, unit, effective tolerance (Eff. Tol. = Tolerance × 10^-Precision) and value. The tolerance is defined on the user interface input field.

The Restore widget allows to evaluate previously saved snap files and compare machine parameters among them, including filtering based on comments, labels, etc.

The Compare widget allows to combine previously saved snap files, which are selected via the restore widget, with the current values that are loaded and presented in the PVs list side-by-side. It will create new columns for each snap file selected and icons will help to identify values that differ.

The save widget allows to save a snap file with the current values that are present, one can also define name (input field) and output directory (dropdown top menu). Once the snap file is saved, it is automatically added to the Restore widget.

GUI is the default method of snapshot (if nothing is provided) and it can be started using the following command:

```bash
usage: snapshot gui [-h] [-m MACRO] [-d DIR] [-b BASE] [-f] [--labels LABELS] [--force_labels] [--config CONFIG] [--trace-execution]
                    [--read_only]
                    [FILE]

positional arguments:
  FILE                  REQ/YAML/JSON file.

options:
  -h, --help            show this help message and exit
  -m MACRO, --macro MACRO
                        macros for request file e.g.: "SYS=TEST,DEV=D1"
  -d DIR, --dir DIR     directory for saved snapshot files
  -b BASE, --base BASE  base directory for request files
  -f, --force           force save/restore in case of disconnected PVs
  --labels LABELS       list of comma separated predefined labels e.g.: "label_1,label_2"
  --force_labels        force predefined labels
  --config CONFIG       path to configuration file
  --trace-execution     print info during long-running tasks
  --read_only           Snapshot without the restore buttons (read only mode)
  --no_restore_all      Snapshot without the restore all button.
```

The `--config` option is deprecated, although it remains. It is recommended
that the configuration snippet is stored in the beginning of the request file.


## Save

Snapshot save command allows to save a snap file based on a Req/Yaml/JSON request file via the cli. 

```bash
usage: snapshot save [-h] [-m MACRO] [-o OUT] [-f] [--labels LABELS] [--comment COMMENT] [--timeout TIMEOUT] [--regex REGEX] FILE

positional arguments:
  FILE                  REQ/YAML/JSON file.

options:
  -h, --help            show this help message and exit
  -m MACRO, --macro MACRO
                        macros for request file e.g.: "SYS=TEST,DEV=D1"
  -o OUT, --out OUT     Output path/file.
  -f, --force           force save in case of disconnected PVs after timeout
  --labels LABELS       list of comma separated labels e.g.: "label_1,label_2"
  --comment COMMENT     Comment
  --timeout TIMEOUT     max time waiting for PVs to be connected
  --regex REGEX         Regex filter to be used when saving PVs
```

## Restore

Snapshot restore command allows to restore values to PVs based on a previously saved snap file via the cli.

```bash
usage: snapshot restore [-h] [-f] [--timeout TIMEOUT] [--regex REGEX] FILE

positional arguments:
  FILE               saved snapshot file

options:
  -h, --help         show this help message and exit
  -f, --force        force restore in case of disconnected PVs after timeout
  --timeout TIMEOUT  max time waiting for PVs to be connected and restored
  --regex REGEX      Regex filter to be used when restoring PVs
```

## Convert

Snapshot convert command is a utility function to convert Req files (soon to be deprecated) to the newer YAML/JSON formats.

```bash
-------- Command line convert mode --------
usage: snapshot.py convert [-h] [-o] [-u {.req,.yaml,.json}] [-t {yaml,json}] FILE

positional arguments:
  FILE                  input file to convert

optional arguments:
  -h, --help            show this help message and exit
  -o, --output-as-file  save output as file with same name (different suffix)
  -u {.req,.yaml,.json}, --update-include-suffix {.req,.yaml,.json}
                        update includes suffix (possibility to prepare for included files conversion)
  -t {yaml,json}, --to {yaml,json}
                        conversion output format

### Example: find <PATH> -iname "*.req" -exec python -m snapshot convert -o -u .yaml {} \;
```

## Format of configuration

The config snippet must be the first thing in the request file, before even any
comments. See the [example request file](example/test.req). It may contain the
following keys:

- "labels": a dict containing:

  - "labels": an array of labels that can be applied to snapshot files.
  - "force_labels": a boolean. If true, only labels defined here will be
    available for saving in the snapshot files. If false, additional labels that
    may be present in the existing files will also be available.

- "filters": a dict containing:

  - "filters": an array of predefined PV name filters that will be available
    from the filter drop-down menu.
  - "rgx_filters": same as "filters", except the filters are in regular
    expression syntax.

- "machine_params": an array of machine parameters, i.e. PVs that are not part
  of the request file, but whose values will be stored as metadata. It is an
  array of pairs `["param_name", "pv_name"]`, e.g. `["electron_energy", "SARCL02-MBND100:P-READ"]`. Within the program, the parameter is referred to
  as `param_name` for display and filetering purposes."

## Format of machine parameter filter expression

Unlike other filters, the machine parameter filter requires a specific syntax to
allow both exact and in-range comparisons of parameter values. The expression
consists of space-separated statements, e.g.

    second_param(value) first_param(low_value, high_value) ...

The above expression will match files where:

- the value of `second_param` is exactly `value`
- and the value of `first_param` is between `low_value` and `high_value`.

Each value can be

- an integer, which must not begin with 0;
- a float, with period as the decimal separator, must not begin with 0 or end
  with a period (i.e. write `1.0`, not `1.`);
- a string, which must be enclosed in double quotes and may contain backslash
  escape sequences.

Strings can be compared against numbers (and vice versa), and can be used for
in-rage checks, but the comparison will be lexicographic, not numeric.

Each parameter may only appear once. If the expression is invalid, it is shown
in red, and no filtering is applied to files.

## Format of saved files

When PVs values are saved using a GUI, they are stored in file where first line
starts with `#` and is followed by meta data (json formating). This is followed
by lines with PV names and saved data (one line per PV). Example:

```
#{"keywords": "key1,key2", "comment": "This is comment", "save_time": 1452670573.6637778}
examplePv:test-1,20
examplePv:test-2,30
examplePv:test-3,"string"
examplePv:test-4,[5.0, 6.0, 7.0, 8.0, 9.0, 0.0, 1.0, 2.0, 3.0, 4.0]
```

## Input file (REQ/YAML/JSON)

The _snapshot_ tool requires an input file (REQ, YAML or JSON) that contains a list of pvs and, optionally, labels, machine parameters, filters and macros.

> :warning: **"\*.req" files are deprecated**: After release V2.0.34 the support for *.req files will be removed, please use JSON/YAML file format.

An example of YAML file is as follows:

```bash
pvs:
  list:
    - name: examplePv:test-1
      precision: 5
    - name: examplePv:test-2
      precision: 2
    - name: examplePv:test-3
config:
  filters:
    - examplePv
    - test-3
  read_only: false
  rgx_filters:
    - - LabelForMyRgxFilter
      - examplePv.*
  force_labels: true
  labels:
    - LabelForFilterExample
  machine_params:
    - - LabelForMyMachineParam
      - examplePv:test-1
include:
- name: cfg/wf_included.yaml
```

The `include` section above is the so-called macro, it allows to easily include multiple pvs that follow similar naming patterns. The content of the `wf_included.yaml` file is below:

```bash
include:
  - name: wf.req
    macros:
      - { NAME: snapshot:test }
      - { NAME: fake:pvs }
```

and the content of the `wf.req` is:

```bash
$(NAME):wf_strings
$(NAME):wf_strings_large
$(NAME):wf_ints
$(NAME):wf_chars
$(NAME):wf_double
$(NAME):wf_double_prec_2
$(NAME):wf_double_prec_5
```

The macro functiona that combines `wf_included.yaml` and `wf.req` will result on a list of pvs as in:

```bash
snapshot:test:wf_strings
snapshot:test:wf_strings_large
snapshot:test:wf_ints
...
fake:test:wf_strings
fake:test:wf_strings_large
fake:test:wf_ints
...
```

# Development

## Installation

Snapshot is available as an Anaconda package on the paulscherrerinstitute
Anaconda package channel. It can be easily installed as follows:

```bash
conda install -c https://conda.anaconda.org/paulscherrerinstitute snapshot
```

## Testing

To test the application a softioc can be started as follows (while being in the
_tests_ directory):

```
docker run -it --rm -v `pwd`:/data -p 5064:5064 -p 5065:5065 -p 5064:5064/udp -p 5065:5065/udp docker.psi.ch:5000/patro_m/epics-base-7.0.6  softIoc -d /data/tests/softioc/ioc.db
```

A test _.req_ file (test.req) is located in the _tests_ directory as well.


# Authors

Paul Scherrer Institute: 

- Didier Voulout
- Leonardo Hax
- Maciej Patro
- Simon Ebner
