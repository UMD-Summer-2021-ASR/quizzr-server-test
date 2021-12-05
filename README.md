# Quizzr.io Data Flow Server (Test Extension)
This repository includes Python modules for running automated tests on the [Quizzr.io Data Flow Server](https://github.com/UMD-Summer-2021-ASR/quizzr-server) repository. To install it, clone the repository and install the requirements given in the `requirements.txt` file. Prior to running one of these automated test files, be sure to include the directory of the server in the `PYTHONPATH` and `SERVER_DIR` environment variables. The `CONNECTION_STRING` for MongoDB is also necessary to run most of these tests.

## Tests
There are two testing modules for the server: `test_endpoints.py` and `test_error_endpoints.py`. Test cases in both modules are grouped by the action they are testing. The individual test cases are variations of the action they are testing. Refer to the in-code documentation for more details on the test cases.

### `test_endpoints.py`
This testing module tests the functionality of the server's endpoints in normal scenarios. Currently, it only implements the following test classes:
* `TestCheckAnswer`
* `TestGetFile`
* `TestGetLeaderboard`
* `TestGetRec`
* `TestGetTranscript`
* `TestGetUnprocAudio`
* `TestHLSGet`
* `TestOwnProfile`
* `TestOtherProfile`
* `TestProcessAudio`
* `TestProcessGameResults`
* `TestUploadRec`
* `TestVoting`


### `test_error_endpoints.py`
Do not use this testing module. It is out of date beyond usability. 
This testing module tests whether the server handles corrupted data as expected. Currently, it only implements the following test classes:
* `TestGetRec`
* `TestGetTranscript`
* `TestGetUnprocAudio`
* `TestProcessAudio`

### Test Class Definitions
The name of each class in a testing module defines the action that the associated group is testing. The following is the list of actions that the class names signify:

| Class Name               | Description                                                    |
| ------------------------ | -------------------------------------------------------------- |
| `TestCheckAnswer`        | Check if an answer to a question is correct.                   |
| `TestGetFile`            | Get a file from Google Drive.                                  |
| `TestGetLeaderboard`     | Get the top users in ranked games.                             |
| `TestGetRec`             | Get a recording for answering a question.                      |
| `TestGetTranscript`      | Get a transcript for recording.                                |
| `TestGetUnprocAudio`     | Get a batch of unprocessed audio documents.                    |
| `TestHLSGet`             | Get a VTT by audio ID.                                         |
| `TestOwnProfile`         | Perform operations on the user's own profile.                  |
| `TestOtherProfile`       | Perform operations on the profiles of other users.             |
| `TestProcessAudio`       | Update a batch of audio documents with processing information. |
| `TestProcessGameResults` | Send the results of a game session to the server.              |
| `TestUploadRec`          | Submit a recording for pre-screening.                          |
| `TestVoting`             | Upvote and downvote recordings.                                |

## The `input` Directory
The code uses the `input` directory to run tests that require audio and/or a transcript. The following is a description of each file:
* `transcript.txt` contains the transcript to use for pre-screening audio files.
* `buzz.wav` and `answer.wav` are for testing submitting a `buzz` and `answer` recording respectively.
* `test.wav` is for running tests where the contents of the file do not matter.
* The speaker of `exact.wav` reads the transcript in `transcript.txt` aloud in an ideal environment.
* The `bad_env.wav` file is a variant of `exact.wav` with a reverberation effect added.
* The speaker of `mismatch.wav` reads a paragraph from [the "Lorem ipsum" Wikipedia article](https://en.wikipedia.org/wiki/Lorem_ipsum).

The `segmented` directory contains the folders `exact` and `mismatch`, which are the `exact.wav` and `mismatch.wav` files, respectively, split into multiple audio files. `segmented/transcript.txt` is a variant of `transcript.txt` delimiting sentences with a newline (`\n`) character. The numbering of each audio file in these folders corresponds to each sentence to use in the transcript. `segmented/partial_mismatch` contains a mix of audio files from `exact` and audio files from `mismatch`.