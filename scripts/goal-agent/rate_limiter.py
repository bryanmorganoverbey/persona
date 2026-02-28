"""
Rate Limiter — enforces per-minute limits on API calls and token usage
to avoid hitting Anthropic rate limits.
"""

import os
import time
from collections import deque
from dataclasses import dataclass, field

MAX_CALLS_PER_MINUTE = int(os.environ.get("GOAL_AGENT_MAX_CALLS_PER_MIN", "5"))
MAX_TOKENS_PER_MINUTE = int(os.environ.get("GOAL_AGENT_MAX_TOKENS_PER_MIN", "10000"))
WINDOW = 60.0  # seconds


@dataclass
class RateLimiter:
    max_calls: int = MAX_CALLS_PER_MINUTE
    max_tokens: int = MAX_TOKENS_PER_MINUTE
    window: float = WINDOW
    _call_times: deque = field(default_factory=deque)
    _token_log: deque = field(default_factory=deque)

    def _prune(self) -> None:
        """Remove entries older than the sliding window."""
        cutoff = time.monotonic() - self.window
        while self._call_times and self._call_times[0] < cutoff:
            self._call_times.popleft()
        while self._token_log and self._token_log[0][0] < cutoff:
            self._token_log.popleft()

    def _tokens_in_window(self) -> int:
        self._prune()
        return sum(t[1] for t in self._token_log)

    def _calls_in_window(self) -> int:
        self._prune()
        return len(self._call_times)

    def wait_if_needed(self) -> None:
        """Block until both call and token budgets have capacity."""
        while True:
            self._prune()
            calls = self._calls_in_window()
            tokens = self._tokens_in_window()

            if calls < self.max_calls and tokens < self.max_tokens:
                return

            # Find how long until the oldest entry expires
            oldest = None
            if calls >= self.max_calls and self._call_times:
                oldest = self._call_times[0]
            if tokens >= self.max_tokens and self._token_log:
                token_oldest = self._token_log[0][0]
                if oldest is None or token_oldest < oldest:
                    oldest = token_oldest

            if oldest is not None:
                wait = (oldest + self.window) - time.monotonic()
                if wait > 0:
                    reason = []
                    if calls >= self.max_calls:
                        reason.append(f"calls={calls}/{self.max_calls}")
                    if tokens >= self.max_tokens:
                        reason.append(f"tokens={tokens}/{self.max_tokens}")
                    print(f"  Rate limit: waiting {wait:.1f}s ({', '.join(reason)})")
                    time.sleep(wait + 0.1)
            else:
                time.sleep(1)

    def record_call(self, tokens_used: int = 0) -> None:
        """Record an API call and its token usage."""
        now = time.monotonic()
        self._call_times.append(now)
        if tokens_used > 0:
            self._token_log.append((now, tokens_used))

    def status(self) -> str:
        self._prune()
        return (
            f"calls={self._calls_in_window()}/{self.max_calls}, "
            f"tokens={self._tokens_in_window()}/{self.max_tokens} (per {self.window:.0f}s)"
        )


# Singleton instance shared across modules
limiter = RateLimiter()
