#!flask/bin/python
import argparse
import io
import json
import os
import sys
import toml
from threading import Lock
from pathlib import Path
from typing import Union

from flask import Flask, render_template, request, send_file, abort
from flask import url_for as flask_url_for

from TTS.config import load_config
from TTS.utils.manage import ModelManager
from TTS.utils.synthesizer import Synthesizer

from functools import lru_cache

from pydub import AudioSegment

from fenkeysmanagement import KeyManager

from flask_sqlalchemy import SQLAlchemy
from flask_statistics import Statistics

def create_argparser():
    def convert_boolean(x):
        return x.lower() in ["true", "1", "yes"]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list_models",
        type=convert_boolean,
        nargs="?",
        const=True,
        default=False,
        help="list available pre-trained tts and vocoder models.",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="tts_models/en/ljspeech/tacotron2-DDC",
        help="Name of one of the pre-trained tts models in format <language>/<dataset>/<model_name>",
    )
    parser.add_argument("--vocoder_name", type=str, default=None, help="name of one of the released vocoder models.")

    # Args for running custom models
    parser.add_argument("--config_path", default=None, type=str, help="Path to model config file.")
    parser.add_argument(
        "--model_path",
        type=str,
        default=None,
        help="Path to model file.",
    )
    parser.add_argument(
        "--vocoder_path",
        type=str,
        help="Path to vocoder model file. If it is not defined, model uses GL as vocoder. Please make sure that you installed vocoder library before (WaveRNN).",
        default=None,
    )
    parser.add_argument("--vocoder_config_path", type=str, help="Path to vocoder model config file.", default=None)
    parser.add_argument("--speakers_file_path", type=str, help="JSON file for multi-speaker model.", default=None)
    parser.add_argument("--port", type=int, default=5002, help="port to listen on.")
    parser.add_argument("--use_cuda", type=convert_boolean, default=False, help="true to use CUDA.")
    parser.add_argument("--debug", type=convert_boolean, default=False, help="true to enable Flask debug mode.")
    parser.add_argument("--show_details", type=convert_boolean, default=False, help="Generate model detail page.")
    return parser


# parse the args
args = create_argparser().parse_args()

path = Path(__file__).parent / "../.models.json"
manager = ModelManager(path)

if args.list_models:
    manager.list_models()
    sys.exit()

# update in-use models to the specified released models.
model_path = None
config_path = None
speakers_file_path = None
vocoder_path = None
vocoder_config_path = None

# CASE1: list pre-trained TTS models
if args.list_models:
    manager.list_models()
    sys.exit()

# CASE2: load pre-trained model paths
if args.model_name is not None and not args.model_path:
    model_path, config_path, model_item = manager.download_model(args.model_name)
    args.vocoder_name = model_item["default_vocoder"] if args.vocoder_name is None else args.vocoder_name

if args.vocoder_name is not None and not args.vocoder_path:
    vocoder_path, vocoder_config_path, _ = manager.download_model(args.vocoder_name)

# CASE3: set custom model paths
if args.model_path is not None:
    model_path = args.model_path
    config_path = args.config_path
    speakers_file_path = args.speakers_file_path

if args.vocoder_path is not None:
    vocoder_path = args.vocoder_path
    vocoder_config_path = args.vocoder_config_path

# load models
synthesizer = Synthesizer(
    tts_checkpoint=model_path,
    tts_config_path=config_path,
    tts_speakers_file=speakers_file_path,
    tts_languages_file=None,
    vocoder_checkpoint=vocoder_path,
    vocoder_config=vocoder_config_path,
    encoder_checkpoint="",
    encoder_config="",
    use_cuda=args.use_cuda,
)

use_multi_speaker = hasattr(synthesizer.tts_model, "num_speakers") and (
    synthesizer.tts_model.num_speakers > 1 or synthesizer.tts_speakers_file is not None
)

speaker_manager = getattr(synthesizer.tts_model, "speaker_manager", None)
# TODO: set this from SpeakerManager
use_gst = synthesizer.tts_config.get("use_gst", False)
key_manager = KeyManager()

app = Flask(__name__)

app.config.from_file("config.toml", load=toml.load)
for mandatory_key in ['SQLALCHEMY_DATABASE_URI', 'ADMIN_KEY']:
    if not app.config.get(mandatory_key):
        raise ValueError("{} cannot be empty".format(mandatory_key))

class TTSException(Exception):
    pass

