import os
import secrets

import pymongo
import pytest
import yaml
from firebase_admin import storage

from server import create_app


@pytest.fixture(scope="session")
def db_name():
    return "QuizzrDatabaseTest"


@pytest.fixture(scope="session")
def blob_root_name():
    return "testing"


@pytest.fixture(scope="session")
def qs_dir():
    return os.environ["SERVER_DIR"]


@pytest.fixture(scope="session")
def input_dir():
    return "input"


@pytest.fixture(scope="session")
def api_doc_path(qs_dir):
    return os.path.join(qs_dir, "api", "backend.yaml")


@pytest.fixture(scope="session")
def server_api_doc(api_doc_path):
    with open(api_doc_path) as api_f:
        api = yaml.load(api_f.read(), Loader=yaml.FullLoader)
    return api


@pytest.fixture(scope="session")
def client(flask_app):
    with flask_app.test_client() as client:
        return client


@pytest.fixture(scope="session")
def mongodb_client():
    connection_string = os.environ["CONNECTION_STRING"]
    return pymongo.MongoClient(connection_string)


@pytest.fixture(scope="session")
def flask_app(blob_root_name, db_name):
    app = create_app({
        "Q_ENV": "testing",
        "DATABASE": db_name,
        "BLOB_ROOT": blob_root_name,
        "DIFFICULTY_LIMITS": [3, 6, None],
        "TESTING": True
    })
    return app


@pytest.fixture(scope="session")
def firebase_bucket(flask_app):
    return storage.bucket()


@pytest.fixture(scope="session")
def blob_file(firebase_bucket, flask_app, input_dir):
    file_name = "test.wav"
    file_path = os.path.join(input_dir, file_name)

    blob_name = secrets.token_urlsafe(nbytes=32)
    blob_path = "/".join([flask_app.config["BLOB_ROOT"], "normal", blob_name])
    blob = firebase_bucket.blob(blob_path)
    blob.upload_from_filename(file_path)
    yield blob_name
    blob.delete()


@pytest.fixture(scope="session")
def mongodb(mongodb_client, db_name):
    database = mongodb_client.get_database(db_name)
    return database
    # Might be too dangerous to allow to execute.
    # query = {"_id": {"$exists": True}}
    # database.Audio.delete_many(query)
    # database.RecordedQuestions.delete_many(query)
    # database.UnrecordedQuestions.delete_many(query)
    # database.UnprocessedAudio.delete_many(query)
    # database.Users.delete_many(query)