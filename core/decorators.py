from functools import wraps

from flask import abort
from flask_login import current_user


def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not getattr(current_user, "is_admin", False):
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view