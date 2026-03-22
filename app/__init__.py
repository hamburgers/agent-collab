"""
Agent Collab - Multi-Agent Collaboration Platform
Flask application factory
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
import os

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'mysql+pymysql://nba_local:nba_secure_pass@localhost/agent_collab'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Add timezone filter for Jinja2
    @app.template_filter('local_time')
    def local_time(dt, fmt='%b %d, %Y %I:%M %p'):
        """Convert UTC datetime to EST and format. Falls back to string if not datetime."""
        if dt is None:
            return ''
        if not isinstance(dt, datetime):
            return str(dt)
        # Convert from UTC to EST (UTC-5)
        est_offset = timedelta(hours=-5)
        est_dt = dt.replace(tzinfo=timezone.utc).astimezone(timezone(est_offset))
        return est_dt.strftime(fmt)
    
    return app
