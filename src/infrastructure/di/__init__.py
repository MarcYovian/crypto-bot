"""Dependency Injection package."""

from src.infrastructure.di.container import ApplicationContainer, container, get_container

__all__ = ["ApplicationContainer", "container", "get_container"]
