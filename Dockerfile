FROM python:3.11-slim

# Install system tools
RUN apt-get update && \
    apt-get install -y bash git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install uv globally (so it's ready in container)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Set PATH so uv is available in all layers and dev terminal
ENV PATH="/root/.cargo/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project files for layer cache
COPY pyproject.toml uv.lock* ./

# Copy the rest of your app
COPY . .

# Run your app
CMD ["python", "main.py"]