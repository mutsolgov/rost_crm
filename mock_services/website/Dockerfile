FROM python:3.12-alpine

WORKDIR /app

COPY app.py seed_data.json ./

EXPOSE 8082

RUN adduser -D -u 10002 mockuser
USER mockuser

CMD ["python", "-u", "app.py"]
