# Stage 1: Build rtl_433
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y \
    gcc \
    git \
    cmake \
    libtool \
    libusb-1.0-0-dev \
    librtlsdr-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/merbanan/rtl_433.git /tmp/rtl_433 \
    && cd /tmp/rtl_433 \
    && mkdir build && cd build \
    && cmake .. \
    && make -j$(nproc) \
    && make install

# Stage 2: Final Image
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libusb-1.0-0 \
    librtlsdr0 \
    && rm -rf /var/lib/apt/lists/*

# Copy rtl_433 from builder
COPY --from=builder /usr/local/bin/rtl_433 /usr/local/bin/rtl_433

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY dashboard/ dashboard/

# Create data directory for SQLite
RUN mkdir -p data

# Expose port 5000
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
