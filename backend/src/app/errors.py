from fastapi import HTTPException


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def to_http_error(error: DomainError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)
