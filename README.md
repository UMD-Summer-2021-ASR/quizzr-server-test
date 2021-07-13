# Quizzr.io Back-end Core (Test Extension)
This repository includes Python modules for running automated tests on the [Quizzr.io Back-end Core](https://github.com/UMD-Summer-2021-ASR/quizzr-server) repository. To install it, clone the repository and install the requirements given in the `requirements.txt` file. Prior to running one of these automated test files, be sure to include the directory of the server in the `PYTHONPATH` environment variable.

## Tests
There are two testing modules for the server: `test_pipeline.py` and `test_error_pipeline.py`. Test cases in both modules are grouped by the endpoint they are testing. Refer to the in-code documentation for more details on the test cases.

### `test_pipeline.py`
This testing module tests the functionality of the server's endpoints in normal scenarios. Currently, it only tests the following endpoints:
* `GET` `/answer/`
* `GET` `/audio/unprocessed/`
* `POST` `/upload`


### `test_error_pipeline.py`
This testing module tests whether the server handles corrupted data as expected. Currently, it only tests the following endpoints:
* `GET` `/answer/`
* `POST` `/audio/processed`
* `GET` `/record/`
* `GET` `/audio/unprocessed/`