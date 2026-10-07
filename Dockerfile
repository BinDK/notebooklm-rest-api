FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify supervisor openbox \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium
COPY . .
COPY supervisord.conf /etc/supervisor/conf.d/notebooklm.conf
RUN mkdir -p /data/notebooklm/profiles/default \
    && chmod 700 /data/notebooklm/profiles/default

EXPOSE 8000
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/notebooklm.conf"]
