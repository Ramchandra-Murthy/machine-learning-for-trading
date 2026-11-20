# The portal reuses the published, book-compatible ML4T runtime.
# Build with: docker compose --profile portal build portal
FROM ml4t/ml4t:latest

USER root
COPY apps/portal/requirements.txt /tmp/portal-requirements.txt
RUN /opt/ml4t/bin/pip install --no-cache-dir -r /tmp/portal-requirements.txt \
    && /opt/ml4t/bin/python -c "import streamlit; print('Streamlit', streamlit.__version__)" \
    && rm /tmp/portal-requirements.txt

WORKDIR /app
EXPOSE 8501
CMD ["/opt/ml4t/bin/streamlit", "run", "apps/portal/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
