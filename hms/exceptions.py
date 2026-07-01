"""Custom exceptions used across the Hospital Management System."""


class HMSError(Exception):
    """Base exception for all HMS errors."""


class NotFoundError(HMSError):
    """Raised when a requested record does not exist."""


class ValidationError(HMSError):
    """Raised when input data fails validation rules."""


class ConflictError(HMSError):
    """Raised when an operation conflicts with existing state
    (e.g. double-booking a doctor, admitting to an occupied bed)."""
