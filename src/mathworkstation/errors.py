class WorkstationError(Exception):
    """Base error for the workstation."""


class CaseNotFoundError(WorkstationError):
    pass


class InvalidCaseError(WorkstationError):
    pass


class PathViolationError(WorkstationError):
    pass


class WorkflowError(WorkstationError):
    pass


class DependencyBlockedError(WorkflowError):
    pass


class InvalidTransitionError(WorkflowError):
    pass

