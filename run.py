#!/usr/bin/env python3
"""
Agent Collab - Run Script
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, debug=True)
