#!/usr/bin/env python

import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'Readme.md')).read()

setup(name='snapshot',
      version='v0.0.1',
      description="Tool for saving and restoring snapshots of EPICS channels",
      long_description=README,
      author='Rok Vintar',
      url='https://github.psi.ch/cosylab/snapshot_tool',
      keywords='snapshot, epics, pv, PSI',
      packages=['snapshot'],
      package_dir={'snapshot': 'src'},
      platforms=["any"],
      )
