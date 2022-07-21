Changelog
=========


(unreleased)
------------
- Release: version. [Leonardo Hax Damiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [Leonardo Hax Damiani]
- Fix code style issues with Black. [Lint Action]
- Removal flake. [Leonardo Hax Damiani]
- CI autofix python version. [Leonardo Hax Damiani]
- CI test autofix. [Leonardo Hax Damiani]
- Black formatting. [Leonardo Hax Damiani]
- Black formatting. [Leonardo Hax Damiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [Leonardo Hax Damiani]
- Delete test_latest.snap. [Leonardo Hax Damiani]
- Delete lint.yaml. [Leonardo Hax Damiani]
- Infrastructure files. [Leonardo Hax Damiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [Leonardo Hax Damiani]
- Merge branch 'master' into export_selected_feature. [lhdamiani]
- Update lint.yml. [Leonardo Hax Damiani]
- Update lint.yml. [Leonardo Hax Damiani]
- Create lint.yml. [Leonardo Hax Damiani]
- Create lint.yaml. [Leonardo Hax Damiani]
- Merge branch 'master' into export_selected_feature. [lhdamiani]
- Metadata fix for files without extension type. [lhdamiani]
- Updated readme. [lhdamiani]
- Copy to clipboard pvs+values. filter combobox filter fix. [Leonardo
  Hax Damiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [lhdamiani]
- Bump build number. [Leonardo Hax Damiani]
- Delete .vscode directory. [Leonardo Hax Damiani]
- Wip: test conda channel to workflow. [Leonardo Hax Damiani]
- Bump build number. [Leonardo Hax Damiani]
- Bugfix sorting unit columns with None. [Leonardo Hax Damiani]
- Updated export csv feature including old snap values. [lhdamiani]
- Bugfix set new output dir. [lhdamiani]
- Bugfix update_rate. fix for convert cmd. [Leonardo Hax Damiani]
- Bump version and build. [Leonardo Hax Damiani]
- Fix not filtered pvs tolerance. [Leonardo Hax Damiani]
- Tolerance update via filters (connected+view) [lhdamiani]
- Couple of fixes: - now period of updates actually changes - ca context
  is now shared for mutliple workers - in case of initial fetch data is
  handled in multithread   manner otherwise single-threading is faster
  because of   ca context handling... [Maciej Patro]
- Resize filename column on restore widget. [lhdamiani]
- Improve snapshot performance: - Avoid direct communication with PV in
  case precision/unit/enum_str is not defined - Parallel execution for
  periodic fetching of PV values. [Maciej Patro]
- Restore widget labels with AND instead of OR. [lhdamiani]
- Tolerance applied only to filtered pvs. [lhdamiani]
- Removal of Eff. Tol. for string pvs. [lhdamiani]
- Set default pv update rate 5s. [Leonardo Hax Damiani]
- Set default pv update rate to 5s. [Leonardo Hax Damiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [lhdamiani]
- Updated Eff. Tol. tooltip. [Leonardo Hax Damiani]
- Bugfix crash when 3rd snap file was selected. [Leonardo Hax Damiani]
- Pvupdate time combobox. bugfix enumstrings. [lhdamiani]
- Wip: no columns resize for performance evaluation. [lhdamiani]
- Restore cli cmd requires snap files to be loaded (similar to req
  files) [lhdamiani]
- Restore cmd with regex filters. [lhdamiani]
- Bugfix enum_str index range. [lhdamiani]
- WarningBox when macros json/yaml file can't be properly loaded.
  [lhdamiani]
- Test files for pco setup. [lhdamiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [lhdamiani]
- Improve readability for lassThan function. [Maciej Patro]
- Updated readme including convert -h. [lhdamiani]
- Sorting improved. [Maciej Patro]
- Full functionality of converter introduced. [Maciej Patro]
- PVs handling updated, converter functionality introduced. [Maciej
  Patro]
- Cleanup precision tests. [lhdamiani]
- Ongoing introduction of converter req2json/req2yaml. [Maciej Patro]
- Fix for includes in request files. [Maciej Patro]
- Fix regex filters without a label. [lhdamiani]
- Including inside json/yaml files is now supported. - metadata from
  included files is completely ignored. [Maciej Patro]
- SnapshotJsonFile - metadata loading cleanup. [Maciej Patro]
- Fix regex filters handling for .req files and align with json/yaml.
  [Maciej Patro]
- Ongoing refactoring of json handling. [Maciej Patro]
- Ongoing cleanup of SnapshotJsonFile.py. [Maciej Patro]
- Move Snapshot file classes to separate files. [Maciej Patro]
- Fix problem with handling metadata in .req files + remove
  functionality connected only to json. [Maciej Patro]
- Remove unused code in SnapshotJsonFile - these parts are only for
  ".req" files. [Maciej Patro]
- Create (copy-paste) SnapshotJsonFile class and start using it for
  handling json files. [Maciej Patro]
- Use the create function instead of direct constructor. [Maciej Patro]
- Extract SnapshotReqFile to separate file. [Maciej Patro]
- Bugfix moving cursor in textChanged for predefined filters.
  [lhdamiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [lhdamiani]
- Add full support for yaml files. [Maciej Patro]
- Refactoring of read_input - simplify the code keeping previous
  functionality intact. [Maciej Patro]
- Ioc.yaml file introduced for test - port of ioc.json. [Maciej Patro]
- Code inspection fixes. [Maciej Patro]
- Optimize imports and ensure consistent absolute importing is in place.
  [Maciej Patro]
- Bugfix regex filters not appearing. [lhdamiani]
- Read only warnings to user. [lhdamiani]
- Update comparison after tolerance changes. [lhdamiani]
- Variables names with _ instead of - [lhdamiani]
- Pattern for naming variables ( _ instead of - ) [lhdamiani]
- Readonly mode (via json) and restore widget spacer. [lhdamiani]
- Updated readme. [lhdamiani]
- Read only cli param to disable restore buttons. [lhdamiani]
- Revert "checkbox to not restore after save" [lhdamiani]

  This reverts commit 5a7deb162aaf914c8adee3430641c2fd35f87e0e.
- Fix whitespaces in dockefile. [Maciej Patro]
- Dockerfile to be used for testing with epics 7.0.6 introduced. [Maciej
  Patro]
- Checkbox to not restore after save. [lhdamiani]
- Code improvements. [lhdamiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [lhdamiani]
- Add number of waverforms - currently commented out - initialization of
  waveform requires epics version >= 7.0.2 docker image   with supported
  version to be found. [Maciej Patro]
- Bugfix snap files filtering widgets and new thread with executor.
  [lhdamiani]
- Update the ioc for tests. [Maciej Patro]
- Minor code improvements. [lhdamiani]
- Bugfix retrieval snap files to restore widget. [lhdamiani]
- Wip soft iocs for testing purposes. [lhdamiani]
- Bugfix removal of unused float subclass. [lhdamiani]
- Updated readme about save cmd. [lhdamiani]
- Regex filter param for snapshot save cmd. [lhdamiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [lhdamiani]
- Merge pull request #39 from paulscherrerinstitute/master. [Leonardo
  Hax Damiani]

  master commits merge
- Precision defined via json and code improvements. [lhdamiani]
- Confirmation dialog before 'restore all' [lhdamiani]
- Debug instructions with json file for default. [lhdamiani]
- Updated json with pvs/config structure. [lhdamiani]
- View conn/disconn filter dropdown. fix Eff. Tol. formula/emit.
  [lhdamiani]
- Bugfix 'Select labels' appearing as label. code improvements.
  [lhdamiani]
- Improved json structure. general code improvements. [lhdamiani]
- Integer values in column. [lhdamiani]
- Minor improvements and refactoring. [lhdamiani]
- Merge branch 'export_selected_feature' of
  https://github.com/paulscherrerinstitute/snapshot into
  export_selected_feature. [lhdamiani]
- Combobox for filter now to display up to 30 visible items. [Maciej
  Patro]
- Deprecation message for *.req files introduced. [Maciej Patro]
- Update unit tests + introduce requirements.txt file for development
  purposes. [Maciej Patro]
- Minor improvements and refactors. [lhdamiani]
- Str value on GUI based on the pv's enum_strs. [lhdamiani]
- Precision reload flag. bugfix float with precision 0. [lhdamiani]
- Debug vscode file. [lhdamiani]
- PV's effective tolerance column and tooltip. [lhdamiani]
- Added sf-cagw epics_ca_addr_list to debug file. [lhdamiani]
- Periodic pv improved with last status and color. [lhdamiani]
- Dialog to get new output directory via menu. [lhdamiani]
- Max items on dropdown labels menu. [lhdamiani]
- Set output directory feature on menu. [lhdamiani]
- Rgx labels next to the dropdown menu. [lhdamiani]
- Removal of PREC and EGU from snap files. [lhdamiani]
- Yaml removal. json improved. [lhdamiani]
- Improved json template. [lhdamiani]
- Debugger config for vscode. [lhdamiani]
- Req file with filters for test. [lhdamiani]
- Clean unused enum class. [lhdamiani]
- Cleaning debug msg. [lhdamiani]
- Checkbox to toggle pvs based on their connection status. [Leonardo
  Hax]
- Visualization dropdown disconn/conn pvs. [lhdamiani]
- Export selected pvs to csv file feature. [lhdamiani]
- Cleanup and compatibility fix. [lhdamiani]
- Unit test parser. [lhdamiani]
- Cleanup and reorganization. [lhdamiani]
- Removal of duplicate. [lhdamiani]
- Yaml fixes. epics3 deprecate dependency fix. [lhdamiani]


2.0.33 (2022-06-02)
-------------------
- Bugfix files without extension (req is default) [lhdamiani]
- Pyyaml dependency added to recipe. [Leonardo Hax Damiani]
- Merge pull request #41 from paulscherrerinstitute/py38fix. [Leonardo
  Hax Damiani]

  Fix python 3.10 explicit integer cast arg
- Py3.10 fix for integer arg. bugfix content variable. [lhdamiani]
- Build dep pyepics. [lhdamiani]
- Merge pull request #40 from paulscherrerinstitute/py38fix. [Leonardo
  Hax Damiani]

  bugfix when parsing req files
- Bugfix content when parsing req files. [lhdamiani]
- Removed dependency to epics.utils3. [ebner]
- Cleanup - removed obsolete build. [ebner]
- Add manual trigger. [ebner]
- Test. [ebner]
- Add github action workflow. [ebner]


2.0.31 (2021-10-11)
-------------------
- Bump version to 2.0.31. [ebner]
- Merge pull request #38 from xiaoqiangwang/master. [Simon Gregor Ebner]

  catch exception of unequal length arrays
- Catch exception of unequal length arrays. [Xiaoqiang Wang]


2.0.30 (2021-05-26)
-------------------
- Merge branch 'pep8' [lhdamiani]
- Code improvements. [lhdamiani]
- Yml pco example. snapshot_ca improvements. [lhdamiani]
- Merge pull request #37 from paulscherrerinstitute/pep8. [Simon Gregor
  Ebner]

  Json + YML imports + Pep8
- Import via yaml file, clean up and minor adjusts. [lhdamiani]
- Pv list using json load and keys. [lhdamiani]
- Fix libca not found error. [lhdamiani]
- Pco test camera ioc for tests. [lhdamiani]
- Autopep8 formatting. [lhdamiani]
- Bump version. [Simon Ebner]
- Merge pull request #35 from exzombie/fix-disconnected-save-crash.
  [Simon Gregor Ebner]

  Fix crash when force-saving disconnected PVs
- Fix crash when force-saving disconnected PVs. [Jure Varlec]
- Bump version. [Simon Ebner]
- Merge pull request #34 from exzombie/bugfixes. [Simon Gregor Ebner]

  Fix minor annoyances
- Allow reducing the number of columns when rebuilding file list. [Jure
  Varlec]
- Don't freeze when opening a snapshot before PVs are initialized. [Jure
  Varlec]
- Stop drawing PV table header in bold whenever anything is selected.
  [Jure Varlec]
- Fix the way snapshot comparison behaves with disconnected PVs. [Jure
  Varlec]


2.0.28 (2020-05-22)
-------------------
- Bump version. [Simon Ebner]
- Merge pull request #33 from exzombie/machine-param-polish. [Simon
  Gregor Ebner]

  Machine param polish
- Change error color of param filter widget to match PV filter widget.
  [Jure Varlec]
- Change default precision to 6, matching what python formatter does.
  [Jure Varlec]
- Display machine param units in column headers instead of the table.
  [Jure Varlec]
- Use tolerance when comparing machine parameters for equality. [Jure
  Varlec]
- Ensure that machine params are a dict, use prec and unit for display.
  [Jure Varlec]
- Ensure the comment column is not wider than filename column. [Jure
  Varlec]
- Store also units and precision of machine parameters. [Jure Varlec]


2.0.27 (2020-05-22)
-------------------
- Bump version. [Simon Ebner]
- Merge pull request #32 from exzombie/consolidate-arrays. [Simon Gregor
  Ebner]

  Bug fixes: array handling, saving disconnected PVs, restore filtered PVs
- Fix the way the filtered list of PVs is passed to the restore widget.
  [Jure Varlec]
- Don't grow the list of filtered PVs indefinitely. [Jure Varlec]
- Handle corrupt snapshot files also in legacy format. [Jure Varlec]
- Consolidate arrays: everything is converted to ndarray at the source.
  [Jure Varlec]

  This also handles the pyepics one-element array weirdness in one place. Ok, in
  two places, really, because PvUpdater does its own getting.
- Correct the one-element-array test in save_pv() [Jure Varlec]

  It used to save one-element arrays as `[[value]]`, which is invalid. Apparently,
  pyepics is quite inconsistent regarding one-element arrays, so we always need to
  check whether we got an array or not. Or maybe the behavior has changed with
  later versions.
- Detect old corrupt snapshots with two-dimensional one-element arrays.
  [Jure Varlec]
- Quickly skip over disconnected and uninitialized PVs when saving.
  [Jure Varlec]
- Merge pull request #31 from exzombie/metadata-features. [Simon Gregor
  Ebner]

  Metadata features
- Document machine parameter filter expressions. [Jure Varlec]
- Forbid punctuation in param names that could interfere with filters.
  [Jure Varlec]
- Increase max allowed comparison tolerance, update label. [Jure Varlec]
- Update Readme and examples with info on config metadata. [Jure Varlec]
- Linewrap the Readme. [Jure Varlec]
- Only suspend the pv_updater thread with autorefresh checkbox. [Jure
  Varlec]
- Change machine param config format to support short param names. [Jure
  Varlec]

  - Machine params are stored as param_name-pv_name pairs.

  - The pairs are in a list to maintain ordering. Internally, the list is a dict
    because python has ordered dicts nowadays.

  - There is a right-click menu option to copy the PV name.
- Save defined machine parameters in the snapshot. [Jure Varlec]
- Implement filtering on machine paramaters. [Jure Varlec]
- Add menu entries for copying machine parameter name and value. [Jure
  Varlec]
- Ensure machine param dict is always present in file metadata. [Jure
  Varlec]
- Display machine parameters in the file selector. [Jure Varlec]
- Read existing machine params from snapshot files. [Jure Varlec]
- Change layout of restore widget, make space for machine param filter.
  [Jure Varlec]
- Make request file metadata same as config file for easier transition.
  [Jure Varlec]

  Config files are still supported. The places where stuff needs to be changed
  to remove support are marked with TODO.

  Only the top-level request file may have the JSON snippet at the top, included
  files must not.
- Read machine parameters from req file. [Jure Varlec]
- Additional checks for file access exceptions. [Jure Varlec]
- Read filters from request file metadata. [Jure Varlec]
- Change how config file is merged into defaults, cleaner config dict.
  [Jure Varlec]
- Tweak request file error messages. [Jure Varlec]
- Allow JSON header in request files. Right now, only 'labels' are used.
  [Jure Varlec]
- Bump version. [Simon Ebner]
- Merge branch 'master' of github.com:paulscherrerinstitute/snapshot.
  [Simon Ebner]
- Merge pull request #30 from exzombie/autorefresh. [Simon Gregor Ebner]

  Cleanup, background file scanning, various tweaks and fixes
- Better reconnect handling courtesy of pyepics-3.4. [Jure Varlec]
- Show only snapshot timestamp in PV table headers. [Jure Varlec]
- Clear out snap columns from the compare widget on file list refresh.
  [Jure Varlec]
- Simplify PV table column resizing. [Jure Varlec]
- Fix the problem of disappearing filter menu. [Jure Varlec]
- Use a saner way to make the PV filter combo stretchable. [Jure Varlec]
- Don't crash when opening a non-existing snapshot. [Jure Varlec]
- Add autorefresh toggle widget. [Jure Varlec]
- Add a "Quit" menu entry. [Jure Varlec]
- Delay starting the file scanner. [Jure Varlec]
- Add a background file scanner to detect changes in snapshot files.
  [Jure Varlec]

  The "Refresh" button is colored red to indicate that a refresh is needed.
- Factor periodic task execution from PvUpdater into a base class. [Jure
  Varlec]
- Factor listing of save files out of get_save_files() [Jure Varlec]
- Fix duplicated labels in snapshot filter dropdown. [Jure Varlec]
- Stop pretending the snapshot list is ever "updated", it is always
  rebuilt. [Jure Varlec]
- Tweak the way PvUpdater is registered with background_workers. [Jure
  Varlec]
- Only parse snapshots once on startup. [Jure Varlec]
- Remove a redundant check. [Jure Varlec]
- Improve performance of scalar comparison. [Jure Varlec]
- Change tracing message format. [Jure Varlec]
- Add a pause/resume background threads tracing message. [Jure Varlec]
- Potential fix packaging. [Simon Ebner]
- Bump version. [Simon Ebner]
- Merge pull request #29 from exzombie/comparison_tolerance. [Simon
  Gregor Ebner]

  Comparison tolerance
