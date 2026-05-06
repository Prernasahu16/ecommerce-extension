# ============================================================
# EXTENSION — run_with_extensions.py
# Use this file INSTEAD of backend/run.py to start the server
# with all extension modules loaded.
#
# The original run.py is UNCHANGED.
# This file imports and wraps it.
# ============================================================

import sys, os
# Make sure backend root is on path
sys.path.insert(0, os.path.dirname(__file__))

import logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s — %(message)s")

# 1. Start with the existing app factory (UNCHANGED)
from app import create_app
app = create_app()

# 2. Register extension modules on top (NEW)
from app_extension import register_extensions
register_extensions(app)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"[Server] Starting with extensions on port {port}")
    print(f"[Server] Extension endpoints available at: http://localhost:{port}/api/ext/")
    app.run(host="0.0.0.0", port=port, debug=debug)
