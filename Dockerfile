FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/app
WORKDIR /opt/app
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt && useradd --uid 10001 --create-home jingxin && mkdir /data && chown jingxin /data
COPY app ./app
COPY static ./static
COPY templates ./templates
USER jingxin
WORKDIR /data
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
