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
When PVs are saved using a GUI, they are stored in file where first line starts with `#` and is followed by meta data (json formating). This is followed by lines with PV names and saved data (one line per PV). Example:

```
#{"keywords": "key1,key2", "comment": "This is comment", "save_time": 1452670573.6637778}
examplePv:test-1;20
examplePv:test-2;30
examplePv:test-3;"string"
examplePv:test-4;[5.0, 6.0, 7.0, 8.0, 9.0, 0.0, 1.0, 2.0, 3.0, 4.0]
```


TODO:
- package as conda package
- filtering files by metadata
- filtering pvs on compare view by status
- improve Readme
- dialog to select request file from the GUI