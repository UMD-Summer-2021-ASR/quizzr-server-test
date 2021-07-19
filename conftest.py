import json
import os

import pymongo
import pytest
from googleapiclient.http import MediaFileUpload

import gdrive_authentication
from server import create_app
from tpm import QuizzrTPM


@pytest.fixture(scope="session")
def db_name():
    return "QuizzrDatabaseTest"


@pytest.fixture(scope="session")
def g_folder_name():
    return "RecordingsTestAuto"


@pytest.fixture(scope="session")
def g_dir_struct_conf():
    return {
        "children": {
            "Buzz": {}
        }
    }


@pytest.fixture(scope="session")
def g_folder_parents():
    return None


@pytest.fixture(scope="session")
def cached_struct_path():
    return ".id_cache.json"


@pytest.fixture(scope="session")
def qs_dir():
    return os.environ["SERVER_DIR"]


@pytest.fixture(scope="session")
def input_dir():
    return "input"


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
def g_dir_struct(google_drive, cached_struct_path, g_folder_name, g_folder_parents, g_dir_struct_conf):
    return QuizzrTPM.init_g_dir_structure(google_drive.service, cached_struct_path, g_folder_name, g_dir_struct_conf)


@pytest.fixture(scope="session")
def flask_app(g_dir_struct, g_folder_name, db_name):
    app = create_app({
        "Q_ENV": "testing",
        "DATABASE": db_name,
        "G_FOLDER": g_folder_name,
        "G_DIR_STRUCT": g_dir_struct,
        "DIFFICULTY_LIMITS": [3, 6, None],
        "TESTING": True
    })
    return app


@pytest.fixture(scope="session")
def g_file_id(google_drive, g_dir_struct, input_dir):
    parent = QuizzrTPM.get_dir_id(g_dir_struct, "/")
    file_name = "test.wav"
    file_metadata = {"name": file_name, "parents": [parent]}
    file_path = os.path.join(input_dir, file_name)

    media = MediaFileUpload(file_path, mimetype="audio/wav")
    gfile = google_drive.service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    gfile_id = gfile.get("id")
    yield gfile_id
    google_drive.service.files().delete(fileId=gfile_id).execute()


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
