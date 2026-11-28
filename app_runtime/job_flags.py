"""Cancellation of cloud jobs. Standard library only: the small dispatcher and CPU containers import it too."""
from datetime import datetime, UTC
import logging


def is_job_cancelled(jobs, job_id):
    """A queued job must not start when it was cancelled: by its record, or by the flag a parent job set."""
    if jobs.get(f"cancelled:{job_id}"):
        return True
    record = jobs.get(job_id)
    return record is None or record.get("status") == "cancelled"


def cancel_children(jobs, job_id, cancel):
    """Stop the jobs a job queued itself (the Vari unCLIP pre-stage). The parent is killed before it can do this."""
    for child_id in jobs.get(f"children:{job_id}") or []:
        child = jobs.get(child_id)
        if child is None or child.get("status") in {"completed", "failed", "cancelled"}:
            continue
        jobs[f"cancelled:{child_id}"] = True  # first, so a queued child is dropped even if stopping the call fails
        jobs[child_id] = {**child, "status": "cancelled", "message": "Cancelled", "updated_at": datetime.now(UTC).isoformat()}
        call_id = jobs.get(f"call:{child_id}")
        if call_id and cancel is not None:
            try:
                cancel(call_id)
            except Exception:
                logging.getLogger("studio").exception("Could not cancel child job %s", child_id)
