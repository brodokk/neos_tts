# Usage

## Installation

You need to build the container then you can launch it with docker compose for example:

```
docker-compose up --build
```

## Configuration

### API

You need to configure create at least one `AUTH KEY` for use the API. Use the `fenkm` command:

```
fenkm genkey
```

### Admin

For access to the admin you will need to setup the following keys in the file `config.toml`:

- `SQLALCHEMY_DATABASE_URI`: database for statistics
- `ADMIN_KEY`: key for acces to the `/admin` endpoints

## Final usage

Quick example with curl, don't forget to use the `AUTH KEY` generated before.

```
curl -v "https://tts.neos.spacealicorn.network/api/cached/tts?text=uwu&speaker_id=&style_wav=&auth_key=<AUTH KEY>" --output /dev/null
```

### Parameters

for `/api` endpoints:

- `auth_key`: the auth key
- `text`: The text you want to convert in audio
- `speaker_id`: Id of the voice to use
- `use_cache`: Use the cache, default to true.

for `/admin` endpoints:

- `admin_key`: The admin key set in the config key `ADMIN_KEY`

# Know bugs

- Firefox don't seems to like the ogg file, please use wav for now or use a chrome based webrowser.
