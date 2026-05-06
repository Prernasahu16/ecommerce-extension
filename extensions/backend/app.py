from flask import Flask
from flask_cors import CORS
import os
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)
    CORS(app)

    app.config["SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret")

    # Basic DB config
    app.config["DB_HOST"] = os.getenv("DB_HOST", "localhost")
    app.config["DB_PORT"] = os.getenv("DB_PORT", "5432")
    app.config["DB_NAME"] = os.getenv("DB_NAME", "ecommerce")
    app.config["DB_USER"] = os.getenv("DB_USER", "postgres")
    app.config["DB_PASSWORD"] = os.getenv("DB_PASSWORD", "")

    @app.route("/")
    def index():
        return {"status": "ok", "message": "Ecommerce API running"}

    return app