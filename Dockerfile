FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY scripts/requirements.txt ./scripts/
RUN pip install --no-cache-dir -r scripts/requirements.txt jinja2

# Copy repository files
COPY . .

EXPOSE 8000

# Generate site on startup to ensure latest data is rendered, then serve
CMD ["sh", "-c", "python scripts/build_site.py && python -m http.server 8000 --directory _site"]
