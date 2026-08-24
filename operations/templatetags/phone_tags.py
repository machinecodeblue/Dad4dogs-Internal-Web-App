from django import template

from operations.services.phones import format_phone, tel_href

register = template.Library()


@register.filter
def phone_display(value):
    return format_phone(value or '')


@register.filter
def as_tel(value):
    return tel_href(value or '')
