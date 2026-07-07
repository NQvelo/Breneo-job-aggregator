"""Domain exceptions for the mock interview API."""


class InterviewAPIError(Exception):
    """Base exception for interview API errors."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class WhisperTranscriptionError(InterviewAPIError):
    def __init__(self, message: str = "Speech-to-text transcription failed."):
        super().__init__(message, status_code=502)


class LLMServiceError(InterviewAPIError):
    def __init__(self, message: str = "LLM service request failed."):
        super().__init__(message, status_code=502)


class LLMResponseParseError(InterviewAPIError):
    def __init__(self, message: str = "LLM returned invalid JSON."):
        super().__init__(message, status_code=502)


class TTSServiceError(InterviewAPIError):
    def __init__(self, message: str = "Georgian speech synthesis failed."):
        super().__init__(message, status_code=502)