- Fix crash when opening a menu without a selected snapshot. [Jure
  Varlec]
- A workaround for inconsistent string encodings. [Jure Varlec]
- Fix a typo in a variable name. [Jure Varlec]
- Disallow moving comparison columns. [Jure Varlec]
- Minor performance improvement to update_pv_value() [Jure Varlec]
- Improve string conversion performance for scalars. [Jure Varlec]
- Improve performance by caching precision and is_array. [Jure Varlec]
- Replace the slow numpy.array2string() with a custom formatter. [Jure
  Varlec]
- Compare snapshot values to each other. [Jure Varlec]
- Add a transparent EQ icon as a spacer for snapshot values. [Jure
  Varlec]
- Remove comparison column, show neq icon with snapshot value. [Jure
  Varlec]
- Add "Process PV" right-click menu. [Jure Varlec]
- Move parse_to_save_file to parser.py. [Jure Varlec]
- Only close the main window after the event loop is running. [Jure
  Varlec]
- Introduce JSON values in snapshots, store EGU and PREC. [Jure Varlec]
- Display all decimals (zero-filled) required by PREC. [Jure Varlec]
- Honor PV precision for comparison, don't crash on PREC < 0. [Jure
  Varlec]
- Honor PV precision for display strings. [Jure Varlec]
- Consolidate string formatting in GUI, remove conversion to bytes.
  [Jure Varlec]

  This also abbreviates waveforms longer than 3 elements. The display was useless
  anyway.

  The issues pyepics had with consuming strings seem to have been fixed since the
  tool was first developed, so encoding to bytes is not needed anymore.
