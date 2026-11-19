"""Paste this into the WSGI configuration file for the PythonAnywhere web app."""

import os
import sys
from dotenv import load_dotenv

project_dir = os.path.expanduser("~/TTsebisa")
load_dotenv(os.path.join(project_dir, ".env"))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from app import app as application
