#!/usr/bin/env python3
"""
Agent Collab - Run Script
"""
import logging
import os
from app import create_app

# Configure logging
log_dir = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'chatter.log')),
        logging.StreamHandler()
    ]
)

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, debug=False)
