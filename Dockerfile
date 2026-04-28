FROM docker.1ms.run/library/python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/config /app/downloads

ENV FLASK_ENV=production

EXPOSE 8200

CMD ["gunicorn", "-w", "4", "--timeout", "120", "-b", "0.0.0.0:8200", "clash_config_parser.app:app"]
