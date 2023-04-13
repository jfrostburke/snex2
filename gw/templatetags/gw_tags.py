from django.contrib.auth.models import User, Group
from django import template
import logging

logger = logging.getLogger(__name__)

register = template.Library()

@register.filter
def has_gw_permissions(user):
    gw_group = Group.objects.get(name='GWO4')

    if user in gw_group.user_set.all():
        return True
    return False
