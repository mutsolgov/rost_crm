FROM python:3.12-alpine

WORKDIR /app

COPY app.py seed_data.json /app/

EXPOSE 8081

ENV PYTHONUNBUFFERED=1 \
    PORT=8081 \
    HOST=0.0.0.0

RUN adduser -D -u 10002 mockuser
USER mockuser

CMD ["python", "-u", "app.py"]
