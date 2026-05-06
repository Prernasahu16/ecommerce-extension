#!/usr/bin/env python3
"""
patch_frontend.py — ONE-TIME patch for Nav.jsx and App.jsx.

Run from: v2_project/ecommerce_platform/frontend/
  python patch_frontend.py

Safety: script is idempotent — re-running does nothing if already patched.
Touches ONLY two specific lines in two files. Zero other changes.
"""

import os, sys

# Default: resolve relative to this script's location in the extensions folder
# Override by setting FRONTEND_PATH env var
FRONTEND = os.getenv(
    "FRONTEND_PATH",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "existing_project", "v2_project",
        "ecommerce_platform", "frontend"
    )
)
FRONTEND = os.path.realpath(FRONTEND)

# -------------------------------------------------------
# 1. Patch Nav.jsx — append intelligence link to LINKS array
# -------------------------------------------------------
nav_path = os.path.join(FRONTEND, "src", "components", "Nav.jsx")
NAV_MARKER   = '{ id: "architecture",    icon: "◫",  label: "Architecture" },'
NAV_NEW_LINK = '  { id: "intelligence",   icon: "🌐", label: "Intelligence" },'

with open(nav_path, "r") as f:
    nav = f.read()

if '"intelligence"' in nav:
    print("Nav.jsx — already patched, skipping")
else:
    nav = nav.replace(NAV_MARKER, NAV_MARKER + "\n" + NAV_NEW_LINK)
    with open(nav_path, "w") as f:
        f.write(nav)
    print("Nav.jsx — patched: intelligence link added")

# -------------------------------------------------------
# 2. Patch App.jsx — import ExtensionHubShell + add page render
# -------------------------------------------------------
app_path = os.path.join(FRONTEND, "src", "App.jsx")

APP_IMPORT_MARKER = 'import "./App.css";'
APP_NEW_IMPORT    = 'import ExtensionHub from "./pages/ExtensionHubShell";'

APP_RENDER_MARKER = '{page === "add-product"     && <AddProduct navigate={navigate} />}'
APP_NEW_RENDER    = '        {page === "intelligence"    && <ExtensionHub />}'

with open(app_path, "r") as f:
    app = f.read()

patched = False

if 'ExtensionHub' not in app:
    app = app.replace(APP_IMPORT_MARKER, APP_IMPORT_MARKER + "\n" + APP_NEW_IMPORT)
    patched = True

if '"intelligence"' not in app:
    app = app.replace(APP_RENDER_MARKER, APP_RENDER_MARKER + "\n" + APP_NEW_RENDER)
    patched = True

if patched:
    with open(app_path, "w") as f:
        f.write(app)
    print("App.jsx  — patched: import + render added")
else:
    print("App.jsx  — already patched, skipping")

print("\nDone. Run: npm run dev")
