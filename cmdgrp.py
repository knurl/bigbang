# bigbang-specific

# other
import threading
from typing import Callable

class CommandGroup:
    def __init__(self):
        self.cv = threading.Condition() # producer-consumer lock
        self.work_to_do: int = 0
        self.work_done: int = 0
        self.cmds_queued: list[Callable[[], None]] = []
        self.cmds_running: list[Callable[[], None]] = []

    def check_not_running(self) -> None:
        assert (n := len(self.cmds_running)) < 1, \
                f'{n} threads already running'

    def add_command(self, f: Callable[[], None],
                    new_work: int) -> None:
        def make_cb_work_done(f: Callable[[], None],
                              new_work: int) -> Callable[[], None]:
            def cb_work_done():
                f()
                with self.cv:
                    self.work_done += new_work
                    self.cv.notify_all()
            return cb_work_done

        with self.cv:
            self.check_not_running()
            self.cmds_queued.append(make_cb_work_done(f, new_work))
            self.work_to_do += new_work

    def check_running(self) -> None:
        assert len(self.cmds_running) > 0, 'No threads running'

    def move_to_running_mode(self) -> None:
        with self.cv:
            self.check_not_running()
            self.cmds_running = self.cmds_queued
            self.cmds_queued = []
            self.check_running()

    def run_commands(self) -> None:
        self.move_to_running_mode()
        for cmd in self.cmds_running:
            t = threading.Thread(target = cmd)
            t.start()

    def run_commands_seq(self) -> None:
        self.move_to_running_mode()
        for cmd in self.cmds_running:
            cmd()

    # Must be called with lock held--and this is only called by wait_for on the
    # condition variable, which always guarantees the lock is held
    def all_commands_done(self) -> bool:
        assert self.work_done <= self.work_to_do
        return self.work_done == self.work_to_do

    def wait_until_done(self) -> None:
        with self.cv:
            self.check_running()
            self.cv.wait_for(self.all_commands_done)

    def ratio_done(self) -> float:
        with self.cv:
            self.check_running()
            assert self.work_done <= self.work_to_do, \
                    f"{self.work_done} should be <= {self.work_to_do}"
            # It's possible that no commands were processed, in which case
            # avoid doing a division-by-zero by saying we're finished.
            return float(self.work_done) / self.work_to_do \
                    if self.work_to_do > 0 else 1.0
