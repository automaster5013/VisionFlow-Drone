from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from app.domain import FramePacket


class VideoSource(ABC):
    @property
    @abstractmethod
    def fps(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def open(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read(self) -> FramePacket | None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> VideoSource:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
