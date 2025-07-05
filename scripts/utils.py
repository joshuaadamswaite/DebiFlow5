from functools import wraps
from flask import request, redirect, flash

def build_investor_path(investor, subfolder, filename):
    """
    Build a standardized GCS path for storing investor files.
    """
    return f"Investors/{investor}/{subfolder}/{filename}"

def require_investor(f):
    """
    Decorator to enforce that 'investor' is provided in request args or form.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        investor = request.args.get("investor") or request.form.get("investor")
        if not investor:
            flash("❌ No investor selected.")
            return redirect("/")
        kwargs['investor'] = investor
        return f(*args, **kwargs)
    return decorated_function
