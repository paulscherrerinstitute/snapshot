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
Snapshot tool can be then started with following command (will be later packaged as conda package):
```
snapshot_app.py <path_to_request_file> -macros "MACRO1=M1,MACRO2=M2,..."
```
When PVs are saved using a GUI, they are stored in json file, which holds metada and pv values for all PVs listed in request file.

TODO:
- package as conda package
- filtering files by metadata
- filtering pvs on compare view by status
- improve Readme
- dialog to select request file from the GUI