- Remove unused value_as_str() [Jure Varlec]
- Compare: more readable update_pv_value() [Jure Varlec]
- Merge pull request #28 from exzombie/gui_tweaks. [Simon Gregor Ebner]

  Gui tweaks and bug fixes
- Remove the "Advanced" label from the save widget. [Jure Varlec]
- Remove the _latest symlink when deleting files. [Jure Varlec]
- Extend the "File name" column label. [Jure Varlec]
- Make comparison widget bigger. [Jure Varlec]
- Complete transition to named column indices. [Jure Varlec]
- Fix snapshot deletion. [Jure Varlec]
- Fix restore access warnings. [Jure Varlec]
- Fix PyQt StandardButton incompatibility. [Jure Varlec]
- Make package python only. [Simon Ebner]
- Merge branch 'master' of github.com:paulscherrerinstitute/snapshot.
  [Simon Ebner]
- Merge pull request #27 from exzombie/master. [Simon Gregor Ebner]

  Fix regex filter loading
- Fix regex filter loading. [Jure Varlec]
- Bump version to 2.0.19. [Simon Ebner]
- Potential fix ? [Simon Ebner]
- Fix bug. [Simon Ebner]
- Version bump. [Simon Ebner]
- Merge branch 'master' of github.com:paulscherrerinstitute/snapshot.
  [Simon Ebner]
