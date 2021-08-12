import os
import random
from copy import deepcopy
from datetime import datetime
from http import HTTPStatus
import logging

import bson
import pytest
from openapi_schema_validator import validate

import testutil

logger = logging.getLogger(__name__)
# TODO: Replace ROUTE class attributes with pytest fixtures that use QuizzrAPISpec.path_for()
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
        qb_id = 1234
        question_result = mongodb.RecordedQuestions.insert_one({"answer": self.CORRECT_ANSWER, "qb_id": qb_id})
        yield qb_id
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})

    # Test Case: The user provides a correct answer
    def test_correct_exact(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.CORRECT_ANSWER})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert response_body["correct"]

    # Test Case: The user provides a correct answer, along with some extra words
    def test_correct_extra(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.CORRECT_ANSWER_INSERTIONS})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert response_body["correct"]

    # Test Case: The user provides a correct answer with some typos.
    def test_correct_typos(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.CORRECT_ANSWER_TYPOS})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert response_body["correct"]

    # Test Case: The user provides an incorrect answer
    def test_incorrect(self, client, question_id):
        response = client.get(self.ROUTE, query_string={"qid": question_id, "a": self.INCORRECT_ANSWER})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "correct" in response_body
        assert not response_body["correct"]


@pytest.mark.usefixtures("blob_file", "client")
class TestGetFile:
    ROUTE = "/audio"

    @pytest.fixture
    def full_route(self, blob_file):
        return "/".join([self.ROUTE, "normal", blob_file])

    def test_download(self, client, full_route):
        response = client.get(full_route)
        assert testutil.match_status(HTTPStatus.OK, response.status)


@pytest.mark.usefixtures("client", "mongodb", "api_spec")
class TestGetLeaderboard:
    ROUTE = "/leaderboard"

    @pytest.fixture
    def users(self, mongodb, api_spec):
        user_docs = []
        for i in range(5):
            profile = api_spec.get_schema_stub("User")
            profile.update({
                "_id": testutil.generate_uid(),
                "username": f"User{i + 1}",
                "ratings": {
                    "all": i + 1,
                    "literature": i + 1,
                    "mathematics": 5 - i
                }
            })
            user_docs.append(profile)
        random.shuffle(user_docs)

        results = mongodb.Users.insert_many(user_docs)
        yield
        mongodb.Users.delete_many({"_id": {"$in": results.inserted_ids}})

    @pytest.mark.parametrize("category", [("all",), ("literature",), ("mathematics",)])
    def test_get(self, client, mongodb, category):
        response = client.get(self.ROUTE, query_string={"category": category})
        assert response.status_code == HTTPStatus.OK
        response_body = response.get_json()
        prev_rating = None
        for profile in response_body["results"]:
            live_profile = mongodb.Users.find_one({"username": profile["username"]}, {"ratings": 1})
            rating = live_profile["ratings"][category]
            if prev_rating is not None:
                assert rating < prev_rating
            prev_rating = rating


