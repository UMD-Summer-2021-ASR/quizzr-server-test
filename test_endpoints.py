import os
import random
from copy import deepcopy
from datetime import datetime
from http import HTTPStatus
import logging

import bson
import pytest
from openapi_schema_validator import validate

from testutil import match_status, generate_audio_id

logger = logging.getLogger(__name__)
# For testing cases that the server is designed to handle on a regular basis.


@pytest.mark.usefixtures("mongodb", "client")
class TestCheckAnswer:
    ROUTE = "/answer"
    CORRECT_ANSWER = "Eiffel Tower"
    CORRECT_ANSWER_INSERTIONS = "The " + CORRECT_ANSWER + " of Paris"
    CORRECT_ANSWER_TYPOS = "riffle topwer"
    INCORRECT_ANSWER = "Empire State Building"

    @pytest.fixture
    def question_id(self, mongodb):
        question_result = mongodb.RecordedQuestions.insert_one({"answer": self.CORRECT_ANSWER})
        yield question_result.inserted_id
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})

    # Test Case: The user provides a correct answer
    def test_correct_exact(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.CORRECT_ANSWER})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert response_body["correct"]

    # Test Case: The user provides a correct answer, along with some extra words
    def test_correct_extra(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.CORRECT_ANSWER_INSERTIONS})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert response_body["correct"]

    # Test Case: The user provides a correct answer with some typos.
    def test_correct_typos(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.CORRECT_ANSWER_TYPOS})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert response_body["correct"]

    # Test Case: The user provides an incorrect answer
    def test_incorrect(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.INCORRECT_ANSWER})
        assert match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert not response_body["correct"]


@pytest.mark.usefixtures("blob_file")
class TestGetFile:
    ROUTE = "/audio"

    @pytest.fixture
    def full_route(self, blob_file):
        return "/".join([self.ROUTE, "normal", blob_file])

    def test_download(self, client, full_route):
        response = client.get(full_route)
        assert match_status(HTTPStatus.OK, response.status)


@pytest.mark.usefixtures("mongodb", "client", "flask_app")
class TestGetRec:
    ROUTE = "/question"

    @pytest.fixture
    def doc_setup(self, mongodb, flask_app):
        num_docs = 5
        audio_docs = []
        for i in range(1, num_docs + 1):
            audio_docs.append({
                "_id": generate_audio_id(),
                "vtt": "The quick brown fox jumps over the lazy dog.",
                "gentleVtt": "This is a dummy VTT.",
                "version": flask_app.config["VERSION"],
                "score": {
                    "wer": i,
                    "mer": i,
                    "wil": i
                }
            })
        test_audio_doc = audio_docs[0]
        random.shuffle(audio_docs)
        audio_results = mongodb.Audio.insert_many(audio_docs)
        question_result = mongodb.RecordedQuestions.insert_one({
            "recordings": [{"id": rec_id, "recType": "normal"} for rec_id in audio_results.inserted_ids]
        })
        yield test_audio_doc
        mongodb.Audio.delete_many({"_id": {"$in": audio_results.inserted_ids}})
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})

    # Test Case: No difficulty specified
    def test_any(self, client, doc_setup):
        required_response_fields = ["_id", "vtt", "gentleVtt", "qid"]
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

    ROUTE = "/question/unrec"

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
    ROUTE = "/audio"

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
class TestProcessAudio:
    ROUTE = "/audio"

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
    def unproc_audio_document(self, mongodb, unrec_question, user, flask_app):
        audio_doc = {
            "_id": generate_audio_id(),
            "questionId": unrec_question["_id"],
            "userId": user["_id"],
            "gentleVtt": "Foo",
            "recType": "normal",
            "version": flask_app.config["VERSION"]
        }

        audio_result = mongodb.UnprocessedAudio.insert_one(audio_doc)
        yield audio_result.inserted_id
        mongodb.UnprocessedAudio.delete_one({"_id": audio_result.inserted_id})

    @pytest.fixture
    def update_batch(self, mongodb, unrec_question, unproc_audio_document):
        batch = [
            {
                "_id": unproc_audio_document,
                "vtt": "Bar",
                "score": {"wer": 1.0, "mer": 1.0, "wil": 1.0},
                "transcript": unrec_question["transcript"],
                "batchNumber": str(datetime.now()),
                "metadata": "detect_num_speakers=False, max_num_speakers=1"
            }
        ]
        yield batch
        mongodb.Audio.delete_one({"_id": unproc_audio_document})

    # Test Case: Send a single update document with the required fields.
    def test_single(self, client, mongodb, update_batch, unproc_audio_document, unrec_question, user):
        doc_required_fields = ["_id", "version", "questionId", "userId", "transcript", "vtt", "score", "batchNumber",
                               "metadata", "gentleVtt", "recType"]
        response = client.patch(self.ROUTE, json={"arguments": update_batch})
        response_body = response.get_json()
        assert response_body["total"] == len(update_batch)
        assert response_body["successes"] == response_body["total"]

        audio_doc = mongodb.Audio.find_one({"_id": unproc_audio_document})
        for field in doc_required_fields:
            assert field in audio_doc
        question_doc = mongodb.RecordedQuestions.find_one({"_id": unrec_question["_id"]})
        recording = question_doc["recordings"][0]
        assert recording["id"] == unproc_audio_document
        assert recording["recType"] == "normal"


