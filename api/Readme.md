# Project Euphonia serving model API

Deploy transcription API as service in Google Cloud run:
(see also: <https://cloud.google.com/build/docs/build-push-docker-image>)

## Prerequisites

Configure environment variables:

```bash
export PROJECT_ID="my_project_id"
export LOCATION="my-project-location"
export TAG="V1"
```

Run `gcloud auth login` and create a repository in GCP:

```bash
gcloud artifacts repositories create project-euphonia \
    --repository-format=docker \
    --location=$LOCATION \
    --description="Project Euphonia Docker repository"
```

Build a new image and upload to repository:

```bash
gcloud builds submit \
    --region=$LOCATION \
    --project=$PROJECT_ID \
    --tag $LOCATION-docker.pkg.dev/$PROJECT_ID/project-euphonia/transcribe:$TAG \
    .
```

## Container deploy

[Deploy](https://cloud.google.com/sdk/gcloud/reference/run/deploy) and run service:

```bash
gcloud run deploy project-euphonia-inference \
    --region=LOCATION \
    --project=test \
    --ingress=all \
    --timeout=300s \
    --memory=8Gi --cpu=2 \
    --image=LOCATION-docker.pkg.dev/PROJECT_ID/REPO_NAME/PATH:TAG
```

**Note**: when deploying whisper large, we need more memory, and in consequence also up the CPUs. Configure `memory` and `cpu` accordingly.

**Note**: when deploying model trained for a language other than English, configure the language in the app python script. For example, this is the configuration for serving Italian transcription models:

```python
# set language to whatever language you used in fine-tuning the model
LANGUAGE = "it"
```

## Test

- find your active Cloud Run endpoints under: <http://console.cloud.google.com/run>
- when you click on the specific service name (if you keep the settings from above, it will be called "`project-euphonia-inference`"), you'll find a URL, eg like `https://project-euphonia-inference-xyz.LOCATION.run.app`.
- test eg with curl (it might take a few minutes for the service to be ready):
curl -F wav=@<path-to-wav-file> <https://project-euphonia-inference-xyz.LOCATION.run.app/transcribe>

## Intended Use

Project Euphonia is a set of open-source toolkits intended for use by developers to create and customize speech recognition solutions. It provides tools and documentation for collecting speech data, fine-tuning open-source Automatic Speech Recognition (ASR) models, and deploying those models for speech-to-text transcription.The open-source toolkits, in its original form, is not intended to be used without modification for the diagnosis, treatment, mitigation, or prevention of any disease or medical condition. Developers are solely responsible for making substantial changes to Project Euphonia’s open-source toolkits and for ensuring that any applications they create comply with all applicable laws and regulations, including those related to medical devices.

### Indications for Use

Project Euphonia’s open-source toolkits is intended to provide developers with the capability to:

- Collect volunteered speech data using a customizable mobile application.
Fine-tune open-source Automatic Speech Recognition (ASR) models using provided training recipes and infrastructure.
- Deploy trained ASR models for speech-to-text transcription.
- Create accessibility solutions and other applications that leverage customized speech recognition technology.

### Toolkit Description

Project Euphonia’s open-source toolkits are designed to facilitate the creation of customized speech recognition solutions. The toolkits consists of:

- A Flutter-based mobile application for recording speech data and associating it with text phrases. The application stores data in a Firebase Storage instance controlled by the developer.
- Google Colab notebooks providing example code and documentation for fine-tuning open-source Automatic Speech Recognition (ASR) models. The notebooks will help inform developers on the following topics: data preparation, model training, and performance evaluation.
- Example code for deploying a web service that performs speech-to-text transcription using the fine-tuned ASR models. The web service can be deployed to cloud platforms such as Google Cloud Run.

-- Additional information
-- just run app_dia and access http://localhost:50001/web/voice_assist.html 
