class ProviderError(Exception):
    def __init__(self, message, code=None, original_response=None):
        super().__init__(message)
        self.code = code
        self.original_response = original_response

class AuthenticationError(ProviderError): pass
class BalanceError(ProviderError): pass
class ProductUnavailableError(ProviderError): pass
class InvalidQuantityError(ProviderError): pass
class OrderFailedError(ProviderError): pass
class NetworkError(ProviderError): pass
class APIError(ProviderError): pass
