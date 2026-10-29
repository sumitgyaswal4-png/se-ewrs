"""Failed-login throttling.

Argon2 makes each guess slow, but nothing stopped a client from making
them one after another for as long as it liked, writing an audit row each
time. This counts *failed* sign-ins in a sliding window, keyed two ways:

* by the email submitted, so one account cannot be guessed at from many
  addresses. The key is the text sent, whether or not such an account
  exists, so a refusal says nothing about which emails are real;
* by client address, so one machine cannot spray guesses across many
  accounts while staying under the per-account limit.

A blocked attempt is refused before the database or Argon2 is touched,
so it costs the server almost nothing and writes no audit row.

Each attempt is counted *before* its password is checked, in the same
locked step as the limit test (``reserve``). Checking first and counting
after the ~250 ms of Argon2 let a burst of concurrent requests all pass
the check before any of them was counted. A correct password then hands
its slot back (``release``), so successes never count against anyone.

The counters live in this process's memory. That is enough for the single
uvicorn worker this project runs; several workers or hosts would each
keep their own count, and would need a shared store such as Redis.
Behind a reverse proxy, start uvicorn with ``--proxy-headers`` and
``--forwarded-allow-ips`` so the client address is the caller's and not
the proxy's: otherwise every user shares one per-address count.
"""

import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional

#: Past this many tracked keys, expired ones are swept before adding more.
_SWEEP_THRESHOLD = 10_000


class FailedLoginLimiter:
    def __init__(
        self,
        max_per_account: int,
        max_per_address: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_per_account = max_per_account
        self.max_per_address = max_per_address
        self.window_seconds = window_seconds
        self.clock = clock
        self._failures: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _keys(email: str, address: Optional[str]):
        yield f"account:{email.strip().lower()}"
        if address:
            yield f"address:{address}"

    def _limit_for(self, key: str) -> int:
        return self.max_per_account if key.startswith("account:") else self.max_per_address

    def _live(self, key: str, now: float) -> Deque[float]:
        stamps = self._failures.get(key)
        if stamps is None:
            return deque()
        while stamps and stamps[0] <= now - self.window_seconds:
            stamps.popleft()
        if not stamps:
            del self._failures[key]
        return stamps

    def _wait(self, email: str, address: Optional[str], now: float) -> Optional[int]:
        """Seconds until another attempt is allowed, or None. Hold the lock."""
        wait = 0.0
        for key in self._keys(email, address):
            stamps = self._live(key, now)
            if len(stamps) >= self._limit_for(key):
                # Allowed again once the oldest attempt that keeps the count
                # at the limit leaves the window.
                oldest = stamps[len(stamps) - self._limit_for(key)]
                wait = max(wait, oldest + self.window_seconds - now)
        return max(1, math.ceil(wait)) if wait > 0 else None

    def _add(self, email: str, address: Optional[str], now: float) -> None:
        if len(self._failures) >= _SWEEP_THRESHOLD:
            for key in list(self._failures):
                self._live(key, now)
        for key in self._keys(email, address):
            self._failures.setdefault(key, deque()).append(now)

    def retry_after(self, email: str, address: Optional[str]) -> Optional[int]:
        """Seconds until another attempt is allowed, or None if it is now."""
        with self._lock:
            return self._wait(email, address, self.clock())

    def reserve(self, email: str, address: Optional[str]) -> Optional[float]:
        """Count an attempt before its password is checked, if one is allowed.

        Returns the attempt's timestamp, to pass to ``release`` if the
        password turns out to be right; or None when the caller must
        refuse the attempt (``retry_after`` then says for how long).
        """
        now = self.clock()
        with self._lock:
            if self._wait(email, address, now) is not None:
                return None
            self._add(email, address, now)
            return now

    def release(self, email: str, address: Optional[str], stamp: float) -> None:
        """A correct password: clear the account's count and return the slot
        this attempt took from the address's. Other failures from that
        address still count."""
        keys = list(self._keys(email, address))
        with self._lock:
            self._failures.pop(keys[0], None)
            for key in keys[1:]:
                stamps = self._failures.get(key)
                if stamps and stamp in stamps:
                    stamps.remove(stamp)
                    if not stamps:
                        del self._failures[key]

    def record_failure(self, email: str, address: Optional[str]) -> None:
        """Count a failure without the limit test (``reserve`` does both)."""
        with self._lock:
            self._add(email, address, self.clock())

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
