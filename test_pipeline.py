import os
import random
from http import HTTPStatus

import pytest

from testutil import match_status, generate_audio_id


# For testing cases that the server is designed to handle on a regular basis.


@pytest.mark.usefixtures("mongodb", "qs_metadata")
class TestAnswer:
    @pytest.fixture(scope="session")
    def route(self):
        return "/answer/"

    @pytest.fixture
    def doc_setup(self, mongodb, qs_metadata):
        num_docs = 5
        audio_docs = []
        for i in range(1, num_docs + 1):
            audio_docs.append({
                "_id": generate_audio_id(),
                "vtt": "The quick brown fox jumps over the lazy dog.",
                "gentleVtt": "This is a dummy VTT.",
                "version": qs_metadata["version"],
                "score": {
                    "wer": i,
                    "mer": i,
                    "wil": i
                }
            })
        test_audio_doc = audio_docs[0]
        random.shuffle(audio_docs)
        audio_results = mongodb.Audio.insert_many(audio_docs)
        question_result = mongodb.RecordedQuestions.insert_one({"recordings": audio_results.inserted_ids})
        yield test_audio_doc
        mongodb.Audio.delete_many({"_id": {"$in": audio_results.inserted_ids}})
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})

    # Test Case: No difficulty specified.
    def test_any(self, client, route, doc_setup):
        required_response_fields = ["_id", "vtt", "gentleVtt"]
        response = client.get(route)
        response_body = response.get_json()
        assert match_status(HTTPStatus.OK, response.status)
        for field in required_response_fields:
            assert field in response_body
        assert doc_setup["_id"] == response_body["_id"]


@pytest.mark.usefixtures("client", "mongodb")
class TestUnprocAudio:
    @pytest.fixture(scope="session")
    def route(self):
        return "/audio/unprocessed/"

    @pytest.fixture
    def unrec_question(self, mongodb):
        question_result = mongodb.UnrecordedQuestions.insert_one({"transcript": "Foo"})
        yield question_result.inserted_id
        mongodb.UnrecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def doc_setup_normal(self, mongodb, unrec_question):
        audio_result = mongodb.UnprocessedAudio.insert_one({
            "_id": generate_audio_id(),
            "questionId": unrec_question
        })
        yield
        mongodb.UnprocessedAudio.delete_one({"_id": audio_result.inserted_id})

    @pytest.fixture
    def doc_setup_admin(self, mongodb, unrec_question):
        audio_result = mongodb.UnprocessedAudio.insert_one({
            "_id": generate_audio_id(),
            "questionId": unrec_question,
            "diarMetadata": "detect_num_speakers=False, max_num_speakers=3"
        })
        yield
        mongodb.UnprocessedAudio.delete_one({"_id": audio_result.inserted_id})

    # Test Case: One audio document submitted by a normal user.
    def test_normal(self, client, route, doc_setup_normal):
        required_doc_fields = ["_id", "transcript"]
        response = client.get(route)
        response_body = response.get_json()
        assert match_status(HTTPStatus.OK, response.status)
        assert "results" in response_body
        for doc in response_body.get("results"):
            for field in required_doc_fields:
                assert field in doc

    # Test Case: One audio document submitted by an administrator.
    def test_admin(self, client, route, doc_setup_admin):
        required_doc_fields = ["_id", "transcript", "diarMetadata"]
        response = client.get(route)
        response_body = response.get_json()
        assert match_status(HTTPStatus.OK, response.status)
        assert "results" in response_body
        for doc in response_body.get("results"):
            for field in required_doc_fields:
                assert field in doc


@pytest.mark.usefixtures("client", "mongodb", "google_drive")
class TestUpload:
    @pytest.fixture(scope="session")
    def route(self):
        return "/upload"

    @pytest.fixture(scope="session")
    def input_dir(self):
        return "input"

    @pytest.fixture
    def unrec_qid(self, input_dir, mongodb):
        transcript_path = os.path.join(input_dir, "transcript.txt")
        assert os.path.exists(transcript_path)
        with open(transcript_path, "r") as f:
            transcript = f.read()
        question_result = mongodb.UnrecordedQuestions.insert_one({"transcript": transcript})
        yield question_result.inserted_id
        mongodb.UnrecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def exact_data(self, mongodb, input_dir, unrec_qid):
        # TODO: Cleanup UnprocessedAudio collection (separate fixture) and Google Drive
        audio_path = os.path.join(input_dir, "exact.wav")
        assert os.path.exists(audio_path)
        user_result = mongodb.Users.insert_one({"recordedAudios": []})
        audio = open(audio_path, "rb")
        yield {"qid": unrec_qid, "audio": audio}
        audio.close()
        mongodb.Users.delete_one({"_id": user_result.inserted_id})

    @pytest.fixture
    def admin_data(self, exact_data):
        data = exact_data.copy()
        data["diarMetadata"] = "detect_num_speakers=False, max_num_speakers=3"
        return data

    @pytest.fixture
    def upload_cleanup(self, mongodb, google_drive):
        yield
        mongodb.UnprocessedAudio.delete_many({"_id": {"$exists": True}})

    # Test Case: Submitting a recording with exact accuracy.
    def test_exact(self, client, route, exact_data):
        response = client.post(route, data=exact_data, content_type='multipart/form-data')
        response_body = response.get_json()
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        assert response_body.get("prescreenSuccessful")

    # Test Case: Submitting a recording as an administrator.
    @pytest.mark.skip(reason="not finished yet")
    def test_admin(self, client, route, admin_data):
        response = client.post(route, data=admin_data, content_type='multipart/form-data')
        response_body = response.get_json()
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        assert response_body.get("prescreenSuccessful")
