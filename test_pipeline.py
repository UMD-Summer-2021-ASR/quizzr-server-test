import os
import random
from http import HTTPStatus

import bson
import pytest

from testutil import match_status, generate_audio_id
# For testing cases that the server is designed to handle on a regular basis.


@pytest.mark.usefixtures("mongodb", "client")
class TestCheckAnswer:
    ROUTE = "/answer/check"

    @pytest.fixture(scope="session")
    def correct_answer(self):
        return "Foo"

    @pytest.fixture(scope="session")
    def incorrect_answer(self):
        return "Bar"

    @pytest.fixture
    def question_id(self, mongodb, correct_answer):
        question_result = mongodb.RecordedQuestions.insert_one({"answer": correct_answer})
        yield question_result.inserted_id
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})

    # Test Case: The user provides a correct answer
    def test_correct(self, client, question_id, correct_answer):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": correct_answer})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert response_body["correct"]

    # Test Case: The user provides an incorrect answer
    def test_incorrect(self, client, question_id, incorrect_answer):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": incorrect_answer})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert not response_body["correct"]


@pytest.mark.usefixtures("g_file_id")
class TestGetFile:
    ROUTE = "/download/"

    @pytest.fixture
    def full_route(self, g_file_id):
        return self.ROUTE + g_file_id

    def test_download(self, client, full_route):
        response = client.get(full_route)
        assert match_status(HTTPStatus.OK, response.status)


@pytest.mark.usefixtures("mongodb", "client", "qs_metadata")
class TestGetRec:
    ROUTE = "/answer/"

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

    # Test Case: No difficulty specified
    def test_any(self, client, doc_setup):
        required_response_fields = ["_id", "vtt", "gentleVtt"]
        response = client.get(self.ROUTE)
        response_body = response.get_json()
        assert match_status(HTTPStatus.OK, response.status)
        for field in required_response_fields:
            assert field in response_body
        assert doc_setup["_id"] == response_body["_id"]


