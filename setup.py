#!/usr/bin/env python

import os
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'Readme.md')).read()

setup(name='snapshot',
      version='2.0.10',
      description="Tool for saving and restoring snapshots of EPICS channels",
      long_description=README,
      author='Paul Scherrer Institute',
      url='https://github.com/paulscherrerinstitute/snapshot',
      keywords='snapshot, epics, pv, PSI',
      packages=['snapshot', 'snapshot.ca_core', 'snapshot.gui', 'snapshot.cmd'],
      # package_dir={'snapshot': 'src', 'snapshot.ca_core': 'src/ca_core', 'snapshot.gui': 'src/gui',
      #              'snapshot.cmd': 'src/cmd'},
      package_data={'snapshot': ['gui/images/*.png', 'gui/qss/*.qss']},
      platforms=["any"],
      # requires=['pyepics', 'pyqt', 'numpy'],
      )