@pytest.mark.usefixtures("mongodb", "client", "flask_app", "api_spec")
class TestGetRec:
    ROUTE = "/question"

    @pytest.fixture(scope="session")
    def path_op_pair(self, api_spec):
        return api_spec.path_for("pick_game_question")

    @pytest.fixture(scope="session")
    def schema(self, path_op_pair, api_spec):
        op_content = api_spec.api["paths"][path_op_pair[0]][path_op_pair[1]]
        schema = op_content["responses"][str(int(HTTPStatus.OK))]["content"]["application/json"]["schema"]
        return api_spec.build_schema(schema)

    @pytest.fixture
    def doc_setup(self, mongodb, flask_app):
        num_docs = 5
        user_id = testutil.generate_uid()
        mongodb.Users.insert_one({"_id": user_id, "recordedAudios": []})
        audio_ids = []
        audio_docs = []
        for i in range(num_docs):
            audio_id = testutil.generate_audio_id()
            audio_ids.append(audio_id)
            audio_docs.append({
                "_id": audio_id,
                "qb_id": 0,
                "vtt": "The quick brown fox jumps over the lazy dog.",
                "gentleVtt": "This is a dummy VTT.",
                "version": flask_app.config["VERSION"],
                "score": {
                    "wer": i + 1,
                    "mer": i + 1,
                    "wil": i + 1
                },
                "userId": user_id
            })

        question_result = mongodb.RecordedQuestions.insert_one({
            "qb_id": 0,
            "transcript": str(bson.ObjectId()),
            "recDifficulty": 0,
            "answer": "Foo",
            "category": "unknown",
            "recordings": [{"id": rec_id, "recType": "normal"} for rec_id in audio_ids]
        })

        test_audio_doc = audio_docs[0]
        random.shuffle(audio_docs)
        audio_results = mongodb.Audio.insert_many(audio_docs)
        yield test_audio_doc
        mongodb.Audio.delete_many({"_id": {"$in": audio_results.inserted_ids}})
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})
        mongodb.Users.delete_one({"_id": user_id})

    @pytest.fixture
    def doc_setup_segmented(self, mongodb, flask_app):
        num_docs = 5
        num_sentences = 5
        test_audio_docs = []
        inserted_audio_ids = []
        inserted_question_ids = []
        user_ids = [testutil.generate_uid(), testutil.generate_uid()]
        mongodb.Users.insert_many([
            {"_id": user_ids[0], "recordedAudios": []},
            {"_id": user_ids[1], "recordedAudios": []}
        ])
        for i in range(num_sentences):
            audio_ids = []
            audio_docs = []
            for j in range(num_docs):
                audio_id = testutil.generate_audio_id()
                audio_ids.append(audio_id)
                audio_docs.append({
                    "_id": audio_id,
                    "sentenceId": i,
                    "qb_id": 0,
                    "vtt": "The quick brown fox jumps over the lazy dog.",
                    "gentleVtt": "This is a dummy VTT.",
                    "version": flask_app.config["VERSION"],
                    "score": {
                        "wer": (num_sentences - i) + j + 1,
                        "mer": (num_sentences - i) + j + 1,
                        "wil": (num_sentences - i) + j + 1
                    },
                    "userId": user_ids[0]
                })
                audio_id = testutil.generate_audio_id()
                audio_ids.append(audio_id)
                audio_docs.append({
                    "_id": audio_id,
                    "sentenceId": i,
                    "qb_id": 0,
                    "vtt": "The quick brown fox jumps over the lazy dog.",
                    "gentleVtt": "This is a dummy VTT.",
                    "version": flask_app.config["VERSION"],
                    "score": {
                        "wer": i + j + 1,
                        "mer": i + j + 1,
                        "wil": i + j + 1
                    },
                    "userId": user_ids[1]
                })

            question_result = mongodb.RecordedQuestions.insert_one({
                "qb_id": 0,
                "sentenceId": i,
                "transcript": str(bson.ObjectId()),
                "recDifficulty": 0,
                "answer": "Foo",
                "category": "unknown",
                "recordings": [{"id": rec_id, "recType": "normal"} for rec_id in audio_ids]
            })

            test_audio_docs.append(audio_docs[0])
            random.shuffle(audio_docs)
            audio_results = mongodb.Audio.insert_many(audio_docs)
            inserted_audio_ids += audio_results.inserted_ids
            inserted_question_ids.append(question_result.inserted_id)
        yield test_audio_docs
        mongodb.Audio.delete_many({"_id": {"$in": inserted_audio_ids}})
        mongodb.RecordedQuestions.delete_many({"_id": {"$in": inserted_question_ids}})
        mongodb.Users.delete_many({"_id": {"$in": user_ids}})

    @pytest.fixture
    def doc_setup_categorical(self, mongodb, flask_app):
        question_docs = []
        audio_docs = []
        categories = ["literature", "history", "mathematics", "science"]
        for i, cat in enumerate(categories):
            audio_id = testutil.generate_audio_id()
            question_docs.append({
                "qb_id": i,
                "transcript": str(bson.ObjectId()),
                "recDifficulty": 0,
                "answer": "Foo",
                "category": cat,
                "recordings": [{"id": audio_id, "recType": "normal"}]
            })
            audio_docs.append({
                "_id": audio_id,
                "qb_id": i,
                "vtt": "The quick brown fox jumps over the lazy dog.",
                "gentleVtt": "This is a dummy VTT.",
                "version": flask_app.config["VERSION"],
                "score": {
                    "wer": i + 1,
                    "mer": i + 1,
                    "wil": i + 1
                },
                "userId": testutil.generate_uid()
            })
        question_results = mongodb.RecordedQuestions.insert_many(question_docs)
        audio_results = mongodb.Audio.insert_many(audio_docs)
        yield
        mongodb.RecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})
        mongodb.Audio.delete_many({"_id": {"$in": audio_results.inserted_ids}})

    # Test Case: Not segmented
    def test_whole(self, path_op_pair, client, mongodb, doc_setup, schema):
        response = client.get(self.ROUTE)
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        validate(response_body, schema)
        question = response_body["results"][0]
        audio = question["audio"][0]
        doc = mongodb.Audio.find_one({"_id": audio["id"]})
        assert doc == doc_setup

    # Test Case: Segmented
    def test_segmented(self, client, mongodb, doc_setup_segmented, schema):
        response = client.get(self.ROUTE)
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        validate(response_body, schema)
        for question in response_body["results"]:
            expected_uid = None
            for audio in question["audio"]:
                doc = mongodb.Audio.find_one({"_id": audio["id"]})
                uid = doc["userId"]
                if not expected_uid:
                    expected_uid = uid
                else:
                    assert expected_uid == uid

    @pytest.mark.parametrize("categories", [
        (["literature"],),
        (["literature", "history"],),
        (["literature", "history", "mathematics", "science"],)
    ])
    def test_categorical(self, client, mongodb, doc_setup_categorical, schema, categories):
        response = client.get(self.ROUTE, query_string={"category": categories})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        validate(response_body, schema)
        for question in response_body["results"]:
            assert question["category"] in categories


