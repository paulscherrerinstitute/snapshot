import abc

from snapshot.core import SnapshotError


class SnapshotFile(abc.ABC):
    @abc.abstractmethod
    def read(self):
        pass


class ReqParseError(SnapshotError):
    """
    Parent exception class for exceptions that can happen while parsing a request file.
    """

    pass
