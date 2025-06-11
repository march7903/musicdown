# Music Downloader Web

This project provides a simple web interface for the original PyQt based music downloader. It exposes a FastAPI application that allows logging in via QR code, searching for songs and downloading them through the browser. The application can be built and run using Docker.

## Usage

1. Build the Docker image:

```bash
docker build -t musicdown-web .
```

2. Run the container:

```bash
docker run -p 8000:8000 musicdown-web
```

To enable lightweight download mode where the browser handles file downloads,
start the container with the `USE_LIGHT_DOWNLOAD_MODE` environment variable:

```bash
docker run -p 8000:8000 -e USE_LIGHT_DOWNLOAD_MODE=true musicdown-web
```

3. Open `http://localhost:8000` in your browser. You will be prompted to scan a QR code for login and can then search and download songs.

The downloads will be stored inside the container under `/app/downloads`.

