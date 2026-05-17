"""Which jobs support in-app apply vs external apply_url only."""

from .models import Job


def job_supports_in_app_apply(job: Job) -> bool:
    """
    True for jobs posted by companies on the Breneo employer platform.
    Fetched/ATS jobs (greenhouse, lever, etc.) keep the original external apply link.
    """
    return (job.platform or "").strip().lower() == "employer"