@pytest.mark.usefixtures("client", "flask_app", "mongodb")
class TestGetTranscript:
    DIFFICULTY_TRIALS = 5
    RANDOM_TRIALS = 5
    MIN_DOCS_RANDOM = 3
    BATCH_SIZE = 3

    ROUTE = "/record/"

    @pytest.fixture(scope="session")
    def difficulty_limits(self, flask_app):
        return flask_app.config["DIFFICULTY_LIMITS"]

    @pytest.fixture(scope="session")
    def rec_difficulties(self, difficulty_limits):
        ds = []
        for i, limit in enumerate(difficulty_limits):
            if limit is not None:
                ds.append(limit)
            else:
                ds.append(difficulty_limits[i - 1] + 1)
        return ds

    @pytest.fixture(scope="session")
    def difficulty_bounds(self, difficulty_limits):
        lower = 0
        upper = difficulty_limits[-1]
        if upper is None:
            upper = difficulty_limits[-2] + self.MIN_DOCS_RANDOM
        return lower, upper

    @pytest.fixture
    def question_doc(self, mongodb):
        question_result = mongodb.UnrecordedQuestions.insert_one({"transcript": "Foo"})
        yield question_result.inserted_id
        mongodb.UnrecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def question_docs(self, mongodb):
        question_docs = [
            {"transcript": "Foo"},
            {"transcript": "Bar"},
            {"transcript": "Baz"}
        ]
        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def difficulties_question(self, mongodb, rec_difficulties):
        question_docs = []
        for d in rec_difficulties:
            question_docs.append({"transcript": "Foo", "recDifficulty": d})

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def difficulties_questions(self, mongodb, difficulty_bounds):
        question_docs = []
        for i in range(difficulty_bounds[0], difficulty_bounds[1] + 1):
            question_docs.append({"transcript": str(bson.ObjectId()), "recDifficulty": i})  # Equivalence buster

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def question_batch(self, mongodb):
        question_docs = []
        for i in range(0, self.BATCH_SIZE + 1):
            question_docs.append({"transcript": "Foo"})

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def question_batch_lesser(self, mongodb):
        question_docs = []
        for i in range(0, 2):
            question_docs.append({"transcript": "Foo"})

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def question_batch_random(self, mongodb):
        question_docs = []
        for i in range(0, self.MIN_DOCS_RANDOM * self.BATCH_SIZE):
            question_docs.append({"transcript": str(bson.ObjectId())})  # Equivalence buster

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def difficulties_question_batch(self, mongodb, rec_difficulties):
        question_docs = []
        for d in rec_difficulties:
            for i in range(0, self.BATCH_SIZE + 1):
                question_docs.append({"transcript": "Foo", "recDifficulty": d})

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def difficulties_question_batch_random(self, mongodb, rec_difficulties):
        question_docs = []
        for d in rec_difficulties:
            for i in range(0, self.MIN_DOCS_RANDOM * self.BATCH_SIZE):
                question_docs.append({"transcript": str(bson.ObjectId()), "recDifficulty": d})  # Equivalence buster

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    # Test Case: No difficulty specified
    def test_any(self, client, question_doc):
        required_response_fields = ["id", "transcript"]
        response = client.get(self.ROUTE)
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "results" in response_body and len(response_body["results"]) > 0
        doc = response_body["results"][0]
        for field in required_response_fields:
            assert field in doc

    # Test to see if the document retrieved is not always the same.
    def test_any_random(self, client, question_docs):
        max_attempts = self.RANDOM_TRIALS

        attempts = 0
        response = client.get(self.ROUTE)
        previous_response_body = response.get_json()
        while attempts < max_attempts:
            response = client.get(self.ROUTE)
            response_body = response.get_json()
            if response_body != previous_response_body:
                break
            attempts += 1
        assert attempts < max_attempts
    
    # Test Cases: Request for each difficulty
    def test_difficulty(self, client, mongodb, difficulties_question, difficulty_limits):
        for i in range(0, self.DIFFICULTY_TRIALS):
            for j, limit in enumerate(difficulty_limits):
                lower = difficulty_limits[j - 1] + 1 if j > 0 else None
                upper = limit
                response = client.get(self.ROUTE, query_string={"difficultyType": j})
                assert match_status(HTTPStatus.OK, response.status)
                response_body = response.get_json()
                assert "results" in response_body and len(response_body["results"]) > 0
                doc = response_body["results"][0]
                question = mongodb.UnrecordedQuestions.find_one({"_id": bson.ObjectId(doc["id"])})
                if lower is not None:
                    assert lower <= question["recDifficulty"]
                if upper is not None:
                    assert question["recDifficulty"] <= upper

    # Same as test_any_random, but for each difficulty
    def test_difficulty_random(self, client, difficulties_questions, difficulty_limits):
        max_attempts = self.RANDOM_TRIALS
        for i in range(len(difficulty_limits)):
            attempts = 0
            response = client.get(self.ROUTE, query_string={"difficultyType": i})
            previous_response_body = response.get_json()
            while attempts < max_attempts:
                response = client.get(self.ROUTE, query_string={"difficultyType": i})
                response_body = response.get_json()
                if response_body != previous_response_body:
                    break
                attempts += 1
            assert attempts < max_attempts

    # Test Case: Getting a batch of documents from a collection
    def test_batch(self, client, question_batch):
        required_response_fields = ["id", "transcript"]
        response = client.get(self.ROUTE, query_string={"batchSize": self.BATCH_SIZE})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "results" in response_body
        assert len(response_body["results"]) == self.BATCH_SIZE
        for doc in response_body["results"]:
            for field in required_response_fields:
                assert field in doc

    # Test Case: Attempting to get a batch of documents larger than the size of the collection
    def test_batch_lesser(self, client, question_batch_lesser):
        response = client.get(self.ROUTE, query_string={"batchSize": self.BATCH_SIZE})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "results" in response_body
        assert len(response_body["results"]) < self.BATCH_SIZE

    # Same as test_any_random, but for a batch of questions
    def test_batch_random(self, client, question_batch_random):
        max_attempts = self.RANDOM_TRIALS

        attempts = 0
        response = client.get(self.ROUTE, query_string={"batchSize": self.BATCH_SIZE})
        previous_response_body = response.get_json()
        while attempts < max_attempts:
            response = client.get(self.ROUTE, query_string={"batchSize": self.BATCH_SIZE})
            response_body = response.get_json()
            if response_body != previous_response_body:
                break
            attempts += 1
        assert attempts < max_attempts

    # Test Case: Difficulty and batch size parameters combined
    def test_difficulty_batch(self, client, mongodb, difficulties_question, difficulty_limits):
        for i in range(0, self.DIFFICULTY_TRIALS):
            for j, limit in enumerate(difficulty_limits):
                lower = difficulty_limits[j - 1] + 1 if j > 0 else None
                upper = limit
                response = client.get(self.ROUTE, query_string={"difficultyType": j, "batchSize": self.BATCH_SIZE})
                assert match_status(HTTPStatus.OK, response.status)
                response_body = response.get_json()
                assert "results" in response_body and len(response_body["results"]) > 0
                for doc in response_body["results"]:
                    question = mongodb.UnrecordedQuestions.find_one({"_id": bson.ObjectId(doc["id"])})
                    if lower is not None:
                        assert lower <= question["recDifficulty"]
                    if upper is not None:
                        assert question["recDifficulty"] <= upper

    # Difficulty and batch size parameters with randomization test applied
    def test_difficulty_batch_random(self, client, difficulties_question_batch_random, difficulty_limits):
        max_attempts = self.RANDOM_TRIALS
        for i in range(len(difficulty_limits)):
            attempts = 0
            response = client.get(self.ROUTE, query_string={"batchSize": self.BATCH_SIZE, "difficultyType": i})
            previous_response_body = response.get_json()
            while attempts < max_attempts:
                response = client.get(self.ROUTE, query_string={"batchSize": self.BATCH_SIZE, "difficultyType": i})
                response_body = response.get_json()
                if response_body != previous_response_body:
                    break
                attempts += 1
            assert attempts < max_attempts


