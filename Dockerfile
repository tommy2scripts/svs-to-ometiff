FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (required for some image processing packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create an unprivileged runtime user before copying application files.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser && \
    mkdir -p /data && \
    chown -R appuser:appuser /app /data

# Copy the project files
COPY --chown=appuser:appuser . /app/

# Install the application and gunicorn
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir gunicorn

# Expose the Flask port
EXPOSE 5000

# Set environment variables for production execution
ENV SVS_GUI_HOST=0.0.0.0
ENV SVS_GUI_PORT=5000
ENV SVS_GUI_MAX_JOBS=1

# Create a volume mount point for image data
VOLUME /data

USER appuser

# Run the application via gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "0", "svs_to_ometiff_gui.serve:app"]
