import os


SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")

DEFAULT_ADMIN_USERNAME = os.environ.get("MAESTRO_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("MAESTRO_ADMIN_PASSWORD", "admin")
