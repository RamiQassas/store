import contextvars
import contextlib
from django.db import models

# Context variables to hold the active store and the bypass flag
_current_store = contextvars.ContextVar('current_store', default=None)
_bypass_tenant_filter = contextvars.ContextVar('bypass_tenant_filter', default=False)

def get_current_store():
    return _current_store.get()

def set_current_store(store):
    return _current_store.set(store)

def reset_current_store(token):
    _current_store.reset(token)

def is_tenant_filter_bypassed():
    return _bypass_tenant_filter.get()

@contextlib.contextmanager
def bypass_tenant_filter():
    token = _bypass_tenant_filter.set(True)
    try:
        yield
    finally:
        _bypass_tenant_filter.reset(token)

class TenantManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        
        # Safe check for migrations
        try:
            self.model._meta.get_field("store")
        except Exception:
            return qs

        if _bypass_tenant_filter.get():
            return qs
        
        store = _current_store.get()
        if store is not None:
            # We are on a tenant store, return only this store's data
            return qs.filter(store=store)
        else:
            # We are on the main platform, return only main platform data (where store is None)
            return qs.filter(store__isnull=True)
