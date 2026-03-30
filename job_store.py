import threading


class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set(self, job_id: str, payload: dict):
        with self._lock:
            self._jobs[job_id] = payload

    def get(self, job_id: str):
        with self._lock:
            return self._jobs.get(job_id)