@pytest.mark.usefixtures("client", "mongodb")
class TestGetUnprocAudio:
    ROUTE = "/audio/unprocessed/"

    @pytest.fixture
    def unrec_question(self, mongodb):
        question_result = mongodb.UnrecordedQuestions.insert_one({"transcript": "Foo"})
        yield question_result.inserted_id
        mongodb.UnrecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def rec_question(self, mongodb):
        question_result = mongodb.RecordedQuestions.insert_one({
            "transcript": "Foo",
            "recordings": [generate_audio_id()]
        })
        yield question_result.inserted_id
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def doc_setup_normal(self, mongodb, unrec_question, rec_question):
        audio_docs = [
            {
                "_id": generate_audio_id(),
                "questionId": unrec_question
            },
            {
                "_id": generate_audio_id(),
                "questionId": rec_question
            }
        ]
        audio_results = mongodb.UnprocessedAudio.insert_many(audio_docs)
        yield
        mongodb.UnprocessedAudio.delete_many({"_id": {"$in": audio_results.inserted_ids}})

    @pytest.fixture
    def doc_setup_admin(self, mongodb, unrec_question):
        audio_result = mongodb.UnprocessedAudio.insert_one({
            "_id": generate_audio_id(),
            "questionId": unrec_question,
            "diarMetadata": "detect_num_speakers=False, max_num_speakers=3"
        })
        yield
        mongodb.UnprocessedAudio.delete_one({"_id": audio_result.inserted_id})

    # Test Case: One audio document submitted by a normal user
    def test_normal(self, client, doc_setup_normal):
        required_doc_fields = ["_id", "transcript"]
        response = client.get(self.ROUTE)
        response_body = response.get_json()
        assert match_status(HTTPStatus.OK, response.status)
        assert "results" in response_body
        for doc in response_body.get("results"):
            for field in required_doc_fields:
                assert field in doc

    # Test Case: One audio document submitted by an administrator
    def test_admin(self, client, doc_setup_admin):
        required_doc_fields = ["_id", "transcript", "diarMetadata"]
        response = client.get(self.ROUTE)
        response_body = response.get_json()
        assert match_status(HTTPStatus.OK, response.status)
        assert "results" in response_body
        for doc in response_body.get("results"):
            for field in required_doc_fields:
                assert field in doc


