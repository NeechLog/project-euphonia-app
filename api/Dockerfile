# FROM python:3.11
FROM python:3.10-slim

# Install required packages
RUN apt-get update && \
    apt-get install -y \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./
#ADD requirements.txt . 
# Install dependencies.

#RUN pip install git+https://github.com/nari-labs/dia.git
RUN pip install -r requirements.txt
# Run the web service on container startup.


# Standard whisper based app
# ENV FLASK_APP=app_whisper.py
# CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0", "-p", "8080"]

# Faster whisper-based app
ENV FLASK_APP=app_faster_whisper.py
ENV PYTHON_LOG_LEVEL=INFO
CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0", "-p", "8080"]





