class TravelProviderError(Exception):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider


class DatabaseUnavailable(Exception):
    pass