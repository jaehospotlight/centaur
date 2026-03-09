"""Module-level singleton for the active secret backend."""

from __future__ import annotations

import os

from secret_backends.base import SecretBackend

_backend: SecretBackend | None = None


def configure(backend: SecretBackend) -> None:
    """Set the active secret backend."""
    global _backend
    _backend = backend


def auto_configure() -> SecretBackend:
    """Build a default backend chain based on environment variables.

    - If ``SECRET_MANAGER_URL`` is set → ``CompositeBackend([EnvBackend(), HttpBackend(url)])``
    - Otherwise → ``EnvBackend()``
    """
    from secret_backends.composite import CompositeBackend
    from secret_backends.env import EnvBackend
    from secret_backends.http import HttpBackend

    url = os.environ.get("SECRET_MANAGER_URL", "")
    token = os.environ.get("SECRET_MANAGER_TOKEN", "")
    backend = CompositeBackend([EnvBackend(), HttpBackend(url, token=token)]) if url else EnvBackend()
    configure(backend)
    return backend


def get_backend() -> SecretBackend:
    """Return the active backend, auto-configuring on first call if needed."""
    global _backend
    if _backend is None:
        auto_configure()
    assert _backend is not None
    return _backend
