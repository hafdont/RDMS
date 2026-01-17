from flask import Flask
from flask_login import LoginManager
from .config import Config, ProductionConfig, DevelopmentConfig
from .utils.db import db, init_db
from .utils.notifications import init_notifications, socketio
from .utils.helpers import time_ago_helper
from .utils.storage_service import storage_service
from .models import * 
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
import os
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
import asyncio
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
import logging
from datetime import datetime
from .utils.cache import init_cache




load_dotenv()

bcrypt = Bcrypt()
login_manager = LoginManager()

mail = Mail()

def now():
    return datetime.utcnow()

def create_app():
    app = Flask(__name__)

    # ---- Initialize Sentry ----
    sentry_logging = LoggingIntegration(
        level=logging.INFO,          
        event_level=logging.ERROR    
    )
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),  # Make sure SENTRY_DSN is in your .env
        integrations=[
            FlaskIntegration(),
            SqlalchemyIntegration(),
            sentry_logging,
        ],
        traces_sample_rate=0.5,       # Capture 50% of transactions
        profiles_sample_rate=0.20,    # Enable profiling
        environment=os.getenv("APP_ENV", "production"),
        release="my-app@1.0.0",       # Optional: set your app version
    )

    # Nouw using Flask environment variable
    app_env = os.getenv("APP_ENV", "production").lower()

    
    if app_env == "production":
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    csrf = CSRFProtect(app)

    app.jinja_env.globals['now'] = now

    # Initialize DigitalOcean Spaces Storage Service - PRODUCTION READY
    storage_service.init_app(app) 

    # Init extensions
    init_db(app)
    bcrypt.init_app(app)
    init_notifications(app)
    init_cache(app)


    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'  # Optional: Set default login view

   # Initialize Flask-Mail
    mail.init_app(app)
    
    # User loader function
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))  # Assuming the user ID is stored in the session
    
    @app.context_processor
    def inject_storage_service():
        from app.utils.storage_service import storage_service
        return dict(storage_service=storage_service)
  
    # Define Max File Size (16 MB) - replaces patch_request_class
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

    # Define Allowed Extensions (Moved from UploadSet)
    app.config['ALLOWED_EXTENSIONS'] = {
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv',
        'odt', 'ods', 'odp', 'rtf', 'xml', 'json', 'zip', 'rar', '7z', 'tar', 'gz'
    }
    
    @app.context_processor
    def inject_globals():
        from app.models import RoleEnum
        return dict(RoleEnum=RoleEnum)
    
    @app.context_processor
    def utility_processor():
        return dict(timeAgo=time_ago_helper) # Make it available as 'timeAgo'

    # Register Blueprints
    from .routes import register_routes
    register_routes(app)

    return app
