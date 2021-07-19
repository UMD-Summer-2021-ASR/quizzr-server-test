# Quizzr.io Data Flow Server (Test Extension)
This repository includes Python modules for running automated tests on the [Quizzr.io Data Flow Server](https://github.com/UMD-Summer-2021-ASR/quizzr-server) repository. To install it, clone the repository and install the requirements given in the `requirements.txt` file. Prior to running one of these automated test files, be sure to include the directory of the server in the `PYTHONPATH` and `SERVER_DIR` environment variables. The `CONNECTION_STRING` for MongoDB is also necessary to run most of these tests.

## Tests
There are two testing modules for the server: `test_endpoints.py` and `test_error_endpoints.py`. Test cases in both modules are grouped by the action they are testing. The individual test cases are variations of the action they are testing. Refer to the in-code documentation for more details on the test cases.

### `test_endpoints.py`
This testing module tests the functionality of the server's endpoints in normal scenarios. Currently, it only implements the following test classes:
* `TestCheckAnswer`
* `TestGetFile`
* `TestGetRec`
* `TestGetTranscript`
* `TestGetUnprocAudio`
* `TestProcessAudio`
* `TestUploadRec`


### `test_error_endpoints.py`
This testing module tests whether the server handles corrupted data as expected. Currently, it only implements the following test classes:
* `TestGetRec`
* `TestGetTranscript`
* `TestGetUnprocAudio`
* `TestProcessAudio`

### Test Class Definitions
The name of each class in a testing module defines the action that the associated group is testing. The following is the list of actions that the class names signify:

| Class Name           | Description                                                    |
| -------------------- | -------------------------------------------------------------- |
| `TestCheckAnswer`    | Check if an answer to a question is correct.                   |
| `TestGetFile`        | Get a file from Google Drive.                                  |
| `TestGetRec`         | Get a recording for answering a question.                      |
| `TestGetTranscript`  | Get a transcript for recording.                                |
| `TestGetUnprocAudio` | Get a batch of unprocessed audio documents.                    |
| `TestProcessAudio`   | Update a batch of audio documents with processing information. |
| `TestUploadRec`      | Submit a recording for pre-screening.                          |