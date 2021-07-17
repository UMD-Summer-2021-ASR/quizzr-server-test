import json
import os

import pymongo
import pytest
from googleapiclient.http import MediaFileUpload

import gdrive_authentication
from server import create_app


@pytest.fixture(scope="session")
def env_name():
    return "testing"  # Deprecated


@pytest.fixture(scope="session")
def db_name():
    return "QuizzrDatabaseTest"


@pytest.fixture(scope="session")
def g_folder_name():
    return "RecordingsTestAuto"


@pytest.fixture(scope="session")
def g_folder_parents():
    return None


@pytest.fixture(scope="session")
def cached_ids_path():
    return ".id_cache.json"


@pytest.fixture(scope="session")
def qs_dir():
    return os.environ["SERVER_DIR"]


@pytest.fixture(scope="session")
def input_dir():
    return "input"


@pytest.fixture(scope="session")
def qs_metadata(qs_dir):
    with open(os.path.join(qs_dir, "metadata.json"), "r") as meta_f:
        return json.load(meta_f)


@pytest.fixture(scope="session")
def flask_app(env_name, g_folder_id):
    app = create_app(env_name, {"TESTING": True, "G_FOLDER_ID": g_folder_id, "DIFFICULTY_LIMITS": [3, 6, None]})
    return app


@pytest.fixture(scope="session")
def client(flask_app):
    with flask_app.test_client() as client:
        return client


@pytest.fixture(scope="session")
def mongodb_client():
    connection_string = os.environ["CONNECTION_STRING"]
    return pymongo.MongoClient(connection_string)


@pytest.fixture(scope="session")
def google_drive(qs_dir):
    gdrive = gdrive_authentication.GDriveAuth(os.path.join(qs_dir, "privatedata"))
    return gdrive


@pytest.fixture(scope="session")
def g_folder_id(google_drive, cached_ids_path, g_folder_name, g_folder_parents):
    # If override not defined, try looking in the cached IDs list
    folder_id = None
    cached_ids = {}
    if os.path.exists(cached_ids_path):
        with open(cached_ids_path, "r") as cache_f:
            cached_ids = json.load(cache_f)
        folder_id = cached_ids.get(g_folder_name)

    # If no results were found from looking in the cached IDs list or there is no cached IDs list, create a new ID
    if not folder_id:
        file_metadata = {
            "name": g_folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        if g_folder_parents:
            file_metadata["parents"] = g_folder_parents
        folder = google_drive.drive.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')

    yield folder_id

    # TODO: Make it only write if there is no cached IDs or the list of cached IDs changed
    cached_ids[g_folder_name] = folder_id
    with open(cached_ids_path, "w") as cache_f:
        json.dump(cached_ids, cache_f)


@pytest.fixture(scope="session")
def g_file_id(google_drive, g_folder_id, input_dir):
    file_name = "test.wav"
    file_metadata = {"name": file_name, "parents": [g_folder_id]}
    file_path = os.path.join(input_dir, file_name)

    media = MediaFileUpload(file_path, mimetype="audio/wav")
    gfile = google_drive.drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
    gfile_id = gfile.get("id")
    return gfile_id


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
