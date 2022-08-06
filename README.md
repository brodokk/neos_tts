# Usage

## Installation

You need to build the container then you can launch it with docker compose for example:

```
docker-compose up --build
```

## Configuration

You need to configure create at least one `AUTH KEY` for use the API. Use the `fenkm` command:

```
fenkm genkey
```

## Final usage

Quick example with curl, don't forget to use the `AUTH KEY` generated before.

```
curl -v "https://tts.neos.spacealicorn.network/api/cached/tts?text=uwu&speaker_id=&style_wav=&auth_key=<AUTH KEY>" --output /dev/null
```

# Bugs

Firefox don't seems to like the ogg file, please use wav for now or use a chrome based webrowser.
