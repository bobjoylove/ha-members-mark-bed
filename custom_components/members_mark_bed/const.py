"""Constants for the Member's Mark WiFi Bed integration."""

DOMAIN = "members_mark_bed"
CONF_ACCESS_KEY = "access_key"
CONF_HEAD_MAX = "head_max"
CONF_FOOT_MAX = "foot_max"

DEFAULT_HOST = ""
# Raw readings at full raise. Highest seen so far: head 9779, foot 6244.
# The covers widen these automatically if the bed reports a higher value.
DEFAULT_HEAD_MAX = 10000
DEFAULT_FOOT_MAX = 6500