- Merge pull request #26 from exzombie/parallel-startup. [Simon Gregor
  Ebner]

  Parallel startup, minor GUI enhancements
- Delete transient menus after use. [Jure Varlec]
- Restore widget: add copy to clipboard to context menu. [Jure Varlec]
- Use named indices for PV table columns, add EGU column. [Jure Varlec]
- Read ctrlvars of a PV in the updater thread. [Jure Varlec]
- Add confirmation dialog to restore PVs. [Jure Varlec]
- Remove unwanted info from save and restore widgets, name file selector
  cols. [Jure Varlec]
- Make the save widget smaller than restore widget. [Jure Varlec]
- Fix an old, dormant issue in restore code, improve comments. [Jure
  Varlec]
- Add a more detailed explanation of background_workers. [Jure Varlec]
- Compare widget: set default visualization on new PVs. [Jure Varlec]
- Qt5 porting fixes. [Jure Varlec]

  - Replace setMargins with setContentsMargins instead of setSpacing
  - Reenable commented table header settings, replace deprecated functions
- Remove the settings dialog. [Jure Varlec]

  It was broken in more than one way. The ability to change macros
  was already removed in the past (e.g. 9e9b2fd43ccb22143933f98b106001c0ab7df2ae).
  It is better to just reload the request file, which is also better tested.
- Change variable case for consistency. [Jure Varlec]
- Optionally print tracing info on stdout. [Jure Varlec]
- Parallelize opening of request files. [Jure Varlec]
- Properly close the main window, don't short-circuit shutdown code.
  [Jure Varlec]
- Parallelize opening snap files. [Jure Varlec]
- Only construct icons once. [Jure Varlec]
- Open req file in parallel, reading snap files in a separate thread.
  [Jure Varlec]
- Allow Snapshot to be constructed without a request file. [Jure Varlec]
- Refactor snap parsing into standalone functions. [Jure Varlec]
- Move config file parsing out of the GUI. [Jure Varlec]
- Version update. [Simon Ebner]
- Merge pull request #25 from exzombie/fix-save. [Simon Gregor Ebner]

  Improvements to error handling on save and background pvget
- Simplify completion of background pvget from SnapshotPv.get() [Jure
  Varlec]

  Instead of restricting which arguments can be passed to SnapshotPv.get(),
  PvUpdater installs a completion function into SnapshotPv which allows
  it to complete the transaction and then do its own thing. The
  arguments to ca.get() used by SnapshotPv and by PvUpdater thus do not
  need to be related.
- Always perform get() when saving PVs. [Jure Varlec]
- Make PV.value always return cache, but call get() the first time.
  [Jure Varlec]

  Some internal PV functions will call get() (auto_monitor is off and
  get() needs to be called to initialize some data). Ensure that the
  get() is actually performed at least once.
- Do asynchronous PV update in the initial context. [Jure Varlec]

  This is related to commit e90da91b3d9ddfec4cf2829014859f403d8787bb
  The workaround there was to use a separate context for background
  updates, which worked, but introduced the possibility of the two
  contexts to be out of sync with regard to the connection status.

  This commit reverts back to the original behaviour, i.e. the
  background thread uses the same context (and PV objects) as the main
  thread, eliminating potential issues. The original problem stems from
  the fact that PvUpdater requested different data using ca.get() than
  PV.get() did. When PV.get() tried to complete the request, it got data
  that it didn't expect. The calls are now compatible.
