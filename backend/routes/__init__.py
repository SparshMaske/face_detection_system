from flask import Blueprint

# Define Blueprints
auth_bp = Blueprint('auth_bp', __name__)
dashboard_bp = Blueprint('dashboard_bp', __name__)
staff_bp = Blueprint('staff_bp', __name__)
visitors_bp = Blueprint('visitors_bp', __name__)
reports_bp = Blueprint('reports_bp', __name__)
analytics_bp = Blueprint('analytics_bp', __name__)
settings_bp = Blueprint('settings_bp', __name__)
camera_bp = Blueprint('camera_bp', __name__)
events_bp = Blueprint('events_bp', __name__)

# Import route modules so decorators bind handlers to each blueprint.
# Without these imports, blueprints are registered with no routes.
from . import auth  # noqa: F401,E402
from . import dashboard  # noqa: F401,E402
from . import staff  # noqa: F401,E402
from . import visitors  # noqa: F401,E402
from . import reports  # noqa: F401,E402
from . import analytics  # noqa: F401,E402
from . import settings  # noqa: F401,E402
from . import camera  # noqa: F401,E402
from . import events  # noqa: F401,E402
