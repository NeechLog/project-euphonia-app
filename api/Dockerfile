# FROM python:3.11
FROM python:3.10-slim


# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

ADD requirements.txt . 
# Install dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup.


# Standard whisper based app
# ENV FLASK_APP=app_whisper.py
# CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0", "-p", "8080"]

# Faster whisper-based app
ENV FLASK_APP=app_faster_whisper.py
CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0", "-p", "8080"]





