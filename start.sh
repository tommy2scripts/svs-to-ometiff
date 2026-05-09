#!/bin/bash
cd "$(dirname "$0")"

echo "Starting svs-to-ometiff GUI..."
PYTHONPATH=src python3 -m svs_to_ometiff_gui.serve
