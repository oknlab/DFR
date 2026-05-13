FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# clone Scrapling repo as requested
RUN git clone --depth 1 https://github.com/D4Vinci/Scrapling /opt/Scrapling

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY start.sh ./start.sh
RUN chmod +x ./start.sh
EXPOSE 10000
CMD ["./start.sh"]
