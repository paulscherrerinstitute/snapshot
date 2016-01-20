# Snapshot tool
Snapshot tool is python based tool with graphical user interface which is able to store (and later restore) values of channel access process variables. PVs). 

## Dependencies:
 - python 3 (conda python 3.5 was used for development)
 - pyepics module
 - numpy module
 - json module


## Usage
To define a set of PVs which should be saved/restored snapshot tool requires a "request" file. Request files are in the following format (note that macro substitution is possible):

```
examplePv:test-1
examplePv:test-2
$(SYS):test-3
```

After snapshoot is build and deployed as conda package (see section TODO) it can be started with following command:

```
snapshot [-h] [-req REQ] [-macros MACROS] [-dir DIR]


optional arguments:
  -h, --help            show this help message and exit
  -req REQ, -r REQ      Request file
  -macros MACROS, -m MACROS
                        Macros for request file e.g.: "SYS=TEST,DEV=D1"
  -dir DIR, -d DIR      Directory for saved files
```

>  Due to a bug described in issue [CTRLHA-217])(https://tracker.psi.ch/jira/browse/CTRLHA-217), snapshot must be started in python interpreter (`-i`) mode. This is temporary solution. To start snapshot tool in interpreter mode `./utils/start_snapshot.py`) can be used with following command

```
python -i start_snapshot.py [-h] [-req REQ] [-macros MACROS] [-dir DIR]
```

## Format of saved files
When PVs values are saved using a GUI, they are stored in file where first line starts with `#` and is followed by meta data (json formating). This is followed by lines with PV names and saved data (one line per PV). Example:

```
#{"keywords": "key1,key2", "comment": "This is comment", "save_time": 1452670573.6637778}
examplePv:test-1,20
examplePv:test-2,30
examplePv:test-3,"string"
examplePv:test-4,[5.0, 6.0, 7.0, 8.0, 9.0, 0.0, 1.0, 2.0, 3.0, 4.0]
```

## Installation
Snapshot tool can be installed as anaconda package. Conda recipe is provided in folder `conda_recipe`.


# Know issues:
 - When the snapshot app is opened and requests PVs that are currently not on the network, first performed action (save / restore) takes quite a long time to finish (aprox N*5 seconds where N is number of PVs). The problem is that, Queued type of connection in Qt threading blocks saving/restoring until all PVs are connected for first time (or after 5 seconds of timeout). Will be fixed in next release.