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
        'mysql+pymysql://user:password@localhost/agent_collab'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    # Register API blueprint only (agent-only, no web UI)
    from app.routes.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app
