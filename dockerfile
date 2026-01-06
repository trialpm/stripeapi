# Use a lightweight Python base image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the application code
COPY work.py .

# Install Python dependencies
RUN pip install --no-cache-dir flask requests gunicorn

# Expose the port the app runs on
EXPOSE 5000

# Run the application using gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "work:app"]
