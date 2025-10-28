from typing import Any


class TrainCommand:
    STOP_COMMAND = "stop"

    def __init__(self, command: str, data: Any = None):
        self._command = command
        self._data = data

    @property
    def command(self) -> str:
        return self._command

    @command.setter
    def command(self, command: str):
        if not command or command.strip() == "":
            raise ValueError(f"{command} is invalid")
        self._command = command

    @property
    def data(self) -> str:
        return self._data

    @data.setter
    def data(self, data: Any):
        self._data = data