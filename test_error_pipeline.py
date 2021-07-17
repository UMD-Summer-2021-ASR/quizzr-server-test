import logging
from http import HTTPStatus

import bson
import pytest

from corruption import shatter_dict
from testutil import generate_audio_id, match_status


# For testing cases where any data the server expects is corrupt and/or incomplete.


@pytest.mark.usefixtures("client", "mongodb")
class TestGetUnprocAudio:
    ROUTE = "/audio/unprocessed/"

    @pytest.fixture
    def unrec_questions(self, mongodb):
        question_docs = [
            {},
            {"transcript": "Foo"}
        ]
        results = mongodb.UnrecordedQuestions.insert_many(question_docs)
        yield results.inserted_ids
        mongodb.UnrecordedQuestions.delete_many({"_id": {"$in": results.inserted_ids}})

    @pytest.fixture
    def audio_doc_no_qid(self, mongodb):
        result = mongodb.UnprocessedAudio.insert_one({"_id": generate_audio_id()})
        yield result.inserted_id
        mongodb.UnprocessedAudio.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def audio_doc_invalid_qid(self, mongodb):
        result = mongodb.UnprocessedAudio.insert_one({"_id": generate_audio_id(), "questionId": bson.ObjectId()})
        yield result.inserted_id
        mongodb.UnprocessedAudio.delete_one({"_id": result.inserted_id})

    @pytest.fixture
    def audio_docs(self, mongodb, unrec_questions):
        entries = []
        for qid in unrec_questions:
            entries.append({"_id": generate_audio_id(), "questionId": qid})
        audio_results = mongodb.UnprocessedAudio.insert_many(entries)
        yield
        mongodb.UnprocessedAudio.delete_many({"_id": {"$in": audio_results.inserted_ids}})

    # Test Case: No documents in the UnprocessedAudio collection
    def test_empty(self, client):
        test_values = {
            "status": HTTPStatus.NOT_FOUND,
            "resp": b'empty_unproc_audio'
        }
        response = client.get(self.ROUTE)
        assert match_status(test_values["status"], response.status)
        assert response.get_data() == test_values["resp"]

    # The test cases below are for specifically when there is only one audio document with the specified condition.
    # Test Case: Audio document does not contain question ID
    def test_no_qid(self, client, audio_doc_no_qid):
        test_values = {
            "status": HTTPStatus.NOT_FOUND,
            "resp": b'empty_qid2entries'
        }
        response = client.get(self.ROUTE)
        assert match_status(test_values["status"], response.status)
        assert response.get_data() == test_values["resp"]

    # Test Case: Audio document contains invalid question ID
    def test_invalid_qid(self, client, audio_doc_invalid_qid):
        test_values = {
            "status": HTTPStatus.OK
        }
        response = client.get(self.ROUTE)
        assert match_status(test_values["status"], response.status)

    # Test Case: Multiple audio documents with data corrupted in the following ways:
    #   1. No question ID
    #   2. Invalid question ID
    #   3. Valid question ID with:
    #     i. No transcript
    #     ii. A transcript
    def test_corrupt(self, client, audio_docs, audio_doc_no_qid, audio_doc_invalid_qid, unrec_questions):
        test_values = {
            "status": HTTPStatus.OK,
            "errors": [
                {"type": "internal_error", "reason": "undefined_question_id"}
            ]
        }
        response = client.get(self.ROUTE)
        response_body = response.get_json()
        assert match_status(test_values["status"], response.status)
        for error in test_values["errors"]:
            assert error in response_body["errors"]


@pytest.mark.usefixtures("client", "mongodb")
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
    def unproc_audio_documents(self, mongodb, unrec_question):
        audio_docs = [
            {},
            {"questionId": bson.ObjectId()},
            {"questionId": bson.ObjectId(), "userId": bson.ObjectId()},
            {"questionId": unrec_question["_id"]},
            {"questionId": unrec_question["_id"], "userId": bson.ObjectId()}
        ]
        for doc in audio_docs:
            doc["_id"] = generate_audio_id()

        audio_results = mongodb.UnprocessedAudio.insert_many(audio_docs)
        yield audio_results.inserted_ids
        mongodb.UnprocessedAudio.delete_many({"_id": {"$in": audio_results.inserted_ids}})

    @pytest.fixture
    def update_batch(self, mongodb, unproc_audio_documents):
        batch = [{}, {"_id": generate_audio_id()}]
        id_list = []
        for doc_id in unproc_audio_documents:
            batch.append({"_id": doc_id, "vtt": "Placeholder"})
            id_list.append(doc_id)
        yield batch
        mongodb.Audio.delete_many({"_id": {"$in": id_list}})

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