db = SQLAlchemy(app)

class Request(db.Model):
    __tablename__ = "request"

    index = db.Column(db.Integer, primary_key=True, autoincrement=True)
    response_time = db.Column(db.Float)
    date = db.Column(db.DateTime)
    method = db.Column(db.String)
    size = db.Column(db.Integer)
    status_code = db.Column(db.Integer)
    path = db.Column(db.String)
    user_agent = db.Column(db.String)
    remote_address = db.Column(db.String)
    exception = db.Column(db.String)
    referrer = db.Column(db.String)
    browser = db.Column(db.String)
    platform = db.Column(db.String)
    mimetype = db.Column(db.String)

db.create_all()

def invalid_auth():
    abort(403)

def check_admin_auth():
    key = request.args.get("admin_key", None)
    if key != app.config.get('ADMIN_KEY'):
        abort(403)

def url_for(endpoint, **values):
    values['admin_key'] = app.config.get('ADMIN_KEY')
    return flask_url_for(endpoint, **values)

app.jinja_env.globals['url_for'] = url_for

statistics = Statistics(app, db, Request, check_admin_auth, '/admin/statistics')


def style_wav_uri_to_dict(style_wav: str) -> Union[str, dict]:
    """Transform an uri style_wav, in either a string (path to wav file to be use for style transfer)
    or a dict (gst tokens/values to be use for styling)

    Args:
        style_wav (str): uri

    Returns:
        Union[str, dict]: path to file (str) or gst style (dict)
    """
    if style_wav:
        if os.path.isfile(style_wav) and style_wav.endswith(".wav"):
            return style_wav  # style_wav is a .wav file located on the server

        style_wav = json.loads(style_wav)
        return style_wav  # style_wav is a gst dictionary with {token1_id : token1_weigth, ...}
    return None

def check_perms(request):
    auth_key = request.args.get("auth_key")
    if not auth_key:
        return False
    key_manager.reload_keys()
    if not key_manager.key_revoked(auth_key):
        return True
    return False

@app.route("/")
def index():
    return """
    TTS server customized by Kyubii and Brodokk for NeosVR.
    """

@app.route("/admin/details")
def details():
    check_admin_auth()
    model_config = load_config(config_path)
    if vocoder_config_path is not None and os.path.isfile(vocoder_config_path):
        vocoder_config = load_config(vocoder_config_path)
    else:
        vocoder_config = None

    return render_template(
        "details.html",
        show_details=args.show_details,
        model_config=model_config,
        vocoder_config=vocoder_config,
        args=args.__dict__,
    )

lock = Lock()
@app.route("/api/tts", methods=["GET"])
def tts():
    if not check_perms(request):
        return invalid_auth()
    try:
        return handle_request(request)
    except TTSException as exc:
        return str(exc), 500

def handle_request(request):
    with lock:
        text = request.args.get("text")
        speaker_idx = request.args.get("speaker_id", "")
        style_wav = request.args.get("style_wav", "")
        use_cache = request.args.get("use_cache", "true")
        style_wav = style_wav_uri_to_dict(style_wav)
        print(" > Model input: {}".format(text))
        print(" > Speaker Idx: {}".format(speaker_idx))

        if use_cache:
            try:
                out = cached_TTS(text, speaker_name=speaker_idx, style_wav=style_wav)
            except ValueError as exc:
                raise TTSException('{} is not a correct speaker_id'.format(exc))
            print("LRU cache stats: {}".format(cached_TTS.cache_info()))
        else:
            out = TTS(text, speaker_name=speaker_idx, style_wav=style_wav)

        return send_file(io.BytesIO(out), mimetype="audio/ogg")

@lru_cache(maxsize=512)
def cached_TTS(text, speaker_name, style_wav):
    return TTS(text, speaker_name, style_wav)

def TTS(text, speaker_name, style_wav):
    try:
        wavs = synthesizer.tts(text, speaker_name, style_wav)
    except KeyError as exc:
        raise TTSException('{} is not a correct speaker_id'.format(exc))
    wav_out = io.BytesIO()
    out = io.BytesIO()
    synthesizer.save_wav(wavs, wav_out)
    wav_out.seek(0)
    audio = AudioSegment.from_file_using_temporary_files(wav_out)
    audio.export(out, format="ogg")
    out.seek(0)
    return out.read()

def main():
    app.run(debug=args.debug, host="::", port=args.port)


if __name__ == "__main__":
    main()
