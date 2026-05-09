"""Constants for HA-NWR-SDR."""

from __future__ import annotations

DOMAIN = "nwr_sdr"

CONF_TOPIC_ROOT = "topic_root"
CONF_TEST_EFFECTIVE_SEVERITY = "test_effective_severity"
DEFAULT_TOPIC_ROOT = "nwr"
DEFAULT_TEST_EFFECTIVE_SEVERITY = 5

EVENT_ALERT_RECEIVED = "nwr_same_alert_received"
EVENT_EOM_RECEIVED = "nwr_eom_received"
EVENT_ALERT_EXPIRED = "nwr_alert_expired"

TOPIC_STATUS = "status"
TOPIC_AUDIO_URL = "audio/url"
TOPIC_SAME_ALERT = "alert/same"
TOPIC_EOM = "alert/eom"

ATTR_EVENT_CODE = "event_code"
ATTR_EVENT_NAME = "event_name"
ATTR_SEVERITY = "severity"
ATTR_SEVERITY_LABEL = "severity_label"
ATTR_EFFECTIVE_SEVERITY = "effective_severity"
ATTR_EFFECTIVE_SEVERITY_LABEL = "effective_severity_label"
ATTR_COUNTIES = "counties"
ATTR_COUNTY_CODES = "county_codes"
ATTR_ISSUE_UTC = "issue_utc"
ATTR_EXPIRY_UTC = "issue_expiry_utc"
ATTR_REMAINING_SECONDS = "true_remaining_secs"
ATTR_RAW = "raw"

EVENT_NAMES = {
    "TOR": "Tornado Warning",
    "EWW": "Extreme Wind Warning",
    "FFW": "Flash Flood Warning",
    "TSW": "Tsunami Warning",
    "NUW": "Nuclear Power Plant Warning",
    "RHW": "Radiological Hazard Warning",
    "HMW": "Hazardous Materials Warning",
    "SPW": "Shelter-in-Place Warning",
    "EVI": "Evacuation Immediate",
    "CDW": "Civil Danger Warning",
    "VOW": "Volcano Warning",
    "EQW": "Earthquake Warning",
    "LEW": "Law Enforcement Warning",
    "LAW": "Local Area Emergency",
    "CEM": "Civil Emergency Message",
    "SVR": "Severe Thunderstorm Warning",
    "BZW": "Blizzard Warning",
    "ISW": "Ice Storm Warning",
    "HUW": "Hurricane Warning",
    "WSW": "Winter Storm Warning",
    "FRW": "Fire Warning",
    "AVW": "Avalanche Warning",
    "SMW": "Special Marine Warning",
    "HWW": "High Wind Warning",
    "FLW": "Flood Warning",
    "DSW": "Dust Storm Warning",
    "EHW": "Extreme Heat Warning",
    "ECW": "Extreme Cold Warning",
    "TYW": "Typhoon Warning",
    "TOA": "Tornado Watch",
    "SVA": "Severe Thunderstorm Watch",
    "FFA": "Flash Flood Watch",
    "FLA": "Flood Watch",
    "HUA": "Hurricane Watch",
    "WSA": "Winter Storm Watch",
    "BZA": "Blizzard Watch",
    "AVA": "Avalanche Watch",
    "HWA": "High Wind Watch",
    "TYA": "Typhoon Watch",
    "TSA": "Tsunami Watch",
    "EHA": "Extreme Heat Watch",
    "ECA": "Extreme Cold Watch",
    "FRA": "Fire Watch",
    "DBA": "Dense Fog Watch",
    "SPS": "Special Weather Statement",
    "FLS": "Flood Statement",
    "FFS": "Flash Flood Statement",
    "HLS": "Hurricane Local Statement",
    "MWS": "Marine Weather Statement",
    "WIY": "Wind Advisory",
    "WCY": "Wind Chill Advisory",
    "FZW": "Freeze Warning",
    "HZW": "Hard Freeze Warning",
    "FZA": "Freeze Watch",
    "HZA": "Hard Freeze Watch",
    "FWW": "Red Flag Warning",
    "DUY": "Blowing Dust Advisory",
    "FOG": "Dense Fog Advisory",
    "SBY": "Snow and Blowing Snow Advisory",
    "BHY": "Beach Hazard Statement",
    "LWY": "Lake Wind Advisory",
    "AQY": "Air Quality Alert",
    "ASY": "Air Stagnation Advisory",
    "FWA": "Fire Weather Watch",
    "RWT": "Required Weekly Test",
    "RMT": "Required Monthly Test",
    "DMO": "Practice/Demo Warning",
    "NMN": "Network Message Notification",
    "ADR": "Administrative Message",
}

TIER_BY_CODE = {
    "TOR": 1,
    "EWW": 1,
    "FFW": 1,
    "TSW": 1,
    "NUW": 1,
    "RHW": 1,
    "HMW": 1,
    "SPW": 1,
    "EVI": 1,
    "CDW": 1,
    "VOW": 1,
    "EQW": 1,
    "LEW": 1,
    "LAW": 1,
    "CEM": 1,
    "SVR": 2,
    "BZW": 2,
    "ISW": 2,
    "HUW": 2,
    "WSW": 2,
    "FRW": 2,
    "AVW": 2,
    "SMW": 2,
    "HWW": 2,
    "FLW": 2,
    "DSW": 2,
    "EHW": 2,
    "ECW": 2,
    "TYW": 2,
    "TOA": 3,
    "SVA": 3,
    "FFA": 3,
    "FLA": 3,
    "HUA": 3,
    "WSA": 3,
    "BZA": 3,
    "AVA": 3,
    "HWA": 3,
    "TYA": 3,
    "TSA": 3,
    "EHA": 3,
    "ECA": 3,
    "FRA": 3,
    "DBA": 3,
    "SPS": 4,
    "FLS": 4,
    "FFS": 4,
    "HLS": 4,
    "MWS": 4,
    "WIY": 4,
    "WCY": 4,
    "FZW": 4,
    "HZW": 4,
    "FZA": 4,
    "HZA": 4,
    "FWW": 4,
    "DUY": 4,
    "FOG": 4,
    "SBY": 4,
    "BHY": 4,
    "LWY": 4,
    "AQY": 4,
    "ASY": 4,
    "FWA": 4,
    "RWT": 5,
    "RMT": 5,
    "DMO": 5,
    "NMN": 5,
    "ADR": 5,
}

SEVERITY_LABELS = {
    1: "Imminent Threat",
    2: "Warning",
    3: "Watch",
    4: "Advisory",
    5: "Test",
}