@pytest.mark.usefixtures("client", "mongodb")
class TestGetRec:
    ROUTE = "/answer/"

    @pytest.fixture
    def all_corrupt(self, mongodb, qs_metadata):
        def attach_ids(documents, id_gen_func, *args, **kwargs):
            for document in documents:
                document_c = document.copy()
                document_c["_id"] = id_gen_func(*args, **kwargs)
                yield document_c

        base_audio_doc = {
            "vtt": "The quick brown fox jumps over the lazy dog.",
            "gentleVtt": "This is a dummy VTT.",
            "version": qs_metadata["version"],
            "score": {"wer": 1.0, "mer": 1.0, "wil": 1.0}
        }

        audio_docs = shatter_dict(base_audio_doc, depth=-1, affected_keys=["vtt", "gentleVtt"])
        audio_results = mongodb.Audio.insert_many(attach_ids(audio_docs, generate_audio_id))
        questions = [
            {}, {"recordings": []}, {"recordings": [generate_audio_id()]}, {"recordings": audio_results.inserted_ids}
        ]
        question_results = mongodb.RecordedQuestions.insert_many(questions)
        yield
        mongodb.Audio.delete_many({"_id": {"$in": audio_results.inserted_ids}})
        mongodb.RecordedQuestions.delete_many({"_id": {"$in": question_results.inserted_ids}})

    # Test Cases:
    #   The question has an undefined "recordings" field
    #   The question has an empty "recordings" field
    #   The question has an invalid audio ID
    #   The question has multiple valid IDs of audio documents with missing data:
    #     i. No VTT from the Kaldi pipeline.
    #     ii. No VTT from the pre-screening.
    def test_all_corrupt(self, client, all_corrupt, caplog):
        test_values = {
            "logs": [
                " is invalid or associated question has no valid audio recordings",
                "No audio documents found",
                "Failed to find a viable audio document",
                "Audio document is missing at least one required field: "
            ],
            "resp": b'rec_corrupt_questions',
            "status": HTTPStatus.NOT_FOUND
        }
        caplog.set_level(logging.DEBUG)
        response = client.get(self.ROUTE)
        assert match_status(test_values["status"], response.status)
        assert response.get_data() == test_values["resp"]
        for log in test_values["logs"]:
            assert log in caplog.text

    # Test Case: There are no recorded questions
    def test_empty(self, client):
        test_values = {
            "resp": b'rec_empty_qids',
            "status": HTTPStatus.NOT_FOUND
        }
        response = client.get(self.ROUTE)
        assert match_status(test_values["status"], response.status)
        assert response.get_data() == test_values["resp"]


@pytest.mark.usefixtures("client", "mongodb")
class TestGetTranscript:
    ROUTE = "/record/"

    @pytest.fixture
    def all_corrupt(self, mongodb):
        question_result = mongodb.UnrecordedQuestions.insert_one({})
        yield
        mongodb.UnrecordedQuestions.delete_one({"_id": question_result.inserted_id})

    # Test Case: The question does not have a transcript
    def test_all_corrupt(self, client, all_corrupt, caplog):
        test_values = {
            "logs": [
                " is invalid or associated question has no transcript"
            ],
            "resp": b'unrec_corrupt_questions',
            "status": HTTPStatus.NOT_FOUND
        }
        response = client.get(self.ROUTE)
        assert match_status(test_values["status"], response.status)
        assert response.get_data() == test_values["resp"]
        for log in test_values["logs"]:
            assert log in caplog.text

    # Test Case: There are no unrecorded questions
    def test_empty(self, client):
        test_values = {
            "resp": b'unrec_empty_qids',
            "status": HTTPStatus.NOT_FOUND
        }
        response = client.get(self.ROUTE)
        assert match_status(test_values["status"], response.status)
        assert response.get_data() == test_values["resp"]
