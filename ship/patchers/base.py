"""Abstract base class for binary patchers and emulation runners."""

from abc import ABC, abstractmethod
from pathlib import Path


class BinaryPatcher(ABC):
    """Protocol for target environment binary patchers and runners."""

    name: str

    @abstractmethod
    def should_patch(self, binary_path: Path, target_key: str) -> bool:
        """Return True if this patcher applies to the given binary."""

    @abstractmethod
    def patch(self, binary_path: Path, target_key: str) -> Path:
        """
        Patch or wrap the binary.
        Returns the path to the executable that should be symlinked.
        """