@pytest.mark.usefixtures("client", "flask_app", "mongodb")
class TestGetTranscript:
    DIFFICULTY_TRIALS = 5
    RANDOM_TRIALS = 5
    MIN_DOCS_RANDOM = 3
    BATCH_SIZE = 3
    NUM_SENTENCES = 5

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
            for j in range(0, self.NUM_SENTENCES):
                question_docs.append({"qb_id": d, "sentenceId": j, "transcript": "Foo", "recDifficulty": d})

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def difficulties_questions(self, mongodb, difficulty_bounds):
        question_docs = []
        for i in range(difficulty_bounds[0], difficulty_bounds[1] + 1):
            for j in range(0, self.NUM_SENTENCES):
                question_docs.append({
                    "qb_id": i,
                    "sentenceId": j,
                    "transcript": str(bson.ObjectId()),  # Equivalence buster
                    "recDifficulty": i
                })

        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def question_batch(self, mongodb):
        question_docs = []
        for i in range(0, self.BATCH_SIZE + 1):
            for j in range(0, self.NUM_SENTENCES):
                question_docs.append({"qb_id": i, "sentenceId": j, "transcript": "Foo"})

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

    @pytest.fixture(scope="class")
    def questions(self, mongodb, rec_difficulties):
        sentence_docs = []
        qb_id = 0
        for d in rec_difficulties:
            for i in range(0, self.BATCH_SIZE):
                for j in range(0, self.NUM_SENTENCES):
                    sentence_docs.append({
                        "qb_id": qb_id,
                        "sentenceId": j,
                        "transcript": str(bson.ObjectId()),  # Equivalence buster
                        "recDifficulty": d
                    })
                    qb_id += 1

        question_results = mongodb.UnrecordedQuestions.insert_many(sentence_docs)
        yield question_results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    # Test Case: No difficulty specified
    def test_any(self, client, questions):
        required_response_fields = ["id", "sentenceId", "transcript"]
        response = client.get(self.ROUTE)
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "results" in response_body and len(response_body["results"]) > 0
        doc = response_body["results"][0]
        for field in required_response_fields:
            assert field in doc

    # Test to see if the document retrieved is not always the same.
    def test_any_random(self, client, questions):
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
    def test_difficulty(self, client, mongodb, questions, difficulty_limits):
        for i in range(0, self.DIFFICULTY_TRIALS):
            for j, limit in enumerate(difficulty_limits):
                lower = difficulty_limits[j - 1] + 1 if j > 0 else None
                upper = limit
                response = client.get(self.ROUTE, query_string={"difficultyType": j})
                assert testutil.match_status(HTTPStatus.OK, response.status)
                response_body = response.get_json()
                assert "results" in response_body and len(response_body["results"]) > 0
                doc = response_body["results"][0]
                question = mongodb.UnrecordedQuestions.find_one({"qb_id": doc["id"]})
                if lower is not None:
                    assert lower <= question["recDifficulty"]
                if upper is not None:
                    assert question["recDifficulty"] <= upper

    # Same as test_any_random, but for each difficulty
    def test_difficulty_random(self, client, questions, difficulty_limits):
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
    def test_batch(self, client, questions):
        required_response_fields = ["id", "sentenceId", "transcript"]
        response = client.get(self.ROUTE, query_string={"batchSize": self.BATCH_SIZE})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "results" in response_body
        assert len(response_body["results"]) == self.BATCH_SIZE
        for doc in response_body["results"]:
            for field in required_response_fields:
                assert field in doc

    # Test Case: Attempting to get a batch of documents larger than the size of the collection
    def test_batch_lesser(self, client, questions):
        response = client.get(self.ROUTE, query_string={"batchSize": len(questions) + 1})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert "results" in response_body
        assert len(response_body["results"]) <= len(questions)

    # Same as test_any_random, but for a batch of questions
    def test_batch_random(self, client, questions):
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
    def test_difficulty_batch(self, client, mongodb, questions, difficulty_limits):
        for i in range(0, self.DIFFICULTY_TRIALS):
            for j, limit in enumerate(difficulty_limits):
                lower = difficulty_limits[j - 1] + 1 if j > 0 else None
                upper = limit
                response = client.get(self.ROUTE, query_string={"difficultyType": j, "batchSize": self.BATCH_SIZE})
                assert testutil.match_status(HTTPStatus.OK, response.status)
                response_body = response.get_json()
                assert "results" in response_body and len(response_body["results"]) > 0
                for doc in response_body["results"]:
                    question = mongodb.UnrecordedQuestions.find_one({"qb_id": doc["id"]})
                    if lower is not None:
                        assert lower <= question["recDifficulty"]
                    if upper is not None:
                        assert question["recDifficulty"] <= upper

    # Difficulty and batch size parameters with randomization test applied
    def test_difficulty_batch_random(self, client, questions, difficulty_limits):
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
    NUM_SENTENCES = 5

    @pytest.fixture
    def unrec_question(self, mongodb):
        qb_id = 0
        question_result = mongodb.UnrecordedQuestions.insert_one({"qb_id": qb_id, "transcript": "Foo"})
        yield qb_id
        mongodb.UnrecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def unrec_question_segmented(self, mongodb):
        qb_id = 0
        question_docs = []
        ids = []
        for i in range(self.NUM_SENTENCES):
            question_docs.append({
                "qb_id": qb_id,
                "sentenceId": i,
                "transcript": str(bson.ObjectId())
            })
            ids.append((qb_id, i))
        question_results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def rec_question(self, mongodb):
        qb_id = 1
        question_result = mongodb.RecordedQuestions.insert_one({
            "qb_id": qb_id,
            "transcript": "Foo",
            "recordings": [testutil.generate_audio_id()]
        })
        yield qb_id
        mongodb.RecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def rec_question_segmented(self, mongodb):
        qb_id = 1
        question_docs = []
        ids = []
        for i in range(self.NUM_SENTENCES):
            question_docs.append({
                "qb_id": qb_id,
                "sentenceId": i,
                "transcript": str(bson.ObjectId()),
                "recordings": [testutil.generate_audio_id()]
            })
            ids.append((qb_id, i))
        question_results = mongodb.RecordedQuestions.insert_many(question_docs)
        yield ids
        mongodb.RecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    @pytest.fixture
    def doc_setup_normal(self, mongodb, unrec_question, rec_question):
        audio_docs = [
            {
                "_id": testutil.generate_audio_id(),
                "qb_id": unrec_question
            },
            {
                "_id": testutil.generate_audio_id(),
                "qb_id": rec_question
            }
        ]
        audio_results = mongodb.UnprocessedAudio.insert_many(audio_docs)
        yield
        mongodb.UnprocessedAudio.delete_many({"_id": {"$in": audio_results.inserted_ids}})

    @pytest.fixture
    def doc_setup_admin(self, mongodb, unrec_question):
        audio_result = mongodb.UnprocessedAudio.insert_one({
            "_id": testutil.generate_audio_id(),
            "qb_id": unrec_question,
            "diarMetadata": "detect_num_speakers=False, max_num_speakers=3"
        })
        yield
        mongodb.UnprocessedAudio.delete_one({"_id": audio_result.inserted_id})

    @pytest.fixture
    def doc_setup_segmented(self, mongodb, unrec_question_segmented, rec_question_segmented):
        audio_docs = []
        for qb_id, sentence_id in unrec_question_segmented:
            audio_docs.append({
                "_id": testutil.generate_audio_id(),
                "qb_id": qb_id,
                "sentenceId": sentence_id
            })
        for qb_id, sentence_id in rec_question_segmented:
            audio_docs.append({
                "_id": testutil.generate_audio_id(),
                "qb_id": qb_id,
                "sentenceId": sentence_id
            })
        audio_results = mongodb.UnprocessedAudio.insert_many(audio_docs)
        yield
        mongodb.UnprocessedAudio.delete_many({"_id": {"$in": audio_results.inserted_ids}})

    # Test Case: Two audio documents submitted by a normal user
    def test_normal(self, client, doc_setup_normal):
        required_doc_fields = ["_id", "transcript"]
        response = client.get(self.ROUTE)
        response_body = response.get_json()
        assert testutil.match_status(HTTPStatus.OK, response.status)
        assert "results" in response_body
        for doc in response_body.get("results"):
            for field in required_doc_fields:
                assert field in doc

    # Test Case: One audio document submitted by an administrator
    def test_admin(self, client, doc_setup_admin):
        required_doc_fields = ["_id", "transcript", "diarMetadata"]
        response = client.get(self.ROUTE)
        response_body = response.get_json()
        assert testutil.match_status(HTTPStatus.OK, response.status)
        assert "results" in response_body
        for doc in response_body.get("results"):
            for field in required_doc_fields:
                assert field in doc

    # Test Case: One audio document submitted by a normal user
    def test_segmented(self, client, doc_setup_segmented):
        required_doc_fields = ["_id", "transcript"]
        response = client.get(self.ROUTE)
        response_body = response.get_json()
        assert testutil.match_status(HTTPStatus.OK, response.status)
        assert "results" in response_body
        for doc in response_body.get("results"):
            for field in required_doc_fields:
                assert field in doc


