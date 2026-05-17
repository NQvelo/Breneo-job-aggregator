"""Domain exceptions for job application flows."""


class JobApplicationError(Exception):
    """Base error with HTTP status and client message."""

    status_code: int = 400
    error_code: str = "application_error"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class JobNotFoundError(JobApplicationError):
    status_code = 404
    error_code = "job_not_found"


class ApplicationNotFoundError(JobApplicationError):
    status_code = 404
    error_code = "application_not_found"


class JobNotAcceptingApplicationsError(JobApplicationError):
    status_code = 400
    error_code = "job_not_accepting_applications"


class EmployerJobOnlyError(JobApplicationError):
    status_code = 400
    error_code = "employer_job_only"


class AlreadyAppliedError(JobApplicationError):
    status_code = 409
    error_code = "already_applied"


class ForbiddenJobAccessError(JobApplicationError):
    status_code = 403
    error_code = "forbidden"
