# Quizzr.io Back-end Core (Test Extension)
This repository includes Python modules for running automated tests on the [Quizzr.io Back-end Core](https://github.com/UMD-Summer-2021-ASR/quizzr-server) repository. To install it, clone the repository and install the requirements given in the `requirements.txt` file. Prior to running one of these automated test files, be sure to include the directory of the server in the `PYTHONPATH` environment variable.

## Tests
Currently, there are only tests on how the server handles cases where the input arguments and MongoDB documents are corrupt while handling requests. More specifically, there are test cases for `GET` `/record/`, `GET` `/answer/`, `GET` `/audio/unprocessed`, and `POST` `/audio/processed`.