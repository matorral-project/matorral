import os

from django.core.exceptions import ValidationError
from django.core.validators import BaseValidator
from django.utils.translation import gettext as _


class ProfilePictureValidator(BaseValidator):
    valid_extensions = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
    max_file_size = 5 * 1024 * 1024  # 5 MB

    def __init__(self):
        pass

    def __call__(self, value):
        file_extension = os.path.splitext(value.name)[1].lower()
        if file_extension not in self.valid_extensions:
            raise ValidationError(
                _("Please upload a valid image file! Supported types are {types}").format(
                    types=", ".join(self.valid_extensions),
                )
            )
        if value.size > self.max_file_size:
            size_in_mb = value.size // 1024**2
            raise ValidationError(
                _("Maximum file size allowed is 5 MB. Provided file is {size} MB.").format(
                    size=size_in_mb,
                )
            )


validate_profile_picture = ProfilePictureValidator()
