"""Public error boundaries for the profile engine."""

from __future__ import annotations


class ProfileError(Exception):
    """Base class caught by the profile CLI."""


class ProfileSourceError(ProfileError):
    """Profile source resolution or parsing failed."""


class ProfileCompileError(ProfileError):
    """Profile compilation or publication failed."""


class ProfileApplyError(ProfileError):
    """Profile application or recovery failed."""


class ProfileLaunchError(ProfileError):
    """Profile launch policy or projection failed."""


class ProfilePermissionsError(ProfileError):
    """Project-permission rendering failed."""


__all__ = [
    "ProfileApplyError",
    "ProfileCompileError",
    "ProfileError",
    "ProfileLaunchError",
    "ProfilePermissionsError",
    "ProfileSourceError",
]
