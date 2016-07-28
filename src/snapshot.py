import sys
import argparse
import re
from .snapshot_ca import parse_macros

# close with ctrl+C
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

def _set_default_subparser(default, subparsers=None):
        subparsers = subparsers or []

        # check if any subparser or global help was specified
        if any(arg in sys.argv[1:] for arg in subparsers + ['-h', '--help']):
            return
        else:
            sys.argv.insert(1, default)

def save(args):
    from .snapshot_cmd import save
    save(args.FILE, args.out, args.macro, args.force, args.timeout)

    #req_file_path, save_file_path='.', macros=None, force=False, timeout=10

def restore(args):
    from .snapshot_cmd import restore
    restore(args.FILE, args.force, args.timeout)

def gui(args):
    from .snapshot_gui import start_gui
    start_gui(args.FILE, args.macro, args.dir, args.force, init_path=args.base)


def main():
    ''' Main creates Qt application and handles arguments '''

    args_pars = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    args_pars.set_defaults(macro=None)
    subparsers = args_pars.add_subparsers(help='modes of work (if not specified \'"gui\" will be used)')
    args_pars.format_usage()

    # Gui
    gui_pars = subparsers.add_parser('gui', help='open graphical interface (default)')
    gui_pars.set_defaults(func=gui)
    gui_pars.add_argument('FILE', nargs='?', help='request file.')
    gui_pars.add_argument('-macro', '-m', help="macros for request file e.g.: \"SYS=TEST,DEV=D1\"")
    gui_pars.add_argument('-dir', '-d',
                           help="directory for saved files")
    gui_pars.add_argument('-base', '-b',
                           help="base directory for opening request files")
    gui_pars.add_argument('--force', '-f',
                           help="force save/restore in case of disconnected PVs", action='store_true')

    # Save
    save_pars = subparsers.add_parser('save', help='save current state of PVs to file, without using GUI')
    save_pars.set_defaults(func=save)
    save_pars.add_argument('FILE', help='request file.')
    save_pars.add_argument('-macro', '-m',
                           help="macros for request file e.g.: \"SYS=TEST,DEV=D1\"")
    save_pars.add_argument('-out', '-o', default='.', help="Output path/file.")
    save_pars.add_argument('--force', '-f',
                           help="force save in case of disconnected PVs after timeout", action='store_true')
    save_pars.add_argument('-timeout', default=10, type=int, help='max time waiting for PVs to be connected')

    # Restore
    rest_pars = subparsers.add_parser('restore', help='restore saved state of PVs from file, without using GUI')
    rest_pars.set_defaults(func=restore)
    rest_pars.add_argument('FILE', help='saved file.')
    rest_pars.add_argument('--force', '-f',
                           help="force restore in case of disconnected PVs after timeout", action='store_true')
    rest_pars.add_argument('-timeout', default=10, type=int,
                           help='max time waiting for PVs to be connected and restored')

    _set_default_subparser('gui', ['gui', 'save', 'restore']) # modifies sys.argv


    # Prepare epilog text for main help
    args_pars.epilog = '''------- GUI mode --------
usage: {}       {}
-------- Command line save mode --------
{}
-------- Command line restore mode --------
{}'''.format(
        re.sub('(?:\sgui|usage:\s)', '', gui_pars.format_usage()),
        re.sub('usage:\s', '', gui_pars.format_help()),
        save_pars.format_help(),
        rest_pars.format_help()
    )

    args_pars.description = '''Tool for saving and restoring snapshots of EPICS process variables (PVs)
Can be used as graphical interface tool, or a command line tool.'''

    args = args_pars.parse_args()

    # Parse macros string if exists
    args.macro = parse_macros(args.macro)


    args.func(args)

# Start the application here
if __name__ == '__main__':
    main()
