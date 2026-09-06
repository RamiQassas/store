from django.test import TestCase, RequestFactory
from apps.common.views import csrf_failure

class CsrfFailureViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_browser_csrf_failure_renders_friendly_page(self):
        request = self.factory.post("/auth/login/", HTTP_ACCEPT="text/html")
        response = csrf_failure(request, reason="CSRF token from POST incorrect.")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "انتهت صلاحية جلسة الأمان", status_code=403)
        self.assertContains(response, "/auth/login/", status_code=403)

    def test_ajax_csrf_failure_returns_json(self):
        request = self.factory.post("/api/test/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        response = csrf_failure(request, reason="CSRF token from POST incorrect.")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertIn("csrf_failure", response.content.decode())
