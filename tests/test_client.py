"""Tests for sage.client module."""

from unittest.mock import MagicMock

from sage.client import ApiResponse, Message, send_message


class TestSendMessage:
    """Tests for send_message()."""

    def test_send_message_streams_response_and_returns_api_response(self):
        """send_message() successfully streams response content and returns ApiResponse."""
        # Create mock client
        mock_client = MagicMock()

        # Create mock stream context manager
        mock_stream = MagicMock()
        mock_client.messages.stream.return_value.__enter__.return_value = mock_stream

        # Create mock events for streaming
        text_delta_event1 = MagicMock()
        text_delta_event1.type = "content_block_delta"
        text_delta_event1.delta.text = "Hello, "

        text_delta_event2 = MagicMock()
        text_delta_event2.type = "content_block_delta"
        text_delta_event2.delta.text = "world!"

        message_delta_event = MagicMock()
        message_delta_event.type = "message_delta"
        message_delta_event.usage = MagicMock()
        message_delta_event.delta.stop_reason = "end_turn"

        mock_stream.__iter__ = lambda self: iter(
            [
                text_delta_event1,
                text_delta_event2,
                message_delta_event,
            ]
        )

        # Create mock final message
        mock_final = MagicMock()
        mock_final.usage.input_tokens = 100
        mock_final.usage.output_tokens = 50
        mock_final.usage.cache_read_input_tokens = 80
        mock_final.usage.cache_creation_input_tokens = 20
        mock_stream.get_final_message.return_value = mock_final

        # Track streamed text
        streamed_chunks = []

        def on_text(chunk):
            streamed_chunks.append(chunk)

        # Call send_message
        messages = [Message(role="user", content="Say hello")]
        result = send_message(
            client=mock_client,
            system="You are a helpful assistant.",
            messages=messages,
            on_text=on_text,
        )

        # Verify result
        assert result.ok is True
        response = result.value
        assert isinstance(response, ApiResponse)
        assert response.content == "Hello, world!"
        assert response.tokens_in == 100
        assert response.tokens_out == 50
        assert response.cache_read == 80
        assert response.cache_write == 20
        assert response.stop_reason == "end_turn"

        # Verify streaming callback was called
        assert streamed_chunks == ["Hello, ", "world!"]

        # Verify client was called correctly
        mock_client.messages.stream.assert_called_once()
        call_kwargs = mock_client.messages.stream.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["max_tokens"] == 4096
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["content"] == "Say hello"

    def test_send_message_counts_web_searches(self):
        """send_message() counts web search tool uses."""
        mock_client = MagicMock()
        mock_stream = MagicMock()
        mock_client.messages.stream.return_value.__enter__.return_value = mock_stream

        # Create events including tool use
        tool_start_event = MagicMock()
        tool_start_event.type = "content_block_start"
        tool_start_event.content_block.type = "tool_use"
        tool_start_event.content_block.name = "web_search"

        text_event = MagicMock()
        text_event.type = "content_block_delta"
        text_event.delta.text = "Search result."

        mock_stream.__iter__ = lambda self: iter([tool_start_event, text_event])

        mock_final = MagicMock()
        mock_final.usage.input_tokens = 100
        mock_final.usage.output_tokens = 50
        mock_final.usage.cache_read_input_tokens = 0
        mock_final.usage.cache_creation_input_tokens = 0
        mock_stream.get_final_message.return_value = mock_final

        result = send_message(
            client=mock_client,
            system="System prompt",
            messages=[Message(role="user", content="Search for X")],
        )

        assert result.ok is True
        assert result.value.searches == 1

    def test_send_message_handles_api_error(self):
        """send_message() returns Err for API status errors."""
        import anthropic

        mock_client = MagicMock()
        mock_client.messages.stream.return_value.__enter__.side_effect = anthropic.APIStatusError(
            message="Bad request",
            response=MagicMock(status_code=400),
            body={"error": {"message": "Bad request"}},
        )

        result = send_message(
            client=mock_client,
            system="System",
            messages=[Message(role="user", content="Test")],
        )

        assert result.ok is False
        assert result.error.code == "api_error"
        assert "400" in result.error.message