@pytest.mark.usefixtures("client", "mongodb")
class TestProcessAudio:
    ROUTE = "/audio"

    @pytest.fixture
    def unrec_question(self, mongodb):
        question_doc = {"transcript": "Foo", "qb_id": 0, "sentenceId": 0}
        result = mongodb.UnrecordedQuestions.insert_one(question_doc)
        yield question_doc
        mongodb.UnrecordedQuestions.delete_one({"_id": result.inserted_id})
        mongodb.RecordedQuestions.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def user(self, mongodb):
        user_doc = {"_id": testutil.generate_uid(), "recordedAudios": []}
        result = mongodb.Users.insert_one(user_doc)
        yield user_doc
        mongodb.Users.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def unproc_audio_document_id(self, mongodb, unrec_question, user, flask_app):
        audio_doc = {
            "_id": testutil.generate_audio_id(),
            "qb_id": unrec_question["qb_id"],
            "sentenceId": unrec_question["sentenceId"],
            "userId": user["_id"],
            "gentleVtt": "Foo",
            "recType": "normal",
            "version": flask_app.config["VERSION"]
        }

        audio_result = mongodb.UnprocessedAudio.insert_one(audio_doc)
        yield audio_result.inserted_id
        mongodb.UnprocessedAudio.delete_one({"_id": audio_result.inserted_id})

    @pytest.fixture
    def update_batch(self, mongodb, unrec_question, unproc_audio_document_id):
        batch = [
            {
                "_id": unproc_audio_document_id,
                "vtt": "Bar",
                "score": {"wer": 1.0, "mer": 1.0, "wil": 1.0},
                "transcript": unrec_question["transcript"],
                "batchNumber": str(datetime.now()),
                "metadata": "detect_num_speakers=False, max_num_speakers=1"
            }
        ]
        yield batch
        mongodb.Audio.delete_one({"_id": unproc_audio_document_id})

    # Test Case: Send a single update document with the required fields.
    def test_single(self, client, mongodb, update_batch, unproc_audio_document_id, unrec_question, user):
        doc_required_fields = ["_id", "version", "qb_id", "sentenceId", "userId", "transcript", "vtt", "score",
                               "batchNumber", "metadata", "gentleVtt", "recType"]
        response = client.patch(self.ROUTE, json={"arguments": update_batch})
        response_body = response.get_json()
        assert response_body["total"] == len(update_batch)
        assert response_body["successes"] == response_body["total"]

        audio_doc = mongodb.Audio.find_one({"_id": unproc_audio_document_id})
        for field in doc_required_fields:
            assert field in audio_doc
        question_doc = mongodb.RecordedQuestions.find_one({
            "qb_id": unrec_question["qb_id"],
            "sentenceId": unrec_question["sentenceId"]
        })
        recording = question_doc["recordings"][0]
        assert recording["id"] == unproc_audio_document_id
        assert recording["recType"] == "normal"

        user_doc = mongodb.Users.find_one({"_id": user["_id"]})
        recording = user_doc["recordedAudios"][0]
        assert recording["id"] == unproc_audio_document_id
        assert recording["recType"] == "normal"


