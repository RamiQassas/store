import os
from unittest.mock import patch, MagicMock
from decimal import Decimal
from django.test import TestCase

from services.provider.alkasr.client import AlkasrAPIClient, AlkasrClient
from services.provider.alkasr.constants import (
    ENDPOINT_PROFILE,
    ENDPOINT_PRODUCTS,
    ENDPOINT_NEW_ORDER,
    ENDPOINT_CHECK_ORDER,
)
from services.provider.alkasr.exceptions import (
    AlkasrAPIException,
    ApiTokenRequiredException,
    InvalidTokenException,
    NotAllowedException,
    IPNotAllowedException,
    MaintenanceException,
    InsufficientBalanceException,
    QuantityNotAvailableException,
    QuantityNotAllowedException,
    PlayerBlockedException,
    TwoFactorRequiredException,
    ProductDeletedException,
    ProductUnavailableException,
    RetryAfterOneMinuteException,
    QuantityTooSmallException,
    QuantityTooLargeException,
    UnknownProviderException,
    InternalServerErrorException,
    TimeoutException,
    NetworkException,
)
from services.provider.alkasr.utils import mask_secrets


class AlkasrAPIClientTestCase(TestCase):
    """
    Comprehensive Test Suite for Phase 3: Centralized AlkasrAPIClient.
    Verifies all required API endpoints, error code exceptions, environment variable fallback,
    parameter formatting, and secret masking.
    """

    def setUp(self):
        self.api_token = "test_secret_token_xyz"
        self.base_url = "https://api.alkasr-vip.com/client/api/"
        self.client = AlkasrAPIClient(api_token=self.api_token, base_url=self.base_url)

    @patch("requests.Session.request")
    def test_get_profile(self, mock_request):
        """1. GET /client/api/profile"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "balance": "450.5000",
            "currency": "USD"
        }
        mock_request.return_value = mock_response

        res = self.client.get_profile()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["balance"], "450.5000")

        # Verify exact request parameters and headers
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["method"], "GET")
        self.assertTrue(kwargs["url"].endswith("/client/api/profile"))
        self.assertEqual(kwargs["headers"]["api-token"], self.api_token)

    @patch("requests.Session.request")
    def test_get_products_all(self, mock_request):
        """2. GET /client/api/products (all products)"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 365, "name": "UC 60", "price": 0.104, "product_type": "amount", "parent_id": 0},
            {"id": 18, "name": "UC 60", "price": 1.094, "product_type": "package", "parent_id": 7}
        ]
        mock_request.return_value = mock_response

        res = self.client.get_products()
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["id"], 365)
        self.assertEqual(res[1]["id"], 18)

        args, kwargs = mock_request.call_args
        self.assertTrue(kwargs["url"].endswith("/client/api/products"))
        self.assertIsNone(kwargs["params"])

    @patch("requests.Session.request")
    def test_get_products_filtered_by_ids(self, mock_request):
        """3. GET /client/api/products?products_id=id1,id2"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 365, "name": "UC 60"}
        ]
        mock_request.return_value = mock_response

        # Test list of IDs
        res = self.client.get_products(products_id=[365, 18])
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["params"]["products_id"], "365,18")

        # Test string of IDs
        self.client.get_products(products_id="7,9")
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["params"]["products_id"], "7,9")

    @patch("requests.Session.request")
    def test_get_content_root(self, mock_request):
        """4. GET /client/api/content/0"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "categories": [{"id": 1, "name": "Games"}]
        }
        mock_request.return_value = mock_response

        res = self.client.get_content(category_id=0)
        args, kwargs = mock_request.call_args
        self.assertTrue(kwargs["url"].endswith("/client/api/content/0"))
        self.assertIn("categories", res)

    @patch("requests.Session.request")
    def test_get_content_specific_category(self, mock_request):
        """5. GET /client/api/content/[category.id]"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "categories": [{"id": 10, "name": "PUBG"}]
        }
        mock_request.return_value = mock_response

        res = self.client.get_content(category_id="10")
        args, kwargs = mock_request.call_args
        self.assertTrue(kwargs["url"].endswith("/client/api/content/10"))

    @patch("requests.Session.request")
    def test_create_order(self, mock_request):
        """6. GET /client/api/newOrder/{PRODUCT_ID}/params"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "wait",
            "order_id": "998877",
            "message": "Order placed successfully"
        }
        mock_request.return_value = mock_response

        order_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        res = self.client.create_order(
            order_uuid=order_uuid,
            product_id="364",
            quantity=1,
            player_params={"playerId": "512345678", "zoneId": "1234"}
        )

        args, kwargs = mock_request.call_args
        self.assertTrue(kwargs["url"].endswith("/client/api/newOrder/364/params"))
        self.assertEqual(kwargs["params"]["order_uuid"], order_uuid)
        self.assertEqual(kwargs["params"]["qty"], 1)
        self.assertEqual(kwargs["params"]["playerId"], "512345678")
        self.assertEqual(kwargs["params"]["zoneId"], "1234")
        self.assertEqual(res["order_id"], "998877")

    @patch("requests.Session.request")
    def test_check_orders_by_ids_and_uuids(self, mock_request):
        """7. GET /client/api/check?orders=[...]"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "1001", "status": "accept"},
            {"id": "1002", "status": "wait"}
        ]
        mock_request.return_value = mock_response

        # Check by numeric provider order IDs
        res = self.client.check_orders(["1001", "1002"], is_uuid=False)
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["params"]["orders"], "[1001,1002]")
        self.assertNotIn("uuid", kwargs["params"])

        # Check by UUIDs
        uuid1 = "11111111-1111-1111-1111-111111111111"
        uuid2 = "22222222-2222-2222-2222-222222222222"
        self.client.check_orders([uuid1, uuid2], is_uuid=True)
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["params"]["orders"], f"[{uuid1},{uuid2}]")
        self.assertEqual(kwargs["params"]["uuid"], "1")

    @patch("requests.Session.request")
    def test_error_code_mapping_exceptions(self, mock_request):
        """8. Verification of all provider error codes to explicit exceptions"""
        error_test_cases = [
            (100, InsufficientBalanceException),
            (105, QuantityNotAvailableException),
            (106, QuantityNotAllowedException),
            (107, PlayerBlockedException),
            (108, TwoFactorRequiredException),
            (109, ProductDeletedException),
            (110, ProductUnavailableException),
            (112, QuantityTooSmallException),
            (113, QuantityTooLargeException),
            (114, UnknownProviderException),
            (120, ApiTokenRequiredException),
            (121, InvalidTokenException),
            (122, NotAllowedException),
            (123, IPNotAllowedException),
            (130, MaintenanceException),
            (500, InternalServerErrorException),
        ]

        for code, expected_exception in error_test_cases:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "status": "error",
                "code": code,
                "message": f"Provider error {code}"
            }
            mock_request.return_value = mock_resp

            with self.assertRaises(expected_exception, msg=f"Error code {code} did not raise {expected_exception.__name__}"):
                self.client.get_profile()

    def test_environment_variable_token_fallback(self):
        """9. Test ALKASR_API_TOKEN environment variable fallback"""
        with patch.dict(os.environ, {"ALKASR_API_TOKEN": "env_fallback_token_123"}):
            cli = AlkasrAPIClient(api_token=None)
            self.assertEqual(cli.api_token, "env_fallback_token_123")

    def test_secret_masking(self):
        """10. Verify that tokens, passwords, and secrets are masked before logging"""
        data = {
            "api-token": "secret_abc",
            "api_token": "secret_def",
            "password": "super_secret_pw",
            "playerId": "12345",
            "nested": {
                "token": "nested_secret",
                "qty": 1
            }
        }
        masked = mask_secrets(data)
        self.assertEqual(masked["api-token"], "***MASKED***")
        self.assertEqual(masked["api_token"], "***MASKED***")
        self.assertEqual(masked["password"], "***MASKED***")
        self.assertEqual(masked["playerId"], "12345")
        self.assertEqual(masked["nested"]["token"], "***MASKED***")
        self.assertEqual(masked["nested"]["qty"], 1)