@pytest.mark.usefixtures("client", "mongodb")
@pytest.mark.skip(reason="not finished yet")
class TestProcessAudio:
    ROUTE = "/audio/processed"

    @pytest.fixture
    def unrec_question(self, mongodb):
        question_doc = {"transcript": "Foo"}
        result = mongodb.UnrecordedQuestions.insert_one(question_doc)
        question_doc["_id"] = result.inserted_id
        yield question_doc
        mongodb.UnrecordedQuestions.delete_one({"_id": result.inserted_id})
        mongodb.RecordedQuestions.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def user(self, mongodb):
        user_doc = {"recordedAudios": []}
        result = mongodb.Users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        yield user_doc
        mongodb.Users.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def unproc_audio_documents(self, mongodb, unrec_question, user):
        audio_doc = {
            "_id": generate_audio_id(),
            "questionId": unrec_question["_id"],
            "userId": user["_id"],
            "gentleVtt": "Foo"
        }

        audio_result = mongodb.UnprocessedAudio.insert_one(audio_doc)
        yield audio_result.inserted_id
        mongodb.UnprocessedAudio.delete_one({"_id": audio_result.inserted_id})
        mongodb.Audio.delete_one({"_id": audio_result.inserted_id})

    @pytest.fixture
    def update_batch(self, mongodb, unproc_audio_document):
        batch = [
            {
                "_id": unproc_audio_document,
                "vtt": "Bar",
                "score": {"wer": 1.0, "mer": 1.0, "wil": 1.0}
            }
        ]
        yield batch
        mongodb.Audio.delete_many({"_id": unproc_audio_document})

    # Test Case: Sending a batch of update arguments, each with a different issue:
    #   1. No audio ID
    #   2. An invalid audio ID
    #   3. A valid ID of an audio document with one of the following issues:
    #     i. No question ID
    #     ii. An invalid question ID
    #     iii. No user ID
    #     iv. An invalid user ID
    def test_corrupt(self, client, update_batch):
        test_values = {
            "errors": [
                {"type": "bad_args", "reason": "undefined_gfile_id"},
                {"type": "bad_args", "reason": "invalid_gfile_id"},
                {"type": "internal_error", "reason": "undefined_question_id"},
                {"type": "internal_error", "reason": "question_update_failure"},
                {"type": "internal_error", "reason": "undefined_user_id"},
                {"type": "internal_error", "reason": "user_update_failure"}
            ]
        }
        response = client.post(self.ROUTE, json={"arguments": update_batch})
        response_body = response.get_json()
        for error in test_values["errors"]:
            assert error in response_body["errors"]


@pytest.mark.usefixtures("client", "mongodb", "google_drive", "input_dir")
class TestUploadRec:
    ROUTE = "/upload"

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
    def upload_cleanup(self, mongodb, google_drive):
        yield
        audio_cursor = mongodb.UnprocessedAudio.find(None, {"_id": 1})
        for audio_doc in audio_cursor:
            fid = audio_doc["_id"]
            google_drive.drive.files().delete(fileId=fid).execute()
        mongodb.UnprocessedAudio.delete_many({"_id": {"$exists": True}})

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

    # Test Case: Submitting a recording with exact accuracy.
    def test_exact(self, client, mongodb, exact_data, upload_cleanup):
        doc_required_fields = ["gentleVtt", "questionId", "userId"]
        response = client.post(self.ROUTE, data=exact_data, content_type='multipart/form-data')
        response_body = response.get_json()
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        assert response_body.get("prescreenSuccessful")
        audio_doc = mongodb.UnprocessedAudio.find_one()
        for field in doc_required_fields:
            assert field in audio_doc

    # Test Case: Submitting a recording as an administrator.
    def test_admin(self, mongodb, client, admin_data, upload_cleanup):
        doc_required_fields = ["gentleVtt", "questionId", "userId", "diarMetadata"]
        response = client.post(self.ROUTE, data=admin_data, content_type='multipart/form-data')
        response_body = response.get_json()
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        assert response_body.get("prescreenSuccessful")
        audio_doc = mongodb.UnprocessedAudio.find_one()
        for field in doc_required_fields:
            assert field in audio_doc
