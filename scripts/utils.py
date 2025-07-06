from functools import wraps
from flask import request, redirect, flash, g
from models import Company, db

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
        company = Company.query.filter_by(name=investor).first()
        if company:
            g.company_bucket = company.bucket_name
        else:
            g.company_bucket = None
        return f(*args, **kwargs)
    return decorated_function
