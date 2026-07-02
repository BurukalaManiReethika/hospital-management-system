from functools import wraps

from flask import abort
from flask_login import current_user


def roles_required(*roles):
    """Restrict a view to users whose role is in `roles`. Admin always allowed."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role != "admin" and current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return decorator
