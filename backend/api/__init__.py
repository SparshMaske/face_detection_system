"""Legacy API module path wrappers.

These shims keep old import paths working while real route implementations
remain in `routes/`.
"""

from .analytics_routes import analytics_bp
from .auth_routes import auth_bp
from .report_routes import reports_bp
from .settings_routes import settings_bp
from .staff_routes import staff_bp
from .visitor_routes import visitors_bp

__all__ = [
    "analytics_bp",
    "auth_bp",
    "reports_bp",
    "settings_bp",
    "staff_bp",
    "visitors_bp",
]
