"""
Custom Exceptions for Alkasr VIP Provider Integration.
Translates provider error codes into explicit internal exceptions.
"""

from .constants import ERROR_CODES


class AlkasrAPIException(Exception):
    """Base exception for all Alkasr API errors."""
    def __init__(self, message=None, code=None, raw_response=None):
        self.code = code
        self.raw_response = raw_response or {}
        if not message:
            message = ERROR_CODES.get(code, f"Alkasr API error (code {code})")
        self.message = message
        super().__init__(self.message)


class ApiTokenRequiredException(AlkasrAPIException):
    """Code 120: API Token Required"""
    pass


class InvalidTokenException(AlkasrAPIException):
    """Code 121: Invalid Token"""
    pass


class NotAllowedException(AlkasrAPIException):
    """Code 122: Action Not Allowed"""
    pass


class IPNotAllowedException(AlkasrAPIException):
    """Code 123: IP Not Allowed"""
    pass


class MaintenanceException(AlkasrAPIException):
    """Code 130: Maintenance"""
    pass


class InsufficientBalanceException(AlkasrAPIException):
    """Code 100: Insufficient Balance"""
    pass


class QuantityNotAvailableException(AlkasrAPIException):
    """Code 105: Quantity Not Available"""
    pass


class QuantityNotAllowedException(AlkasrAPIException):
    """Code 106: Quantity Not Allowed"""
    pass


class PlayerBlockedException(AlkasrAPIException):
    """Code 107: Player Blocked"""
    pass


class TwoFactorRequiredException(AlkasrAPIException):
    """Code 108: 2FA Required"""
    pass


class ProductDeletedException(AlkasrAPIException):
    """Code 109: Product Deleted"""
    pass


class ProductUnavailableException(AlkasrAPIException):
    """Code 110: Unavailable"""
    pass


class RetryAfterOneMinuteException(AlkasrAPIException):
    """Code 111: Retry After One Minute"""
    pass


class QuantityTooSmallException(AlkasrAPIException):
    """Code 112: Quantity Too Small"""
    pass


class QuantityTooLargeException(AlkasrAPIException):
    """Code 113: Quantity Too Large"""
    pass


class UnknownProviderException(AlkasrAPIException):
    """Code 114: Unknown Error"""
    pass


class InternalServerErrorException(AlkasrAPIException):
    """Code 500: Internal Server Error"""
    pass


class NetworkException(AlkasrAPIException):
    """Network failure or connection error."""
    pass


class TimeoutException(AlkasrAPIException):
    """HTTP Request timeout."""
    pass


class ValidationException(AlkasrAPIException):
    """Pre-order or configuration validation failure."""
    pass


EXCEPTION_CODE_MAP = {
    100: InsufficientBalanceException,
    105: QuantityNotAvailableException,
    106: QuantityNotAllowedException,
    107: PlayerBlockedException,
    108: TwoFactorRequiredException,
    109: ProductDeletedException,
    110: ProductUnavailableException,
    111: RetryAfterOneMinuteException,
    112: QuantityTooSmallException,
    113: QuantityTooLargeException,
    114: UnknownProviderException,
    120: ApiTokenRequiredException,
    121: InvalidTokenException,
    122: NotAllowedException,
    123: IPNotAllowedException,
    130: MaintenanceException,
    500: InternalServerErrorException,
}


def raise_for_code(code, message=None, raw_response=None):
    """Factory method to raise specific Alkasr exception based on error code."""
    exc_class = EXCEPTION_CODE_MAP.get(code, AlkasrAPIException)
    raise exc_class(message=message, code=code, raw_response=raw_response)