- Show empty values on update timeout, do compare (may be empty in
  snapshot) [Jure Varlec]
- Catch and log all errors on save. [Jure Varlec]
- Fix that comment is not used when saving. [Simon Ebner]
- Fix context menu. [Simon Ebner]
- Fix advanced option. [Simon Ebner]
- Bump version. [Simon Ebner]
- Always show advanced options. [Simon Ebner]
- Merge pull request #24 from exzombie/pv-polling. [Simon Gregor Ebner]

  Poll PV values instead of subscribing to monitors
- Fix a rare crash on mass PV reconnect. [Jure Varlec]
- Provide an public interface in SnapshotPv for updating cached value.
  [Jure Varlec]
- Update docstrings. [Jure Varlec]
- Account for the time required for taking the lock in PvUpdater. [Jure
  Varlec]
- Use a separate CA context in PvUpdater. [Jure Varlec]

  It turned out that PV methods do not handle well the case of
  incomplete ca.get() operations for some reason, causing exceptions
  when PvUpdater experienced timeouts.
- Throttle the PvUpdater so that it waits for the GUI to finish. [Jure
  Varlec]
- Suspend background thread during long-running operations. [Jure
  Varlec]
- Allow PV gets and puts while PvUpdater is running. [Jure Varlec]
- Reenable comparison on value update. [Jure Varlec]
- Override the SnapshotPv.value property, values provided by PvUpdater.
  [Jure Varlec]
- Mark PV update slot as internal. [Jure Varlec]
- Gitignore: egg info for installation in editable mode. [Jure Varlec]
- Handle PV connection status changes. [Jure Varlec]
- Update comment. [Jure Varlec]
- Don't reset the filter proxy model on every single PV update. [Jure
  Varlec]

  This lets the underlying Qt proxy model handle the dataChanged()
  signal and filtering. It's smarter and doesn't rebuild the whole proxy
  on every update. The view can then request and redraw only data that
  is currently being viewed instead of the whole thing.
- Remove a superfluous dict. [Jure Varlec]
- Introduce a polling thread for fetching PV values. [Jure Varlec]
- Disable PV monitoring, deactivate callbacks. [Jure Varlec]

  Callbacks are not removed as they will be refactored later.


2.0.10 (2020-02-13)
-------------------
- QT fixes. [Simon Ebner]
- Bump version to 2.0.9. [Simon Ebner]
- Fix bug. [Simon Ebner]
- Remove testfiles. [Simon Ebner]
- Bump version. [Simon Ebner]
- Migration QT4 to QT5. [Simon Ebner]
- Add some more tests, update git ignore. [Simon Ebner]


2.0.7 (2020-02-05)
------------------
- Bump version. [Simon Ebner]
- Merge pull request #23 from exzombie/refactor-parsing. [Simon Gregor
  Ebner]

  Refactor parsing to improve startup performance
- Fix metadata editing where filename was used instead of path. [Jure
  Varlec]
- Show errors that occur when parsing snapshot data. [Jure Varlec]
- Load snapshot data from file when opening a snapshot or restoring.
  [Jure Varlec]
- On startup and refresh, only parse snapshot metadata, not data. [Jure
  Varlec]


2.0.6 (2018-10-30)
------------------
- Add sleep, resize column. [Simon Ebner]


2.0.5 (2018-10-30)
------------------
- Add try around filesystem operation. [Simon Ebner]


2.0.4 (2018-10-30)
------------------
- Version 2.0.4. [Simon Ebner]
- Add refresh button adjust sorting. [Simon Ebner]
- Use monitor value for snapshot. [Simon Ebner]
- Add timeout and log messages. [Simon Ebner]


2.0.3 (2018-10-19)
------------------
- Version 2.0.3. [Simon Ebner]
- Add reduction of emits. [Simon Ebner]


2.0.2 (2018-10-12)
------------------
- Remove forgotten print statement. [Simon Ebner]
- Add test ioc and req file. [Simon Ebner]
- Remove rate throttling and decreased gui update intervall. [Simon
  Ebner]
- Version 2.0.1. [Simon Ebner]
- Fix attribute name. [Simon Ebner]
- Do not use monitor for taking snapshot. [Simon Ebner]
- Merge pull request #21 from paulscherrerinstitute/refactor. [Simon
  Gregor Ebner]

  Refactor
- Remove fix version. [ebner]
- Upgrade version. [Simon Ebner]
- Fix. [Simon Ebner]
- Fix. [Simon Ebner]
- Attemp to limit update rate on gui. [Simon Ebner]
- Remove unecessary code. [Simon Ebner]
- Improve channel creation. [Simon Ebner]
- Add statistic numbers. [Simon Ebner]
- Fix. [Simon Ebner]
- Added init.py. [Simon Ebner]
- Add test for snaphot class. [Simon Ebner]
- Recactoring. [Simon Ebner]


1.7.2 (2018-06-29)
------------------
- Update version. [ebner]
- Merge pull request #20 from ganymede42/master. [Simon Gregor Ebner]

  improve startup time
- Improve startup time. [Thierry Zamofing]

  instead of parsing all files in the snapshot directory, only parse those with the common prefix
- Fix 3.6 build. [ebner]
- Add build for python 3.6. [ebner]


1.7.1 (2017-04-07)
------------------
- Update version to 1.7.1. [ebner]
- Fix latest link. [ebner]
- Merge pull request #19 from paulscherrerinstitute/cmd_labels_comments.
  [Simon Gregor Ebner]

  Cmd labels comments
- Fix upload config to only upload on new tag. [ebner]
- Merge pull request #18 from paulscherrerinstitute/restore_selected.
  [Simon Gregor Ebner]

  Restore selected


1.7.0 (2017-03-17)
------------------
- Readme. [Vintar Rok]
- Adding option to have labels and comment in command line. [Vintar Rok]
- Bug fix ... apply filter when changing selected file or PV changes
  value. [Vintar Rok]


