"""
Unit tests for the rate_limiter module.

Tests the TokenBucket and RateLimiter classes for correctness and thread safety.
"""
import time
import threading
import pytest
from rate_limiter import TokenBucket, RateLimiter


def test_token_bucket_initialization():
    """Test TokenBucket initialization."""
    bucket = TokenBucket(capacity=5, refill_rate=1)
    assert bucket.capacity == 5
    assert bucket.refill_rate == 1
    assert bucket.tokens == 5


def test_token_bucket_consume():
    """Test token consumption."""
    bucket = TokenBucket(capacity=5, refill_rate=1)
    assert bucket.consume() is True
    assert bucket.tokens == 4


def test_token_bucket_exhaust():
    """Test token exhaustion."""
    bucket = TokenBucket(capacity=2, refill_rate=1)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False
    assert abs(bucket.tokens) < 1e-5


def test_token_bucket_refill():
    """Test token refill over time."""
    bucket = TokenBucket(capacity=2, refill_rate=1)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False
    time.sleep(1.1)  # Wait for refill
    assert bucket.consume() is True


def test_token_bucket_thread_safety():
    """Test thread safety of TokenBucket."""
    bucket = TokenBucket(capacity=100, refill_rate=1)
    
    def consume_tokens():
        for _ in range(10):
            bucket.consume()
    
    threads = []
    for _ in range(10):
        thread = threading.Thread(target=consume_tokens)
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    assert bucket.tokens >= 0


def test_rate_limiter_initialization():
    """Test RateLimiter initialization."""
    limiter = RateLimiter(capacity=5, refill_rate=5/60)
    assert limiter.capacity == 5
    assert limiter.refill_rate == 5/60


def test_rate_limiter_allow_login():
    """Test RateLimiter login allowance."""
    limiter = RateLimiter(capacity=2, refill_rate=1)
    ip_address = "127.0.0.1"
    assert limiter.allow_login(ip_address) is True
    assert limiter.allow_login(ip_address) is True
    assert limiter.allow_login(ip_address) is False


def test_rate_limiter_multiple_ips():
    """Test RateLimiter with multiple IP addresses."""
    limiter = RateLimiter(capacity=2, refill_rate=1)
    ip1 = "127.0.0.1"
    ip2 = "192.168.1.1"
    assert limiter.allow_login(ip1) is True
    assert limiter.allow_login(ip2) is True
    assert limiter.allow_login(ip1) is True
    assert limiter.allow_login(ip2) is True
    assert limiter.allow_login(ip1) is False
    assert limiter.allow_login(ip2) is False


def test_rate_limiter_cooldown_time():
    """Test RateLimiter cooldown time calculation."""
    limiter = RateLimiter(capacity=2, refill_rate=1)
    ip_address = "127.0.0.1"
    assert limiter.allow_login(ip_address) is True
    assert limiter.allow_login(ip_address) is True
    assert limiter.allow_login(ip_address) is False
    remaining_time = limiter.get_remaining_time(ip_address)
    assert remaining_time > 0
    assert remaining_time <= 1


def test_rate_limiter_cooldown_expiration():
    """Test RateLimiter cooldown expiration."""
    limiter = RateLimiter(capacity=2, refill_rate=1)
    ip_address = "127.0.0.1"
    assert limiter.allow_login(ip_address) is True
    assert limiter.allow_login(ip_address) is True
    assert limiter.allow_login(ip_address) is False
    time.sleep(1.1)  # Wait for cooldown
    assert limiter.allow_login(ip_address) is True


if __name__ == "__main__":
    pytest.main(["-v"])