@pytest.mark.usefixtures("client", "mongodb", "socket_server_key")
class TestProcessGameResults:
    ROUTE = "/game_results"

    @pytest.fixture
    def users(self, mongodb):
        user_docs = [
            {
                "_id": testutil.generate_uid(),
                "username": "John Doe"
            },
            {
                "_id": testutil.generate_uid(),
                "username": "Jane Doe"
            },
            {
                "_id": testutil.generate_uid(),
                "username": "Johnson"
            }
        ]
        results = mongodb.Users.insert_many(user_docs)
        yield user_docs
        mongodb.Users.delete_many({"_id": {"$in": results.inserted_ids}})

    @pytest.fixture
    def user(self, mongodb):
        user_doc = {
            "_id": testutil.generate_uid(),
            "username": "John Doe"
        }
        result = mongodb.Users.insert_one(user_doc)
        yield user_doc
        mongodb.Users.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def update_args(self, user):
        return [
            {
                "mode": "casual",
                "category": "literature",
                "users": {
                    user["username"]: {
                        "questionStats": {
                            "played": 10,
                            "buzzed": 5,
                            "correct": 2,
                            "cumulativeProgressOnBuzz": {
                                "percentQuestionRead": 2.5,
                                "numSentences": 10
                            }
                        },
                        "finished": True,
                        "won": False
                    }
                }
            },
            {
                "mode": "casual",
                "category": "literature",
                "users": {
                    user["username"]: {
                        "questionStats": {
                            "played": 7,
                            "buzzed": 2,
                            "correct": 2,
                            "cumulativeProgressOnBuzz": {
                                "percentQuestionRead": 1.5,
                                "numSentences": 6
                            }
                        },
                        "finished": False,
                        "won": False
                    }
                }
            },
            {
                "mode": "casual",
                "category": "literature",
                "users": {
                    user["username"]: {
                        "questionStats": {
                            "played": 7,
                            "buzzed": 2,
                            "correct": 2,
                            "cumulativeProgressOnBuzz": {
                                "percentQuestionRead": 1.5,
                                "numSentences": 6
                            }
                        },
                        "finished": True,
                        "won": True
                    }
                }
            },
            {
                "mode": "casual",
                "category": "history",
                "users": {
                    user["username"]: {
                        "questionStats": {
                            "played": 7,
                            "buzzed": 2,
                            "correct": 2,
                            "cumulativeProgressOnBuzz": {
                                "percentQuestionRead": 1.5,
                                "numSentences": 6
                            }
                        },
                        "finished": True,
                        "won": True
                    }
                }
            },
            {
                "mode": "competitive",
                "category": "literature",
                "users": {
                    user["username"]: {
                        "questionStats": {
                            "played": 7,
                            "buzzed": 2,
                            "correct": 2,
                            "cumulativeProgressOnBuzz": {
                                "percentQuestionRead": 1.5,
                                "numSentences": 6
                            }
                        },
                        "finished": True,
                        "won": True
                    }
                }
            }
        ]

    @pytest.fixture
    def expected_results(self, user):
        stats_list = [
            {
                "casual": {
                    "questions": {
                        "played": {"all": 10, "literature": 10},
                        "buzzed": {"all": 5, "literature": 5},
                        "correct": {"all": 2, "literature": 2},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 2.5, "literature": 2.5},
                            "numSentences": {"all": 10, "literature": 10}
                        }
                    },
                    "game": {
                        "played": {"all": 1, "literature": 1},
                        "finished": {"all": 1, "literature": 1},
                        "won": {"all": 0, "literature": 0}
                    }
                }
            },
            {
                "casual": {
                    "questions": {
                        "played": {"all": 17, "literature": 17},
                        "buzzed": {"all": 7, "literature": 7},
                        "correct": {"all": 4, "literature": 4},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 4.0, "literature": 4.0},
                            "numSentences": {"all": 16, "literature": 16}
                        }
                    },
                    "game": {
                        "played": {"all": 2, "literature": 2},
                        "finished": {"all": 1, "literature": 1},
                        "won": {"all": 0, "literature": 0}
                    }
                }
            },
            {
                "casual": {
                    "questions": {
                        "played": {"all": 24, "literature": 24},
                        "buzzed": {"all": 9, "literature": 9},
                        "correct": {"all": 6, "literature": 6},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 5.5, "literature": 5.5},
                            "numSentences": {"all": 22, "literature": 22}
                        }
                    },
                    "game": {
                        "played": {"all": 3, "literature": 3},
                        "finished": {"all": 2, "literature": 2},
                        "won": {"all": 1, "literature": 1}
                    }
                }
            },
            {
                "casual": {
                    "questions": {
                        "played": {"all": 31, "literature": 24, "history": 7},
                        "buzzed": {"all": 11, "literature": 9, "history": 2},
                        "correct": {"all": 8, "literature": 6, "history": 2},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 7.0, "literature": 5.5, "history": 1.5},
                            "numSentences": {"all": 28, "literature": 22, "history": 6}
                        }
                    },
                    "game": {
                        "played": {"all": 4, "literature": 3, "history": 1},
                        "finished": {"all": 3, "literature": 2, "history": 1},
                        "won": {"all": 2, "literature": 1, "history": 1}
                    }
                }
            },
            {
                "casual": {
                    "questions": {
                        "played": {"all": 31, "literature": 24, "history": 7},
                        "buzzed": {"all": 11, "literature": 9, "history": 2},
                        "correct": {"all": 8, "literature": 6, "history": 2},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 7.0, "literature": 5.5, "history": 1.5},
                            "numSentences": {"all": 28, "literature": 22, "history": 6}
                        }
                    },
                    "game": {
                        "played": {"all": 4, "literature": 3, "history": 1},
                        "finished": {"all": 3, "literature": 2, "history": 1},
                        "won": {"all": 2, "literature": 1, "history": 1}
                    }
                },
                "competitive": {
                    "questions": {
                        "played": {"all": 7, "literature": 7},
                        "buzzed": {"all": 2, "literature": 2},
                        "correct": {"all": 2, "literature": 2},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 1.5, "literature": 1.5},
                            "numSentences": {"all": 6, "literature": 6}
                        }
                    },
                    "game": {
                        "played": {"all": 1, "literature": 1},
                        "finished": {"all": 1, "literature": 1},
                        "won": {"all": 1, "literature": 1}
                    }
                }
            }
        ]
        for stats in stats_list:
            for mode_stats in stats.values():
                q_stats = mode_stats["questions"]
                q_stats["avgProgressOnBuzz"] = {}
                for k, c_progress_on_buzz_stat in q_stats["cumulativeProgressOnBuzz"].items():
                    avg_progress_on_buzz = q_stats["avgProgressOnBuzz"]
                    # noinspection PyTypeChecker
                    avg_progress_on_buzz[k] = {}
                    for cat_name, cat_val in c_progress_on_buzz_stat.items():
                        avg_progress_on_buzz[k][cat_name] = cat_val / q_stats["played"][cat_name]
                q_stats["buzzRate"] = {}
                q_stats["buzzAccuracy"] = {}
                for cat_name in q_stats["played"]:
                    # noinspection PyTypeChecker
                    q_stats["buzzRate"][cat_name] = q_stats["buzzed"][cat_name] / q_stats["played"][cat_name]
                    # noinspection PyTypeChecker
                    q_stats["buzzAccuracy"][cat_name] = q_stats["correct"][cat_name] / q_stats["buzzed"][cat_name]
                g_stats = mode_stats["game"]
                g_stats["winRate"] = {}
                for cat_name in g_stats["played"]:
                    # noinspection PyTypeChecker
                    g_stats["winRate"][cat_name] = g_stats["won"][cat_name] / g_stats["played"][cat_name]
        return [{"stats": stats, **user} for stats in stats_list]

    @pytest.fixture
    def update_args_multiple(self, users):
        user_update_args = {}
        for i, user in enumerate(users):
            user_update_args[user["username"]] = {
                "questionStats": {
                    "played": i + 1,
                    "buzzed": i + 1,
                    "correct": i + 1,
                    "cumulativeProgressOnBuzz": {
                        "percentQuestionRead": i + 1,
                        "numSentences": i + 1
                    }
                },
                "finished": i % 2 == 0,  # Alternate between True and False
                "won": i % 4 == 0  # Set to True every 4 iterations, otherwise False
            }
        return {
            "mode": "casual",
            "category": "literature",
            "users": user_update_args
        }

    @pytest.fixture
    def update_args_multi_category(self, user):
        return [
            {
                "mode": "casual",
                "categories": ["literature", "history"],
                "users": {
                    user["username"]: {
                        "questionStats": {
                            "played": {"literature": 10, "history": 5},
                            "buzzed": {"literature": 5, "history": 1},
                            "correct": {"literature": 2, "history": 0},
                            "cumulativeProgressOnBuzz": {
                                "percentQuestionRead": {"literature": 2.5, "history": 1.5},
                                "numSentences": {"literature": 10, "history": 7}
                            }
                        },
                        "finished": True,
                        "won": False
                    }
                }
            },
            {
                "mode": "casual",
                "categories": ["mathematics", "history"],
                "users": {
                    user["username"]: {
                        "questionStats": {
                            "played": {"mathematics": 10, "history": 5},
                            "buzzed": {"mathematics": 5, "history": 1},
                            "correct": {"mathematics": 2, "history": 0},
                            "cumulativeProgressOnBuzz": {
                                "percentQuestionRead": {"mathematics": 2.5, "history": 1.5},
                                "numSentences": {"mathematics": 10, "history": 7}
                            }
                        },
                        "finished": True,
                        "won": True
                    }
                }
            }
        ]

    @pytest.fixture
    def expected_results_multi_category(self, user):
        stats_list = [
            {
                "casual": {
                    "questions": {
                        "played": {"all": 15, "literature": 10, "history": 5},
                        "buzzed": {"all": 6, "literature": 5, "history": 1},
                        "correct": {"all": 2, "literature": 2, "history": 0},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 4.0, "literature": 2.5, "history": 1.5},
                            "numSentences": {"all": 17, "literature": 10, "history": 7}
                        }
                    },
                    "game": {
                        "played": {"all": 1, "literature": 1, "history": 1},
                        "finished": {"all": 1, "literature": 1, "history": 1},
                        "won": {"all": 0, "literature": 0, "history": 0}
                    }
                }
            },
            {
                "casual": {
                    "questions": {
                        "played": {"all": 30, "literature": 10, "history": 10, "mathematics": 10},
                        "buzzed": {"all": 12, "literature": 5, "history": 2, "mathematics": 5},
                        "correct": {"all": 4, "literature": 2, "history": 0, "mathematics": 2},
                        "cumulativeProgressOnBuzz": {
                            "percentQuestionRead": {"all": 8.0, "literature": 2.5, "history": 3.0, "mathematics": 2.5},
                            "numSentences": {"all": 34, "literature": 10, "history": 14, "mathematics": 10}
                        }
                    },
                    "game": {
                        "played": {"all": 2, "literature": 1, "history": 2, "mathematics": 1},
                        "finished": {"all": 2, "literature": 1, "history": 2, "mathematics": 1},
                        "won": {"all": 1, "literature": 0, "history": 1, "mathematics": 1}
                    }
                }
            }
        ]
        for stats in stats_list:
            for mode_stats in stats.values():
                q_stats = mode_stats["questions"]
                q_stats["avgProgressOnBuzz"] = {}
                for k, c_progress_on_buzz_stat in q_stats["cumulativeProgressOnBuzz"].items():
                    avg_progress_on_buzz = q_stats["avgProgressOnBuzz"]
                    # noinspection PyTypeChecker
                    avg_progress_on_buzz[k] = {}
                    for cat_name, cat_val in c_progress_on_buzz_stat.items():
                        avg_progress_on_buzz[k][cat_name] = cat_val / q_stats["played"][cat_name]
                q_stats["buzzRate"] = {}
                q_stats["buzzAccuracy"] = {}
                for cat_name in q_stats["played"]:
                    # noinspection PyTypeChecker
                    q_stats["buzzRate"][cat_name] = q_stats["buzzed"][cat_name] / q_stats["played"][cat_name]
                    # noinspection PyTypeChecker
                    q_stats["buzzAccuracy"][cat_name] = q_stats["correct"][cat_name] / q_stats["buzzed"][cat_name]
                g_stats = mode_stats["game"]
                g_stats["winRate"] = {}
                for cat_name in g_stats["played"]:
                    # noinspection PyTypeChecker
                    g_stats["winRate"][cat_name] = g_stats["won"][cat_name] / g_stats["played"][cat_name]
        return [{"stats": stats, **user} for stats in stats_list]

    # Test Case: One user. Test multiple updates and assert that they work as intended.
    def test_single_growth(self, client, mongodb, user, update_args, socket_server_key, expected_results):
        for i in range(len(update_args)):
            response = client.put(self.ROUTE, json=update_args[i], headers={"Authorization": socket_server_key})
            assert testutil.match_status(HTTPStatus.OK, response.status)  # Might be better to use response.status_code
            response_body = response.get_json()
            assert response_body["successful"] == response_body["requested"]
            live_user = mongodb.Users.find_one({"_id": user["_id"]})
            assert live_user == expected_results[i]

    # Test Case: Multiple users. Assert that the iteration works properly.
    def test_multiple(self, client, mongodb, users, update_args_multiple, socket_server_key):
        response = client.put(self.ROUTE, json=update_args_multiple, headers={"Authorization": socket_server_key})
        assert testutil.match_status(HTTPStatus.OK, response.status)
        response_body = response.get_json()
        assert response_body["successful"] == response_body["requested"]
        for user in users:
            live_user = mongodb.Users.find_one({"_id": user["_id"]})
            assert "stats" in live_user

    # Test Case: One user, multiple categories. Test multiple updates and assert that they work as intended.
    def test_multi_category(self, client, mongodb, user,
                            update_args_multi_category, socket_server_key, expected_results_multi_category):
        for i in range(len(update_args_multi_category)):
            response = client.put(self.ROUTE,
                                  json=update_args_multi_category[i], headers={"Authorization": socket_server_key})
            assert testutil.match_status(HTTPStatus.OK, response.status)  # Might be better to use response.status_code
            response_body = response.get_json()
            assert response_body["successful"] == response_body["requested"]
            live_user = mongodb.Users.find_one({"_id": user["_id"]})
            assert live_user == expected_results_multi_category[i]


