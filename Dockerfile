FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# adb : requis par logos_bot (sync Samsung ADB via WiFi)
RUN apt-get update && apt-get install -y --no-install-recommends adb tzdata \
    && rm -rf /var/lib/apt/lists/*

# adb stocke les clés RSA pour le pairing de l'appareil
RUN mkdir -p /root/.android

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "src/app/ui_main.py"]
