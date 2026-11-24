"""Task domain errors.

Messages carry only ids, enum values and key names, never params values.
"""


class TaskError(Exception):
    """Base class for task rule violations."""


class TaskNotFound(TaskError):
    """No task with this id for this user (also used for another user's task)."""


class IllegalTransition(TaskError):
    """The (from, to) move is not in the table, or not allowed for this task kind."""


class GuardedTransition(TaskError):
    """The move exists but only a dedicated, authorized operation may make it."""


class VersionConflict(TaskError):
    """The task changed since the caller read it."""


class InvalidTaskParams(TaskError):
    """Task params break a creation rule."""
