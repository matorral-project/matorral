from django import template

register = template.Library()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@register.filter
def filter_images(attachments):
    return [a for a in attachments if a.filename.lower().endswith(tuple(IMAGE_EXTENSIONS))]


@register.filter
def is_image(attachment):
    return attachment.filename.lower().endswith(tuple(IMAGE_EXTENSIONS))
