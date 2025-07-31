# Dockerfile
FROM python:3.11-slim

# Install git
RUN apt-get update && \
    apt-get install -y git curl bash && \
    rm -rf /var/lib/apt/lists/*

# Install uv 
RUN curl -LsSf https://astral.sh/uv/install.sh | bash

# Set environment so uv is on PATH
ENV PATH="/root/.cargo/bin:${PATH}"

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code
COPY . .

CMD ["python", "app.py"]