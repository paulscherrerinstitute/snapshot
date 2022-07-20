#!/usr/bin/env python

import io
import os

from setuptools import setup


def read(*paths, **kwargs):
    """Read the contents of a text file safely.
    >>> read("som_cam", "VERSION")
    '0.1.0'
    >>> read("README.md")
    ...
    """

    content = ""
    with io.open(
        os.path.join(os.path.dirname(__file__), *paths),
        encoding=kwargs.get("encoding", "utf8"),
    ) as open_file:
        content = open_file.read().strip()
    return content


setup(
    name="snapshot",
    version=read("snapshot", "VERSION"),
    description="Tool for saving and restoring snapshots of EPICS channels",
    long_description=read("Readme.md"),
    author="Paul Scherrer Institute",
    url="https://github.com/paulscherrerinstitute/snapshot",
    keywords="snapshot, epics, pv, PSI",
    packages=[
        "snapshot",
        "snapshot.ca_core",
        "snapshot.gui",
        "snapshot.cmd",
        "snapshot.request_files",
    ],
    # package_dir={'snapshot': 'src', 'snapshot.ca_core': 'src/ca_core', 'snapshot.gui': 'src/gui',
    #              'snapshot.cmd': 'src/cmd'},
    package_data={"snapshot": ["gui/images/*.png", "gui/qss/*.qss"]},
    platforms=["any"],
    zip_safe=False
    # requires=['pyepics', 'pyqt', 'numpy'],
)