1.6.0 (2017-03-01)
------------------
- Bug fix. [Vintar Rok]
- Bypassing pyepics waveform of strings problem. [Vintar Rok]
- Remove pyepics code used for debugging. [Vintar Rok]
- Version change in setup.py and meta.yaml. [Vintar Rok]
- Visualization fix. [Vintar Rok]
- Small visualization change. [Vintar Rok]
- Hack to work with string waveforms. [Vintar Rok]
- Bug fix. [Vintar Rok]
- Restore only selected PVs. [Vintar Rok]


1.5.6 (2017-02-03)
------------------
- Fixed builds. [ebner]
- Merge pull request #17 from paulscherrerinstitute/file_load_fix.
  [Simon Gregor Ebner]

  snapshot can hangup at load time -> fixed
- Version change. [Vintar Rok]
- Cosmetics. [Vintar Rok]
- Update GUI periodically not on every change, since big numer of
  changing channels can freeze the application. [Vintar Rok]


1.5.5 (2016-12-22)
------------------
- New version 1.5.5. [ebner]
- Add back some capturing of the return values. [ebner]
- Increase version. [ebner]
- Fix bug. [ebner]
- Add appveyor build status. [ebner]
- More Fix for appveyor config. [ebner]
- Fix appveyor config. [ebner]
- Add config for appveyor. [ebner]
- Add travis build icon. [ebner]
- Add travis build file. [ebner]
- Apply some code cleanup. [ebner]

  Some minor code cleanup
- Update metadata and readme. [ebner]

  Minor "fixes" in the setup.py and Readme.md
- Remove doc folder. [ebner]

  The doc folder does not hold any easy to use and additional information. Moreless it convolutes the commits so that changes are not always visible at a glance.
  Therefore it was decided to remove this folder and not keep it.

  If you need to have a look at the usage, please refer to the code. Also the API intendent to be used is/will be briefly described in the Readme.md
- Merge pull request #16 from paulscherrerinstitute/err_report. [Simon
  Gregor Ebner]

  Err report
- Readme and example update. [Vintar Rok]
- Doc update. [Vintar Rok]
- Version to 1.5.3. [Vintar Rok]
- Remove undefined states in save and restore procedure on GUI. [Vintar
  Rok]
- Merge pull request #15 from paulscherrerinstitute/conn_fix. [Simon
  Gregor Ebner]

  Conn fix


1.5.2 (2016-12-09)
------------------
- Nicer implementation. [Vintar Rok]
- Version changed to 1.5.2. [Vintar Rok]
- Internal docs updated. [Vintar Rok]
- Improved changing macros on gui. [Vintar Rok]
- Not needed after refactor. [Vintar Rok]
- Additional small fix handling base path. [Vintar Rok]
- Leave pyepics and garbage collector to handle the channels + some
  minor fixes with gui and changing macros. [Vintar Rok]
- First add callbacks and then set defaults if needed. this way we
  cannot miss a calback. [Vintar Rok]
- Base path fix. [Vintar Rok]
- Fixes in comparison of waveforms + fix of restoring filtered only.
  [Vintar Rok]
- Fix conenction callbacks +  settings dialog in gui. [Vintar Rok]
- Updated docs. [Vintar Rok]
- Nicer imports. [Vintar Rok]
- Remove Snapshot.all_connected status because it is no more needed.
  [Vintar Rok]
- Merge docs. [Vintar Rok]
- Example+docs. [Vintar Rok]
- Epics updates self.connected after the connection callbacks and this
  brokes the functionallity. [Vintar Rok]
- Merge pull request #14 from
  paulscherrerinstitute/default_save_dir_fix. [Simon Gregor Ebner]

  minor fix defining default save directory
- Merge pull request #13 from paulscherrerinstitute/req_upgrade. [Simon
  Gregor Ebner]

  Implementation of COSYLAB-912 and COSYLAB-911
- Fix link in readme. [ebner]


1.5.1 (2016-11-28)
------------------
- Additional fixes. [Vintar Rok]
- Bug fix. [Vintar Rok]
- Version changed. [Vintar Rok]
- Minor fix defining default save directory. [Vintar Rok]


1.5.0 (2016-11-28)
------------------
- Version change. [Vintar Rok]
- Minor change to avoid occasionaly crashin, when user wants to close
  the config window. [Vintar Rok]
- Readme update. [Vintar Rok]
- Recursive loading of request files. [Vintar Rok]
- Minor fixes. [Vintar Rok]
- Files reorganization. [Vintar Rok]
- Remove double actions on PV table styling (faster GUI response)
  [Vintar Rok]
- Indication of changing request file added. [Vintar Rok]
- Loging statuses faster. [Vintar Rok]
- Dir path is now class constant (faster GUI loading) [Vintar Rok]
- Minor fixes. [Vintar Rok]
- More proper way of handling columsn in PV list. [Vintar Rok]
- New compare widget (view/model based) which is updated directly by PV
  calback + reorganization of code for easier maintainance. [Vintar Rok]
- Save and restore functionallities fixed in gui tool (compare still not
  working) [Vintar Rok]
- Partial refeactor (gui not working) ... remove live compare
  functionallity from the snapshot core functionallity (ca part) [Vintar
  Rok]
- Update Readme. [ebner]
- Merge pull request #12 from paulscherrerinstitute/development. [Simon
  Gregor Ebner]

  Predefined labels and filters + sort by time


1.4.0 (2016-11-03)
------------------
- Fixing bugs in file selector update. [Vintar Rok]
- Remove duplicate predefined labels. [Vintar Rok]
- Time formating for modif time sorting must start with a year not a
  day. [Vintar Rok]
- Config file: force-label, bug fixed + version numbers raised. [Vintar
  Rok]
- New screenshot. [Vintar Rok]
- Doc updated. [Vintar Rok]
- Config file handling with labels and predefined filters. [Vintar Rok]
- Labels handling from config file and command line atribute. [Vintar
  Rok]
