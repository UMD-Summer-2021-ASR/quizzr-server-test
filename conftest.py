import json
import os

import pymongo
import pytest

import gdrive_authentication
from server import create_app


@pytest.fixture(scope="session")
def db_name():
    return "QuizzrDatabaseTest"


@pytest.fixture(scope="session")
def client(db_name):
    app = create_app(db_name)
    with app.test_client() as client:
        return client


@pytest.fixture(scope="session")
def mongodb_client():
    connection_string = os.environ["CONNECTION_STRING"]
    return pymongo.MongoClient(connection_string)


@pytest.fixture(scope="session")
def qs_dir():
    return os.environ["SERVER_DIR"]


@pytest.fixture(scope="session")
def qs_metadata(qs_dir):
    with open(os.path.join(qs_dir, "metadata.json"), "r") as meta_f:
        return json.load(meta_f)


@pytest.fixture(scope="session")
def google_drive(qs_dir):
    gdrive = gdrive_authentication.GDriveAuth(os.path.join(qs_dir, "privatedata"))
    return gdrive


@pytest.fixture(scope="session")
def mongodb(mongodb_client, db_name):
    database = mongodb_client.get_database(db_name)
    yield database
    query = {"_id": {"$exists": True}}
    database.Audio.delete_many(query)
    database.RecordedQuestions.delete_many(query)
    database.UnrecordedQuestions.delete_many(query)
    database.UnprocessedAudio.delete_many(query)
    database.Users.delete_many(query)
