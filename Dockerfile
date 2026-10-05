FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . && useradd --create-home flightcheck && mkdir /data && chown flightcheck:flightcheck /data
USER flightcheck
ENV FLIGHTCHECK_DB=/data/runs.sqlite3
EXPOSE 8000
CMD ["python", "-m", "flightcheck.cli", "--policy", "config/policy.yml", "serve", "--host", "0.0.0.0"]