- Sort PVs added. [Vintar Rok]
- Sort files by time added. [Vintar Rok]
- Regex bette rhandling + indication of syntax problem. [Vintar Rok]
- Filter pv by regex. [Vintar Rok]
- Old styls signal slots to new style signal slots. [Vintar Rok]
- Restore filtered-only option added. [Vintar Rok]
- Bug fix: compare mode..single-file or multi-file, was behind for 1
  click. [Vintar Rok]
- Core supports resotring a slected subset of a PVs. [Vintar Rok]
- Fix for predefined labels when editing metadata. [Vintar Rok]
- Predefined labels for GUI tool. [Vintar Rok]


1.3.3 (2016-10-04)
------------------
- Proper way of handling the prolem form previous commit. This fiyes
  problems for pyepics 3.2.4 and possibily odler version. Newer versions
  should not have this problem by default. [Vintar Rok]
- When closing the app, call finalize_libca() to disconnect all PVs.
  [Vintar Rok]


1.3.2 (2016-10-03)
------------------
- Version change to 1.3.2. [Vintar Rok]
- Warnings for a problematic saved files (no meta data, false meta data,
  bad value, ...) are shown to user when the snapshot is opened. [Vintar
  Rok]


1.3.1 (2016-09-27)
------------------
- Consistency of the arguments (old style arguments are silently
  handled). [Vintar Rok]
- Bug updating the snap file list fixed. [Vintar Rok]
- Fixed dependencies list. [ebner]


1.3.0 (2016-08-15)
------------------
- Updated version to 1.3.0. [ebner]
- Merge pull request #10 from paulscherrerinstitute/devl. [Simon Gregor
  Ebner]

  Resolving issues
- Save data metadata now contains request file name from which it was
  created. This is used for matching request and save data files. If the
  request file info is missing in the metadata, then loaded request file
  prefix is used to filter the save data files. [Saso Skube]
- Added ability to copy PV names from the PV canvas. [Saso Skube]
- Updated git ignore file and did minor fixes. [Saso Skube]
- Added ability to edit saved snapshot's metadata (comment and labels)
  [Saso Skube]
- GUI: Added ability to use a prefix for the output data file name.
  [Saso Skube]
- Update readme. [Vintar Rok]


1.2.0 (2016-07-28)
------------------
- Version increased. [Vintar Rok]
- Merge pull request #7 from paulscherrerinstitute/upgrade_changes.
  [rokvintar]

  Upgrade changes
- Minor fixes. [Vintar Rok]
- While in GUI mode, each save creates symlink *_latest.snap to last
  saved file. [Vintar Rok]
- Change request file during snapshot is opened. [Vintar Rok]
- Bug, handling arrays with only one value. [Vintar Rok]
- Commandline programs added. [Vintar Rok]
- Licenicing. [Tom Slejko]


1.1.3 (2016-05-03)
------------------
- Updated readme with new usage. [ebner]
- Added an option to set the base directory for the open dialog for
  request files. [ebner]
- Version 1.1.2. [Vintar Rok]
- OSX menu bar fixed: Again using native menu bar. Actions must be in
  the menus for mac os x + actions named settings, preferences or
  something similar must have overriden menu role. [Rok Vintar]
- Updated readme. [ebner]


1.1.1 (2016-03-29)
------------------
- Version 1.1.1. [Vintar Rok]
- Adding layouts to other layouts with addLayout() instead of addItem()
  [Vintar Rok]
- Fixed settings menu for mac os x. [ebner]


1.1.0 (2016-03-21)
------------------
- Merge pull request #1 from paulscherrerinstitute/rv_settings.
  [rokvintar]

  Macros are now retained in the saved file. Settings window added (macros, save directory, force mode)
- Version 1.1.0 (conda recepie and setup.py updated) [Vintar Rok]
- Minor bug fixes. [Vintar Rok]
- Settings window added. User can set: macros, saved files dir and force
  mode. [Vintar Rok]
- Macros retained in the .snap file. [Vintar Rok]
- Removed second screenshot. [ebner]
- Fixed link. [ebner]
- Added screenshots. [ebner]
- Updated readme and links. [ebner]


1.0.0 (2016-02-23)
------------------
- Increased to version 1.0. [ebner]
- Merge branch 'vintar_r' into 'master' [vintar_r]

  Vintar r



  See merge request !6
- V 0.9.3. [Vintar Rok]
- Compare multiple files added. Representation of data changed (no more
  color coded) [Vintar Rok]
- Removing "zebra look" in lists of files and PVs. Replaced with lines.
  [Vintar Rok]
- Ask user if force current action(save/restore) if not in forced mode.
  [Vintar Rok]
- Comment and labels as advanced options during save. [Vintar Rok]
- Show/hide status log. Hidden by default. [Vintar Rok]


0.9.2 (2016-02-12)
------------------
- New version. [ebner]
- Renamed recipe folder to "standard" [ebner]
- Added: Updating saved values coloumn even if PV not connected and
  selected .snap file chnaged. [Vintar Rok]
- Added: parsing req file now removes data{} around PVs, to support old
  format. [Vintar Rok]
- Fixed bug: when .req called from current dir and no ./ then dir for
  saved files was empty string. Changed to convert any path to absolute
  path. [Vintar Rok]
- When separator in .snap files changed from ; to , arrays ere parrsed
  into long list (they also use , to separate values). Fixed now to do
  split only on first , [Vintar Rok]
- Do not use show() on QFileDialog, becouse it hangs on OSX. Use get
  getOpenFileName() instead. [Rok Vintar]
- Merge branch 'master' of https://git.psi.ch/cosylab/snapshot_tool.
  [Vintar Rok]
- Bug in file filtering fixed. [Vintar Rok]
- Macros flag changed to macro, to have same interface as for caqtdm
  erc. [Vintar Rok]
- Bug in filtering fixed. [Vintar Rok]
- Date widgets removed. [Vintar Rok]
- Merge branch 'bug_fixes' into 'master' [vintar_r]

  Fixing bugs, styling and extending label selector

  Fixing bugs, styling and extending label selector

  See merge request !5
