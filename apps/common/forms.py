import re
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

class DynamicFormValidator:
    """
    Validates user input against a versioned JSON schema.
    Supported types: text, textarea, number, email, date, phone, boolean.
    """
    def __init__(self, schema):
        self.schema = schema or {}
        self.version = self.schema.get("version", 1)
        self.fields = self.schema.get("fields", [])

    def validate(self, data):
        """
        Validates the data dictionary against the schema fields.
        Returns cleaned data or raises ValidationError.
        """
        cleaned_data = {}
        errors = {}

        for field in self.fields:
            name = field.get("name") or field.get("label")
            if not name:
                continue
                
            value = data.get(name)
            is_required = field.get("required", False)
            field_type = field.get("type", "text")
            label = field.get("label", name)

            # Required Check
            if is_required and (value is None or value == ""):
                errors[name] = _("حقل {label} مطلوب.").format(label=label)
                continue

            if value is None or value == "":
                cleaned_data[name] = value
                continue

            # Type Validation
            try:
                if field_type == "number":
                    cleaned_data[name] = float(value)
                elif field_type == "email":
                    validate_email(value)
                    cleaned_data[name] = value
                elif field_type == "boolean":
                    cleaned_data[name] = str(value).lower() in ["true", "1", "yes", "on"]
                elif field_type == "phone":
                    if not re.match(r"^\+?1?\d{9,15}$", str(value)):
                        errors[name] = _("رقم هاتف {label} غير صالح.").format(label=label)
                    else:
                        cleaned_data[name] = value
                elif field_type in ["file", "image"]:
                    # These should be in request.FILES, handled by the caller
                    cleaned_data[name] = value
                else:
                    cleaned_data[name] = str(value)
            except (ValueError, ValidationError):
                errors[name] = _("قيمة غير صالحة لحقل {label} ({field_type}).").format(label=label, field_type=field_type)

        if errors:
            raise ValidationError(errors)
            
        return cleaned_data
