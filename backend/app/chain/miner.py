"""Proof-of-work search. Hashing runs off the request thread and yields the CPU."""

from __future__ import annotations

import threading
import time
from multiprocessing import Process, Queue, Value

from app.chain.crypto import meets_difficulty
from app.chain.ledger import Block


def find_nonce(block: Block, stop: threading.Event | None = None, pause: threading.Event | None = None, counter=None, cpu_percent: int = 100, limit: int | None = None):
    """Search for a nonce. Returns (nonce, hash) or None when stopped or limited."""
    cpu = max(1, min(int(cpu_percent), 100))
    nonce = 0
    while True:
        if stop is not None and stop.is_set():
            return None
        while pause is not None and pause.is_set():
            if stop is not None and stop.is_set():
                return None
            time.sleep(0.05)
        started = time.perf_counter()
        for _ in range(2000):
            block.nonce = nonce
            digest = block.block_hash()
            nonce += 1
            if counter is not None:
                counter.value += 1
            if meets_difficulty(digest, block.difficulty):
                return nonce - 1, digest
            if limit is not None and nonce >= limit:
                return None
        elapsed = time.perf_counter() - started
        if cpu < 100 and elapsed > 0:
            time.sleep(elapsed * (100 - cpu) / cpu)


def _process_target(block: Block, cpu_percent: int, counter, queue: Queue) -> None:
    found = find_nonce(block, counter=counter, cpu_percent=cpu_percent)
    queue.put(found)


def mine_in_process(block: Block, cpu_percent: int, stop: threading.Event, pause: threading.Event) -> tuple[tuple[int, str] | None, int]:
    """Run the search in a child process. Stop and pause terminate that process."""
    counter = Value("Q", 0)
    queue: Queue = Queue()
    process = Process(target=_process_target, args=(block, cpu_percent, counter, queue), daemon=True)
    process.start()
    while process.is_alive():
        if stop.is_set() or pause.is_set():
            process.terminate()
            process.join(2)
            return None, int(counter.value)
        time.sleep(0.1)
    process.join()
    found = queue.get() if not queue.empty() else None
    return found, int(counter.value)


class MinerControl:
    """Background mining loop. The work callable performs one attempt and returns a result or None."""

    def __init__(self, work, cpu_percent: int = 20) -> None:
        self._work = work
        self.cpu_percent = cpu_percent
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.status = "stopped"
        self.hashes = 0
        self.success = 0
        self.failed = 0
        self.started = 0.0
        self.paused_seconds = 0.0
        self._pause_mark = 0.0
        self.hashrate = 0.0
        self.samples: list[dict] = []
        self._sample_hashes = 0
        self._sample_at = 0.0
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.status in {"running", "paused"}:
                return
            self.stop_event.clear()
            self.pause_event.clear()
            self.started = time.monotonic()
            self.paused_seconds = 0.0
            self.hashes = 0
            self.success = 0
            self.failed = 0
            self.hashrate = 0.0
            self.samples = []
            self._sample_hashes = 0
            self._sample_at = self.started
            self.status = "running"
            self.thread = threading.Thread(target=self._loop, name="project-coin-miner", daemon=False)
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.pause_event.clear()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(3)
        with self.lock:
            self.status = "stopped"

    def pause(self) -> None:
        if self.status != "running":
            return
        self._pause_mark = time.monotonic()
        self.pause_event.set()
        with self.lock:
            self.status = "paused"

    def resume(self) -> None:
        if self.status != "paused":
            return
        if self._pause_mark:
            self.paused_seconds += time.monotonic() - self._pause_mark
            self._pause_mark = 0.0
        self.pause_event.clear()
        with self.lock:
            self.status = "running"

    def duration(self) -> float:
        if not self.started:
            return 0.0
        paused = self.paused_seconds
        if self.status == "paused" and self._pause_mark:
            paused += time.monotonic() - self._pause_mark
        return max(0.0, time.monotonic() - self.started - paused)

    def note_hashes(self, count: int) -> None:
        now = time.monotonic()
        with self.lock:
            self.hashes += count
            elapsed = now - self._sample_at
            if elapsed >= 0.5:
                self.hashrate = (self.hashes - self._sample_hashes) / elapsed
                self._sample_hashes = self.hashes
                self._sample_at = now
                self.samples.append({"t": int(time.time()), "hashrate": round(self.hashrate, 2)})
                self.samples = self.samples[-240:]

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            if self.pause_event.is_set():
                time.sleep(0.05)
                continue
            try:
                found = self._work(self.stop_event, self.pause_event, self)
            except Exception:
                found = None
            if self.stop_event.is_set() or self.pause_event.is_set():
                continue
            with self.lock:
                if found:
                    self.success += 1
                else:
                    self.failed += 1
        with self.lock:
            self.status = "stopped"
