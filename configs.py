# config.py
"""
Configuration and setup for the Asana Integration Platform
"""

import os
import logging
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this')
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size
    app.config['JSON_SORT_KEYS'] = False
    
    return app

def setup_logging():
    """Configure application logging"""
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/app.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def setup_rate_limiter(app):
    """Configure rate limiting"""
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per hour"],
        storage_uri="memory://"
    )
    return limiter

def ensure_directories():
    """Create necessary directories"""
    directories = ['logs', 'uploads', 'server_files', 'templates', 'static']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
