FROM python:3.11-slim

WORKDIR /app

# تثبيت المكتبات النظام
RUN apt-get update && apt-get install -y \
    gcc \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# إنشاء مجلدات ضرورية
RUN mkdir -p sessions logs

# تشغيل السكرابر
CMD ["python", "main.py"]