@pytest.mark.usefixtures("client", "mongodb", "firebase_bucket", "input_dir", "dev_uid")
class TestUploadRec:
    ROUTE = "/audio"
    CONTENT_TYPE = "multipart/form-data"

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
    def user_id(self, mongodb, dev_uid):
        user_result = mongodb.Users.insert_one({"_id": dev_uid, "recordedAudios": []})
        yield user_result.inserted_id
        mongodb.Users.delete_one({"_id": user_result.inserted_id})

    @pytest.fixture
    def upload_cleanup(self, mongodb, firebase_bucket, flask_app):
        yield
        audio_cursor = mongodb.UnprocessedAudio.find(None, {"_id": 1})
        for audio_doc in audio_cursor:
            fid = audio_doc["_id"]
            firebase_bucket.blob("/".join([flask_app.config["BLOB_ROOT"], "normal", fid])).delete()
        mongodb.UnprocessedAudio.delete_many({"_id": {"$exists": True}})
        audio_cursor = mongodb.Audio.find(None, {"_id": 1})
        for audio_doc in audio_cursor:
            fid = audio_doc["_id"]
            firebase_bucket.blob("/".join([flask_app.config["BLOB_ROOT"], "buzz", fid])).delete()
        mongodb.Audio.delete_many({"_id": {"$exists": True}})

    @pytest.fixture
    def exact_data(self, mongodb, input_dir, unrec_qid):
        audio_path = os.path.join(input_dir, "exact.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"qid": unrec_qid, "audio": audio, "recType": "normal"}
        audio.close()

    @pytest.fixture
    def mismatch_data(self, mongodb, input_dir, unrec_qid):
        audio_path = os.path.join(input_dir, "mismatch.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"qid": unrec_qid, "audio": audio, "recType": "normal"}
        audio.close()

    @pytest.fixture
    def bad_env_data(self, mongodb, input_dir, unrec_qid):
        audio_path = os.path.join(input_dir, "bad_env.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"qid": unrec_qid, "audio": audio, "recType": "normal"}
        audio.close()

    @pytest.fixture
    def admin_data(self, exact_data):
        data = exact_data.copy()
        data["diarMetadata"] = "detect_num_speakers=False, max_num_speakers=3"
        return data

    @pytest.fixture
    def buzz_data(self, mongodb, input_dir):
        audio_path = os.path.join(input_dir, "buzz.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"audio": audio, "recType": "buzz"}
        audio.close()

    # Test Case: Submitting a recording that should be guaranteed to pass the pre-screening.
    def test_success(self, client, mongodb, exact_data, upload_cleanup, user_id):
        doc_required_fields = ["gentleVtt", "questionId", "userId", "recType"]
        response = client.post(self.ROUTE, data=exact_data, content_type=self.CONTENT_TYPE)
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        assert response_body.get("prescreenSuccessful")
        audio_doc = mongodb.UnprocessedAudio.find_one()
        for field in doc_required_fields:
            assert field in audio_doc

    # Test Case: Submitting a recording with audio distorted by environmental noise.
    def test_bad_env(self, client, mongodb, bad_env_data, upload_cleanup, user_id):
        response = client.post(self.ROUTE, data=bad_env_data, content_type=self.CONTENT_TYPE)
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        logger.debug(f"response_body = {response_body}")
        assert response_body.get("prescreenSuccessful")

    # Test Case: Submitting a recording of the speaker reading a paragraph from the "Lorem ipsum" Wikipedia article.
    # Source: https://en.wikipedia.org/wiki/Lorem_ipsum
    def test_mismatch(self, client, mongodb, mismatch_data, upload_cleanup, user_id):
        response = client.post(self.ROUTE, data=mismatch_data, content_type=self.CONTENT_TYPE)
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        logger.debug(f"response_body = {response_body}")
        assert not response_body.get("prescreenSuccessful")

    # Test Case: Submitting a recording as an administrator.
    def test_admin(self, mongodb, client, admin_data, upload_cleanup, user_id):
        doc_required_fields = ["gentleVtt", "questionId", "userId", "recType", "diarMetadata"]
        response = client.post(self.ROUTE, data=admin_data, content_type=self.CONTENT_TYPE)
        response_body = response.get_json()
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        assert response_body.get("prescreenSuccessful")
        logger.debug(f"response_body = {response_body}")
        audio_doc = mongodb.UnprocessedAudio.find_one()
        assert audio_doc
        for field in doc_required_fields:
            assert field in audio_doc
        assert audio_doc["recType"] == "normal"

    # Test Case: Submitting a buzz recording.
    def test_buzz(self, mongodb, client, buzz_data, upload_cleanup, user_id):
        doc_required_fields = ["userId", "recType"]
        response = client.post(self.ROUTE, data=buzz_data, content_type=self.CONTENT_TYPE)
        response_body = response.get_json()
        logger.debug(f"response_body = {response_body}")
        assert match_status(HTTPStatus.ACCEPTED, response.status)
        assert response_body.get("prescreenSuccessful")

        audio_doc = mongodb.Audio.find_one()
        assert audio_doc
        for field in doc_required_fields:
            assert field in audio_doc
        assert audio_doc["recType"] == "buzz"

        user_doc = mongodb.Users.find_one({"_id": user_id})
        rec = user_doc["recordedAudios"][0]
        assert rec["id"] == audio_doc["_id"]
        assert rec["recType"] == "buzz"


@pytest.mark.usefixtures("client", "mongodb", "api_spec", "dev_uid")
class TestOwnProfile:
    ROUTE = "/profile"

    @pytest.fixture
    def profile_args(self, mongodb):
        in_profile = {
            "pfp": [1, 2, 3],
            "username": "Foo"
        }
        yield in_profile
        mongodb.Users.delete_one(in_profile)

    @pytest.fixture
    def profile_update_args(self):
        return {
            "pfp": [4, 5, 6],
            "username": "Bar",
            "usernameSpecs": "colored"
        }

    @pytest.fixture
    def user_profile(self, mongodb, api_spec, dev_uid):
        user_schema = api_spec.api["components"]["schemas"]["User"]
        profile = deepcopy(user_schema["examples"][0])
        profile["_id"] = dev_uid
        result = mongodb.Users.insert_one(profile)
        yield profile
        mongodb.Users.delete_one({"_id": result.inserted_id})

    def test_create(self, client, mongodb, profile_args, dev_uid, api_spec):
        response = client.post(self.ROUTE, json=profile_args)
        assert match_status(HTTPStatus.CREATED, response.status)
        profile = mongodb.Users.find_one({"_id": dev_uid})
        assert profile
        validate(profile, api_spec.get_schema("User", resolve_references=True))

    def test_get(self, client, user_profile):
        required_fields = [
            "pfp",
            "username",
            "usernameSpecs",
            "rating",
            "totalQuestionsPlayed",
            "totalGames",
            "coins",
            "coinsCumulative",
            "activityOverview",
            "recordedAudios",
            "permLevel"
        ]
        response = client.get(self.ROUTE)
        assert match_status(HTTPStatus.OK, response.status)
        profile = response.get_json()
        assert profile
        for field in required_fields:
            assert field in profile

    def test_update(self, client, mongodb, user_profile, profile_update_args):
        response = client.patch(self.ROUTE, json=profile_update_args)
        assert match_status(HTTPStatus.OK, response.status)
        new_profile = {**user_profile, **profile_update_args}  # Merge two dictionaries without modifying either one.
        other_profile = mongodb.Users.find_one({"_id": new_profile["_id"]})
        assert new_profile == other_profile

    def test_delete(self, client, mongodb, user_profile):
        response = client.delete(self.ROUTE)
        assert match_status(HTTPStatus.OK, response.status)
        assert not mongodb.Users.find_one({"_id": user_profile["_id"]})


@pytest.mark.usefixtures("client", "mongodb", "api_spec", "dev_uid")
class TestOtherProfile:
    ROUTE = "/profile"

    @pytest.fixture
    def profile_args(self, mongodb):
        in_profile = {
            "pfp": [1, 2, 3],
            "username": "Foo"
        }
        yield in_profile
        mongodb.Users.delete_one(in_profile)

    @pytest.fixture
    def profile_update_args(self):
        return {
            "pfp": [4, 5, 6],
            "username": "Bar",
            "usernameSpecs": "colored"
        }

    @pytest.fixture
    def admin_profile(self, mongodb, api_spec, dev_uid):
        user_schema = api_spec.api["components"]["schemas"]["User"]
        profile = deepcopy(user_schema["examples"][0])
        profile.update({
            "_id": dev_uid,
            "username": "admin",
            "permLevel": "admin"
        })
        result = mongodb.Users.insert_one(profile)
        yield profile
        mongodb.Users.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def other_profile(self, mongodb, api_spec, dev_uid):
        user_schema = api_spec.api["components"]["schemas"]["User"]
        profile = user_schema["examples"][0]
        result = mongodb.Users.insert_one(profile)
        yield profile
        mongodb.Users.delete_one({"_id": result.inserted_id})

    def test_get(self, client, other_profile, api_spec):
        full_route = "/".join([self.ROUTE, other_profile["username"]])
        response = client.get(full_route)
        assert match_status(HTTPStatus.OK, response.status)
        profile = response.get_json()
        for field in profile:
            assert field in other_profile
            assert profile[field] == other_profile[field]

    def test_update(self, client, mongodb, admin_profile, other_profile, profile_update_args):
        full_route = "/".join([self.ROUTE, other_profile["username"]])
        response = client.patch(full_route, json=profile_update_args)
        assert match_status(HTTPStatus.OK, response.status)
        new_profile = {**other_profile, **profile_update_args}  # Merge two dictionaries without modifying either one.
        actual_profile = mongodb.Users.find_one({"_id": new_profile["_id"]})
        assert new_profile == actual_profile

    def test_delete(self, client, mongodb, admin_profile, other_profile):
        full_route = "/".join([self.ROUTE, other_profile["username"]])
        response = client.delete(full_route)
        assert match_status(HTTPStatus.OK, response.status)
        assert not mongodb.Users.find_one({"_id": other_profile["_id"]})
