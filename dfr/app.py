"""DFR application lifecycle and ASGI factory.

Example:
    from dfr.app import DFRApp

    app = DFRApp(django_settings_module="project.settings")
    asgi_app = app.asgi()
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from django.core.asgi import get_asgi_application

from dfr.types import DFRBootPhase

__all__ = ["DFRApp", "DFRBootstrapError", "DFRSettings"]


class DFRBootstrapError(RuntimeError):
    """Raised when DFR app lifecycle methods are called out of order."""


@dataclass(slots=True, frozen=True)
class DFRSettings:
    """Runtime settings for DFR application bootstrap.

    Attributes:
        django_settings_module: Django settings module path.
        title: Human-readable API title.
        version: API version string.
    """

    django_settings_module: str
    title: str = "DFR"
    version: str = "0.1.0"


class DFRApp:
    """Unified DFR application container.

    This class performs two-phase boot:
    1. Initialize Django app registry.
    2. Finalize DFR routing resources.

    Example:
        app = DFRApp(django_settings_module="project.settings")
        app.bootstrap()
        asgi_app = app.asgi()
    """

    def __init__(self, *, django_settings_module: str, title: str = "DFR", version: str = "0.1.0") -> None:
        self.settings = DFRSettings(
            django_settings_module=django_settings_module,
            title=title,
            version=version,
        )
        self._boot_phase: DFRBootPhase = DFRBootPhase.CREATED
        self._asgi_app: Any | None = None

    @property
    def boot_phase(self) -> DFRBootPhase:
        """Current application bootstrap phase."""

        return self._boot_phase

    def bootstrap(self) -> None:
        """Initialize Django and finalize DFR resources.

        Raises:
            DFRBootstrapError: If bootstrap is attempted after app materialization.
        """

        if self._asgi_app is not None:
            raise DFRBootstrapError(
                "Cannot re-bootstrap after ASGI app creation. Create a new DFRApp instance to reconfigure."
            )

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", self.settings.django_settings_module)

        import django

        if self._boot_phase is DFRBootPhase.CREATED:
            django.setup(set_prefix=False)
            self._boot_phase = DFRBootPhase.DJANGO_INITIALIZED

        if self._boot_phase is DFRBootPhase.DJANGO_INITIALIZED:
            # Routing/materialization hooks will be invoked here in later batches.
            self._boot_phase = DFRBootPhase.ROUTES_FINALIZED

        self._boot_phase = DFRBootPhase.READY

    def asgi(self) -> Any:
        """Return the ASGI application for deployment.

        Returns:
            ASGI callable compatible with Uvicorn/Granian.

        Raises:
            DFRBootstrapError: If Django bootstrap fails or settings are missing.
        """

        if self._asgi_app is not None:
            return self._asgi_app

        if self._boot_phase is not DFRBootPhase.READY:
            self.bootstrap()

        try:
            self._asgi_app = get_asgi_application()
        except Exception as exc:  # pragma: no cover - defensive boundary error path
            raise DFRBootstrapError(
                "Failed to create ASGI application. Verify DJANGO_SETTINGS_MODULE and installed apps configuration."
            ) from exc

        return self._asgi_app
