"""
Rate limiter for TrustTunnel macOS GUI.

Implements a token bucket algorithm to enforce rate limits on login attempts.
- Tokens are refilled at a fixed rate (e.g., 5 tokens per minute).
- Each login attempt consumes one token.
- If no tokens are available, the attempt is rejected.
- Thread-safe using threading.Lock.
"""
import time
import threading


class TokenBucket:
    """Token bucket algorithm for rate limiting."""

    def __init__(self, capacity, refill_rate):
        """
        Initialize the token bucket.

        Args:
            capacity (int): Maximum number of tokens the bucket can hold.
            refill_rate (float): Tokens added per second.
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def consume(self, tokens=1):
        """
        Consume tokens from the bucket.

        Args:
            tokens (int): Number of tokens to consume.

        Returns:
            bool: True if tokens were available, false otherwise.
        """
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def _refill(self):
        """Refill tokens based on the elapsed time since the last refill."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        if tokens_to_add > 0:
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now


class RateLimiter:
    """Rate limiter for login attempts per IP address."""

    def __init__(self, capacity, refill_rate):
        """
        Initialize the rate limiter.

        Args:
            capacity (int): Maximum number of login attempts allowed in the window.
            refill_rate (float): Tokens added per second (e.g., 5/60 for 5 per minute).
        """
        self.buckets = {}
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.lock = threading.Lock()

    def allow_login(self, ip_address):
        """
        Check if a login attempt is allowed for the given IP address.

        Args:
            ip_address (str): IP address of the login attempt.

        Returns:
            bool: True if the login attempt is allowed, false otherwise.
        """
        with self.lock:
            if ip_address not in self.buckets:
                self.buckets[ip_address] = TokenBucket(self.capacity, self.refill_rate)
            return self.buckets[ip_address].consume()

    def get_remaining_time(self, ip_address):
        """
        Get the remaining cooldown time for the given IP address.

        Args:
            ip_address (str): IP address of the login attempt.

        Returns:
            float: Remaining time in seconds until the next token is available. -1 if no cooldown.
        """
        with self.lock:
            if ip_address not in self.buckets:
                return -1
            bucket = self.buckets[ip_address]
            bucket._refill()
            if bucket.tokens >= 1:
                return -1
            return (1 - bucket.tokens) / bucket.refill_rate