- Updating Readme, and code cleanup. [Vintar Rok]
- Additionaly customizing style, to work well with native look on sf6
  (finlc). Fixing sizes  of elemnts, etc. [Vintar Rok]
- Returning to native stylineg (except splitters). Adding sources to
  package, changing version to 0.9.1. [Vintar Rok]
- Label widgets extended to suggest existing labels. [Vintar Rok]
- Fix style also for scroll bar, and combobox. [Vintar Rok]
- PV filtering for complete incomplete PVs data changed. [Vintar Rok]
- Force save/restore option added as flag at the startup. [Vintar Rok]
- Setting background colors to be unified on different systems. [Vintar
  Rok]
- Bug in path to splitter image fixed. [Vintar Rok]
- Adding sytling and icons. Removing bugy part of label selector.
  [Vintar Rok]
- Styling the label filter/input. [Vintar Rok]
- Becouse callbacks are executed in pyepics thread, callbacks now emit
  signal, and method in Qt thread handles gui specific things. [Vintar
  Rok]
- Fixing coulmn sizes in qtreeviews. [Vintar Rok]
- Chaning main GUI class to main window. [Vintar Rok]
- Filtering files by name added. [Vintar Rok]
- Some styling added. Filtering files by time removed. [Vintar Rok]
- Delete file warning message added. [Vintar Rok]
- Request file as positional but optionala prameter. [Vintar Rok]
- Delete file option added. [Vintar Rok]
- Tabs removed. [Vintar Rok]
- Status info moved to staus bar. [Vintar Rok]
- Filtering by time now also filters files if end time is smaller than
  from time. [Vintar Rok]
- Default file name extention is timestamp of the saving time, not of
  the starting time. [Vintar Rok]
- Keywords renamed to labels. [Vintar Rok]
- Threads removed, core module is now asychronous. Bug with blocking if
  PV not connected is now fixed. [Vintar Rok]
- When including snapshot_ca relative path (.) must be used to have a
  working module. [Vintar Rok]
- Merged with cleanup branch. [Vintar Rok]
- Cleanup snapshot.py. [ebner]
- Fixed code to be python 3 compatible. [ebner]
- Updated recipe to use local source. [ebner]
- Moved recipe folder. [ebner]


0.9.0 (2016-01-20)
------------------
- Readme updated for release 0.9.0. [Vintar Rok]
- Star_snapshot is a python file which uses snapshot module. It can be
  used when interpeter mode is needed (in case of readline bug) [Vintar
  Rok]
- Recipe prepared for version 0.9.0. [Vintar Rok]
- Conflicts with cleanup brunch resolved. [Vintar Rok]
- Some more cleanup. [ebner]
- Cleanup. [ebner]
- Relative path to module ca_snapshot added, all print's removed from
  the code. [Vintar Rok]
- Delimeter between PV name and value in saved files is now , instead of
  ;(; is a valid PV name character) [Vintar Rok]
- More propper way of closing the app if there is no request file.
  [Vintar Rok]
- Conda recipe files moved and updated, tested with python3. [Vintar
  Rok]
- Importing changed to python3 way. [Vintar Rok]
- Gui refratured. [Vintar Rok]
- If request file not as argument, prompts window asking for it. [Vintar
  Rok]
- If request file not as argument, prompts window asking for it. [Vintar
  Rok]
- Bugs fixed: 1. empty keywords filter, hides all files, 2. opening
  connection sif not connected to slow and blocking when initializing.
  [Vintar Rok]
- Bugs fixed: 1. empty keywords filter, hides all files, 2. opening
  connection sif not connected to slow and blocking when initializing.
  [Vintar Rok]
- Conda packaging problem. [Vintar Rok]
- Adding setup.py. [Vintar Rok]
- COSYLAB-453 preparing structure for conda packaging. [Vintar Rok]
- COSYLAB-453 File filtering GUI part added (calendar widgets and so on)
  [Vintar Rok]
- Asyn restoring. [Vintar Rok]
- Indication of save/restore, in process, done. Bug in restoring fixed.
  [Vintar Rok]
- File formats finalized. [Vintar Rok]
- Filtering of PVs in live compare view. [Vintar Rok]
- Handle if pv value was not set in selected file. [Vintar Rok]
- Handle lost of connection. [Vintar Rok]
- Handle lost of connection. [Vintar Rok]
- Color pv if equal or not. [Vintar Rok]
- Bugs in comparing ... handling arrays. [Vintar Rok]
- Bug in the parser, not skipping empty lines. [Vintar Rok]
- Comparing functions modified (more clean, comapring values in native
  type) [Vintar Rok]
- COSYLAB-453 comparing values, not string representation of values.
  [Vintar Rok]
- COSYLAB-453 comparing values, not string representation of values.
  [Vintar Rok]
- COSYLAB-453 Readme added. Adding Shebang. [Vintar Rok]
- Merge branch 'threading_bug' into 'master' [vintar_r]

  Threading bug



  See merge request !1
- Save only NORD values for arrays. [Vintar Rok]
- Format for saving change to json. [Vintar Rok]
- Saving of arrays added. [Vintar Rok]
- COSYLAB-453 live compare added. [Vintar Rok]
- Properly updating restore widget when files are added (after save)
  [Vintar Rok]
- Code cleaned, clearer interface. [Vintar Rok]
- COSYLAB-453 Multi threading did not work. Save blocked the GUI.
  Solved. [Vintar Rok]
- COSYLAB-453 All singals from worker thrad should be catched in
  SnapshotGUI, which then updates all needed components. Arguments
  changed/removed. See help -h. Still breakse if wsome parameters are
  not given. [Vintar Rok]
- COSYLAB-453 Saved file sorted, selected file is used for restore.
  Adding application arguments and help. [Vintar Rok]
- COSYLAB-453 generating list of saved files. [Vintar Rok]
- COSYLAB-453 generating list of saved files. [Vintar Rok]
- COSYLAB-453 Unfinished version of GUI. Core will be medified to use
  different file format. [Vintar Rok]
- COSYLAB-453 Core of the snapshot application. Need to modify comments.
  [Vintar Rok]


