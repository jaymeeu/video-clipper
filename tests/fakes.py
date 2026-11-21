"""In-memory stand-ins for the service's infrastructure (Redis store, queue)."""

from clippers.jobs import JobRecord


class InMemoryJobStore:
    """Implements jobs.JobStore with a dict, and remembers every save (to check progress)."""

    def __init__(self) -> None:
        self.records: dict[str, JobRecord] = {}
        self.history: list[JobRecord] = []

    async def get(self, job_id: str) -> JobRecord | None:
        return self.records.get(job_id)

    async def save(self, record: JobRecord) -> None:
        self.records[record.id] = record
        self.history.append(record)


class RecordingQueue:
    """An `Enqueue` callable that just records the job ids it was given."""

    def __init__(self) -> None:
        self.job_ids: list[str] = []

    async def __call__(self, job_id: str) -> None:
        self.job_ids.append(job_id)
