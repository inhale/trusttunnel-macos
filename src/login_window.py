"""
TrustTunnel VPN Login Window with Rate Limiting.

Implements client-side rate limiting to prevent brute-force attacks on the login form.
- Rate limit: 5 attempts per minute per IP address.
- User-friendly message when the limit is hit.
- Message disappears automatically when the cooldown expires.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
import threading
import time
from rate_limiter import RateLimiter


class LoginWindow:
    def __init__(self, root, on_login_success):
        self.root = root
        self.on_login_success = on_login_success
        self.root.title("TrustTunnel VPN Login")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        # Rate limiter: 5 attempts per minute (5/60 tokens per second)
        self.rate_limiter = RateLimiter(capacity=5, refill_rate=5/60)
        self.cooldown_message = None
        self.cooldown_active = False

        # Username
        ttk.Label(self.root, text="Username:").pack(pady=(20, 0))
        self.username_entry = ttk.Entry(self.root)
        self.username_entry.pack(pady=5, padx=20, fill=tk.X)

        # Password
        ttk.Label(self.root, text="Password:").pack(pady=(10, 0))
        self.password_entry = ttk.Entry(self.root, show="*")
        self.password_entry.pack(pady=5, padx=20, fill=tk.X)

        # Login Button
        self.login_button = ttk.Button(
            self.root, 
            text="Login", 
            command=self.attempt_login
        )
        self.login_button.pack(pady=20)

    def attempt_login(self):
        """Handle login attempts with rate limiting."""
        # Mock IP address for testing
        ip_address = "127.0.0.1"

        # Check rate limit
        if not self.rate_limiter.allow_login(ip_address):
            self.show_cooldown_message(ip_address)
            return

        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            messagebox.showerror("Error", "Username and password are required!")
            return

        try:
            response = requests.post(
                "http://13.140.25.184:3001/auth",
                json={"username": username, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                self.on_login_success(username)
            else:
                messagebox.showerror("Error", "Invalid username or password!")
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")

    def show_cooldown_message(self, ip_address):
        """Show a cooldown message and clear it when the cooldown expires."""
        if self.cooldown_active:
            return

        self.cooldown_active = True
        remaining_time = self.rate_limiter.get_remaining_time(ip_address)

        if self.cooldown_message:
            self.cooldown_message.destroy()

        self.cooldown_message = tk.Label(
            self.root, 
            text=f"Too many attempts. Try again in {int(remaining_time)} seconds.",
            fg="red"
        )
        self.cooldown_message.pack(pady=(10, 0))

        # Schedule the message to disappear
        self.root.after(int(remaining_time * 1000), self.clear_cooldown_message)

    def clear_cooldown_message(self):
        """Clear the cooldown message."""
        if self.cooldown_message:
            self.cooldown_message.destroy()
            self.cooldown_message = None
        self.cooldown_active = False


if __name__ == "__main__":
    root = tk.Tk()
    LoginWindow(root, lambda username: print(f"Logged in as {username}"))
    root.mainloop()