@pytest.mark.usefixtures("client", "mongodb", "firebase_bucket", "input_dir", "dev_uid")
class TestUploadRec:
    ROUTE = "/audio"
    CONTENT_TYPE = "multipart/form-data"
    DEFAULT_QID = 0
    DEFAULT_SID = 0

    @pytest.fixture
    def unrec_qid(self, input_dir, mongodb):
        transcript_path = os.path.join(input_dir, "transcript.txt")
        assert os.path.exists(transcript_path)
        with open(transcript_path, "r") as f:
            transcript = f.read()
        question_result = mongodb.UnrecordedQuestions.insert_one({
            "transcript": transcript,
            "qb_id": self.DEFAULT_QID
        })
        yield
        mongodb.UnrecordedQuestions.delete_one({"_id": question_result.inserted_id})

    @pytest.fixture
    def unrec_sentence_ids(self, input_dir, mongodb):
        transcript_path = os.path.join(input_dir, "segmented", "transcript.txt")
        assert os.path.exists(transcript_path)
        with open(transcript_path, "r") as f:
            transcript_text = f.read()
        transcripts = transcript_text.strip().split("\n")
        sentence_docs = []
        sentence_ids = []
        for i, t in enumerate(transcripts):
            sentence_docs.append({"transcript": t, "sentenceId": i, "qb_id": self.DEFAULT_QID})
            sentence_ids.append(i)
        results = mongodb.UnrecordedQuestions.insert_many(sentence_docs)
        yield sentence_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": results.inserted_ids}})

    @pytest.fixture
    def user_id(self, mongodb, dev_uid):
        user_result = mongodb.Users.insert_one({"_id": dev_uid, "recordedAudios": []})
        yield user_result.inserted_id
        mongodb.Users.delete_one({"_id": user_result.inserted_id})

    @pytest.fixture
    def upload_cleanup(self, mongodb, firebase_bucket, flask_app):
        yield
        audio_cursor = mongodb.UnprocessedAudio.find(None, {"_id": 1, "recType": 1})
        for audio_doc in audio_cursor:
            fid = audio_doc["_id"]
            firebase_bucket.blob("/".join([flask_app.config["BLOB_ROOT"], audio_doc["recType"], fid])).delete()
        mongodb.UnprocessedAudio.delete_many({"_id": {"$exists": True}})
        audio_cursor = mongodb.Audio.find(None, {"_id": 1, "recType": 1})
        for audio_doc in audio_cursor:
            fid = audio_doc["_id"]
            firebase_bucket.blob("/".join([flask_app.config["BLOB_ROOT"], audio_doc["recType"], fid])).delete()
        mongodb.Audio.delete_many({"_id": {"$exists": True}})

    @pytest.fixture
    def exact_data(self, input_dir, unrec_qid):
        audio_path = os.path.join(input_dir, "exact.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"qb_id": self.DEFAULT_QID, "audio": audio, "recType": "normal"}
        audio.close()

    @pytest.fixture
    def mismatch_data(self, input_dir, unrec_qid):
        audio_path = os.path.join(input_dir, "mismatch.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"qb_id": self.DEFAULT_QID, "audio": audio, "recType": "normal"}
        audio.close()

    @pytest.fixture
    def bad_env_data(self, input_dir, unrec_qid):
        audio_path = os.path.join(input_dir, "bad_env.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"qb_id": self.DEFAULT_QID, "audio": audio, "recType": "normal"}
        audio.close()

    @pytest.fixture
    def admin_data(self, exact_data):
        data = exact_data.copy()
        data["diarMetadata"] = "detect_num_speakers=False, max_num_speakers=3"
        return data

    @pytest.fixture
    def buzz_data(self, input_dir):
        audio_path = os.path.join(input_dir, "buzz.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"audio": audio, "recType": "buzz"}
        audio.close()

    @pytest.fixture
    def answer_data(self, input_dir, unrec_qid):
        audio_path = os.path.join(input_dir, "answer.wav")
        assert os.path.exists(audio_path)
        audio = open(audio_path, "rb")
        yield {"audio": audio, "recType": "answer", "qb_id": self.DEFAULT_QID}
        audio.close()

    @pytest.fixture
    def segmented_data(self, input_dir, unrec_sentence_ids):
        data = self.get_segmented_data(input_dir, unrec_sentence_ids, "exact")
        yield data
        for f in data["audio"]:
            f.close()

    @pytest.fixture
    def segmented_mismatch_data(self, input_dir, unrec_sentence_ids):
        data = self.get_segmented_data(input_dir, unrec_sentence_ids, "mismatch")
        yield data
        for f in data["audio"]:
            f.close()

    @pytest.fixture
    def segmented_partial_mismatch_data(self, input_dir, unrec_sentence_ids):
        data = self.get_segmented_data(input_dir, unrec_sentence_ids, "partial_mismatch")
        yield data
        for f in data["audio"]:
            f.close()

    def get_segmented_data(self, input_dir, unrec_sentence_ids, subdir_name):
        """Get the form arguments for a batch of audio files based on segmented questions."""
        data = {"audio": [], "recType": [], "qb_id": [], "sentenceId": []}
        for i in unrec_sentence_ids:
            audio_path = os.path.join(input_dir, "segmented", subdir_name, f"{i}.wav")
            assert os.path.exists(audio_path)
            data["audio"].append(open(audio_path, "rb"))
            data["recType"].append("normal")
            data["qb_id"].append(self.DEFAULT_QID)
            data["sentenceId"].append(i)
        return data

    # Test Case: Submitting a recording that should be guaranteed to pass the pre-screening.
    def test_success(self, client, mongodb, exact_data, upload_cleanup, user_id):
        doc_required_fields = ["gentleVtt", "qb_id", "userId", "recType"]
        response = client.post(self.ROUTE, data=exact_data, content_type=self.CONTENT_TYPE)
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        assert response_body.get("prescreenSuccessful")
        audio_doc = mongodb.UnprocessedAudio.find_one()
        for field in doc_required_fields:
            assert field in audio_doc

    # Test Case: Submitting a recording with audio distorted by environmental noise.
    def test_bad_env(self, client, mongodb, bad_env_data, upload_cleanup, user_id):
        response = client.post(self.ROUTE, data=bad_env_data, content_type=self.CONTENT_TYPE)
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        logger.debug(f"response_body = {response_body}")
        assert response_body.get("prescreenSuccessful")

    # Test Case: Submitting a recording of the speaker reading a paragraph from the "Lorem ipsum" Wikipedia article.
    # Source: https://en.wikipedia.org/wiki/Lorem_ipsum
    def test_mismatch(self, client, mongodb, mismatch_data, upload_cleanup, user_id):
        response = client.post(self.ROUTE, data=mismatch_data, content_type=self.CONTENT_TYPE)
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        logger.debug(f"response_body = {response_body}")
        assert not response_body.get("prescreenSuccessful")

    # Test Case: Submitting a recording as an administrator.
    def test_admin(self, mongodb, client, admin_data, upload_cleanup, user_id):
        doc_required_fields = ["gentleVtt", "qb_id", "userId", "recType", "diarMetadata"]
        response = client.post(self.ROUTE, data=admin_data, content_type=self.CONTENT_TYPE)
        response_body = response.get_json()
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
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
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
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

    # Test Case: Submitting a recording for an answer.
    def test_answer(self, mongodb, client, answer_data, upload_cleanup, user_id):
        doc_required_fields = ["userId", "recType", "qb_id"]
        response = client.post(self.ROUTE, data=answer_data, content_type=self.CONTENT_TYPE)
        response_body = response.get_json()
        logger.debug(f"response_body = {response_body}")
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
        assert response_body.get("prescreenSuccessful")

        audio_doc = mongodb.Audio.find_one()
        assert audio_doc
        for field in doc_required_fields:
            assert field in audio_doc
        assert audio_doc["recType"] == "answer"

        user_doc = mongodb.Users.find_one({"_id": user_id})
        rec = user_doc["recordedAudios"][0]
        assert rec["id"] == audio_doc["_id"]
        assert rec["recType"] == "answer"

    # Test Case: Submitting a segmented question.
    def test_segmented(self, mongodb, client, segmented_data, upload_cleanup, user_id):
        doc_required_fields = ["gentleVtt", "qb_id", "sentenceId", "userId", "recType"]
        response = client.post(self.ROUTE, data=segmented_data, content_type=self.CONTENT_TYPE)
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        assert response_body.get("prescreenSuccessful")
        cursor = mongodb.UnprocessedAudio.find()
        for audio_doc in cursor:
            for field in doc_required_fields:
                assert field in audio_doc

    def test_segmented_mismatch(self, mongodb, client, segmented_mismatch_data, upload_cleanup, user_id):
        response = client.post(self.ROUTE, data=segmented_mismatch_data, content_type=self.CONTENT_TYPE)
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        assert not response_body.get("prescreenSuccessful")

    @pytest.mark.xfail
    def test_segmented_partial_mismatch(self,
                                        mongodb, client, segmented_partial_mismatch_data, upload_cleanup, user_id):
        doc_required_fields = ["gentleVtt", "qb_id", "sentenceId", "userId", "recType"]
        response = client.post(self.ROUTE, data=segmented_partial_mismatch_data, content_type=self.CONTENT_TYPE)
        assert testutil.match_status(HTTPStatus.ACCEPTED, response.status)
        response_body = response.get_json()
        assert response_body.get("prescreenSuccessful")
        cursor = mongodb.UnprocessedAudio.find()
        for audio_doc in cursor:
            for field in doc_required_fields:
                assert field in audio_doc


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
        profile = api_spec.get_schema_stub("User")
        profile["_id"] = dev_uid
        result = mongodb.Users.insert_one(profile)
        yield profile
        mongodb.Users.delete_one({"_id": result.inserted_id})

    def test_create(self, client, mongodb, profile_args, dev_uid, api_spec):
        response = client.post(self.ROUTE, json=profile_args)
        assert testutil.match_status(HTTPStatus.CREATED, response.status)
        profile = mongodb.Users.find_one({"_id": dev_uid})
        assert profile
        validate(profile, api_spec.get_schema("User", resolve_references=True))

    def test_get(self, client, user_profile):
        required_fields = [
            "pfp",
            "username",
            "usernameSpecs",
            "ratings",
            "totalQuestionsPlayed",
            "totalGames",
            "coins",
            "coinsCumulative",
            "activityOverview",
            "recordedAudios",
            "permLevel"
        ]
        response = client.get(self.ROUTE)
        assert testutil.match_status(HTTPStatus.OK, response.status)
        profile = response.get_json()
        assert profile
        for field in required_fields:
            assert field in profile

    def test_update(self, client, mongodb, user_profile, profile_update_args):
        response = client.patch(self.ROUTE, json=profile_update_args)
        assert testutil.match_status(HTTPStatus.OK, response.status)
        new_profile = {**user_profile, **profile_update_args}  # Merge two dictionaries without modifying either one.
        other_profile = mongodb.Users.find_one({"_id": new_profile["_id"]})
        assert new_profile == other_profile

    def test_delete(self, client, mongodb, user_profile):
        response = client.delete(self.ROUTE)
        assert testutil.match_status(HTTPStatus.OK, response.status)
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
        assert testutil.match_status(HTTPStatus.OK, response.status)
        profile = response.get_json()
        for field in profile:
            assert field in other_profile
            assert profile[field] == other_profile[field]

    def test_update(self, client, mongodb, admin_profile, other_profile, profile_update_args):
        full_route = "/".join([self.ROUTE, other_profile["username"]])
        response = client.patch(full_route, json=profile_update_args)
        assert testutil.match_status(HTTPStatus.OK, response.status)
        new_profile = {**other_profile, **profile_update_args}  # Merge two dictionaries without modifying either one.
        actual_profile = mongodb.Users.find_one({"_id": new_profile["_id"]})
        assert new_profile == actual_profile

    def test_delete(self, client, mongodb, admin_profile, other_profile):
        full_route = "/".join([self.ROUTE, other_profile["username"]])
        response = client.delete(full_route)
        assert testutil.match_status(HTTPStatus.OK, response.status)
        assert not mongodb.Users.find_one({"_id": other_profile["_id"]})
