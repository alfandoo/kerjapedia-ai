import pytest

from app.services.cv_reviewer import CV_TMP_PREFIX, validate_cv_upload


def test_valid_cv_returns_isolated_prefix():
    key = validate_cv_upload("lamaran.pdf", "application/pdf", 1024)
    assert key.startswith(CV_TMP_PREFIX)
    assert ".." not in key


def test_invalid_suffix_rejected():
    with pytest.raises(ValueError):
        validate_cv_upload("cv.exe", "application/pdf", 1024)


def test_oversize_rejected():
    with pytest.raises(ValueError):
        validate_cv_upload("cv.pdf", "application/pdf", 10 * 1024 * 1024)


def test_path_traversal_rejected():
    with pytest.raises(ValueError):
        validate_cv_upload("../secret.pdf", "application/pdf", 1024)
