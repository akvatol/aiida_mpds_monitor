from unittest.mock import MagicMock, patch

from aiida_mpds_monitor.webhook import send_archive, send_webhook


class TestSendWebhook:
    """Test cases for send_webhook function."""

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_send_webhook_success(self, mock_post):
        """Test successful webhook submission."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = send_webhook(
            "http://example.com/webhook", "test_payload", "finished"
        )

        assert result is True
        mock_post.assert_called_once_with(
            "http://example.com/webhook",
            data={
                "payload": "test_payload",
                "status": "finished",
            },
            timeout=10,
        )

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_send_webhook_redacts_auth_key_in_error_log(self, mock_post):
        mock_response = MagicMock(status_code=403, text="Forbidden")
        mock_post.return_value = mock_response

        with patch("aiida_mpds_monitor.webhook.logger") as mock_logger:
            result = send_webhook(
                "http://example.com/webhook",
                "test_payload",
                "excepted",
                key="secret_key",
            )

        assert result is False
        log_args = mock_logger.error.call_args.args
        assert log_args[3]["key"] == "***"
        assert "secret_key" not in repr(log_args)

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_send_webhook_failure(self, mock_post):
        """Test webhook submission failure and logging of request data."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "internal error"
        mock_post.return_value = mock_response
        with patch("aiida_mpds_monitor.webhook.logger") as mock_logger:
            result = send_webhook(
                "http://example.com/webhook", "test_payload", "excepted"
            )
            assert result is False
            mock_logger.error.assert_called_once()
            # ensure the logged message contains the URL and data payload
            args, _ = mock_logger.error.call_args
            assert "http://example.com/webhook" in args[2]
            assert "test_payload" in repr(args[3])

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_send_webhook_with_auth_key(self, mock_post):
        """Test webhook submission with authentication key."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = send_webhook(
            "http://example.com/webhook",
            "test_payload",
            "finished",
            key="secret_key",
        )

        assert result is True
        mock_post.assert_called_once_with(
            "http://example.com/webhook",
            data={
                "payload": "test_payload",
                "status": "finished",
                "key": "secret_key",
            },
            timeout=10,
        )

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_send_webhook_exception(self, mock_post):
        """Test webhook exception handling and that the request is logged."""
        mock_post.side_effect = Exception("Connection error")
        with patch("aiida_mpds_monitor.webhook.logger") as mock_logger:
            result = send_webhook(
                "http://example.com/webhook", "test_payload", "finished"
            )
            assert result is False
            mock_logger.error.assert_called_once()
            args, _ = mock_logger.error.call_args
            # first arg is format string, second arg should be the exception
            assert "Connection error" in str(args[1])

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_send_webhook_409_treated_as_success(self, mock_post):
        """Test that 409 (already exists on server) is treated as success."""
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_post.return_value = mock_response

        with patch("aiida_mpds_monitor.webhook.logger") as mock_logger:
            result = send_webhook(
                "http://example.com/webhook", "test_payload", "finished"
            )

        assert result is True
        mock_logger.info.assert_called_once()
        mock_logger.error.assert_not_called()

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_send_webhook_timeout(self, mock_post):
        """Test webhook timeout handling."""
        mock_post.side_effect = TimeoutError("Request timeout")

        result = send_webhook(
            "http://example.com/webhook", "test_payload", "finished"
        )

        assert result is False


class TestSendArchive:
    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_successful_multipart_upload(self, mock_post, tmp_path):
        archive = tmp_path / "BaMnO3.7z"
        archive.write_bytes(b"archive contents")
        mock_post.return_value = MagicMock(status_code=200)

        result = send_archive(
            "http://example.com/upload",
            archive,
            bid=42,
            schema_id=7,
            key="archive-secret",
            timeout=15,
        )

        assert result is True
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        assert mock_post.call_args.args == ("http://example.com/upload",)
        assert kwargs["data"] == {"bid": "42", "schema_id": "7"}
        assert kwargs["headers"] == {"Authorization": "Bearer archive-secret"}
        assert kwargs["timeout"] == 15
        filename, file_handle, content_type = kwargs["files"]["file"]
        assert filename == "BaMnO3.7z"
        assert content_type == "application/x-7z-compressed"
        assert file_handle.closed

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_non_200_upload_is_failure_and_logs_response(self, mock_post, tmp_path):
        archive = tmp_path / "result.7z"
        archive.write_bytes(b"archive")
        mock_post.return_value = MagicMock(status_code=403, text="Forbidden")

        with patch("aiida_mpds_monitor.webhook.logger") as mock_logger:
            result = send_archive("http://example.com/upload", archive)

        assert result is False
        assert mock_logger.error.call_count == 1
        assert mock_logger.error.call_args.args[1] == 403
        assert mock_logger.error.call_args.args[4] == "Forbidden"

    @patch("aiida_mpds_monitor.webhook.requests.post")
    def test_missing_archive_is_failure_without_http_request(self, mock_post, tmp_path):
        result = send_archive(
            "http://example.com/upload", tmp_path / "missing.7z"
        )

        assert result is False
        mock_post.assert_not_called()
