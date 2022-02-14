#!/bin/bash

# Setup python virtual environment
cd /opt/factum
source venv/bin/activate

# run script
cd /opt/factum/app
python3 -u tools/cli/periodic.py
