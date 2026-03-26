# syntax=docker/dockerfile:1
# Picasso MCP Server Dockerfile
# [ Picasso MCP | Python MCP Server for Google AI Studio Image Generation ]
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /images

EXPOSE 8000

ENTRYPOINT [ "python3", "src/server.py" ]
