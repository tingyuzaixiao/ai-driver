from enum import Enum


class TaskStatus(Enum):
    PENDING = 1
    RUNNING = 2
    STOPPED = 3
    COMPLETED = 4
    FAILED = 5