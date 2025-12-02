# Project Setup Guide

## Prerequisites
- Python 3.x
- UV package manager

## Installation

1. **Synchronize dependencies**:
   ```bash
   uv sync
   ```

## Running the Application

1. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

2. **Install the dependencies**:
   ```bash
   uv pip install -e .
   uv pip install -e ".[audio,ml,dev]"
   ```

3. **Set the path correctly**:
   ```bash
   export PYTHONPATH=$(pwd)
   ```

4. **Start the application**:
   ```bash
   euphonia-serve
   ```
