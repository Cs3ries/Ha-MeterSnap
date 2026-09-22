"""Constants for the MeterSnap integration."""

DOMAIN = "meter_snap"
NAME = "MeterSnap"
VERSION = "1.1.4-b3"

# Storage
STORAGE_KEY = "meter_snap_data"
STORAGE_VERSION = 1
IMAGE_DIR = "meter_snap/images"

# Meter Types
METER_ELECTRICITY = "electricity"
METER_GAS = "gas"
METER_AUTO = "auto"
METER_TYPES = [METER_ELECTRICITY, METER_GAS]

# OCR Providers
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_CUSTOM = "custom"
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai"
PROVIDER_NONE = "none"
OCR_PROVIDERS = [PROVIDER_OPENROUTER, PROVIDER_CUSTOM, PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_NONE]

# Default AI Models & Endpoints
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_OPENROUTER_MODEL = "inclusionai/ling-3.0-flash-vl:free"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_CUSTOM_MODEL = "llava"
DEFAULT_CUSTOM_ENDPOINT = "http://localhost:11434/v1/chat/completions"

# Optional dashboard
CONF_ENERGY_DASHBOARD = "energy_dashboard"

# Configuration Keys - General / AI
CONF_OCR_PROVIDER = "ocr_provider"
CONF_API_KEY = "api_key"
CONF_CUSTOM_ENDPOINT = "custom_endpoint"
CONF_CUSTOM_MODEL = "custom_model"

# Configuration Keys - Electricity
CONF_ELEC_ENABLED = "electricity_enabled"
CONF_ELEC_NAME = "electricity_name"
CONF_ELEC_UNIT_PRICE = "electricity_unit_price"  # in €/kWh (z.B. 0.32)
CONF_ELEC_BASE_PRICE = "electricity_base_price"  # in €/Monat (z.B. 12.0)
CONF_ELEC_MONTHLY_PAYMENT = "electricity_monthly_payment"  # Abschlagszahlung €/Monat

# Configuration Keys - Gas
CONF_GAS_ENABLED = "gas_enabled"
CONF_GAS_NAME = "gas_name"
CONF_GAS_UNIT_PRICE = "gas_unit_price"  # in €/kWh (z.B. 0.10)
CONF_GAS_BASE_PRICE = "gas_base_price"  # in €/Monat (z.B. 10.0)
CONF_GAS_MONTHLY_PAYMENT = "gas_monthly_payment"  # Abschlagszahlung €/Monat
CONF_GAS_CALORIFIC_VALUE = "gas_calorific_value"  # Brennwert (z.B. 11.2 kWh/m³)
CONF_GAS_CONVERSION_FACTOR = "gas_conversion_factor"  # Zustandszahl Z (z.B. 0.95)

# Defaults
DEFAULT_ELEC_UNIT_PRICE = 0.32
DEFAULT_ELEC_BASE_PRICE = 12.0
DEFAULT_ELEC_MONTHLY_PAYMENT = 90.0

DEFAULT_GAS_UNIT_PRICE = 0.10
DEFAULT_GAS_BASE_PRICE = 10.0
DEFAULT_GAS_MONTHLY_PAYMENT = 110.0
DEFAULT_GAS_CALORIFIC_VALUE = 11.2
DEFAULT_GAS_CONVERSION_FACTOR = 0.95

# Sensor Keys
SENSOR_CURRENT_READING = "reading"
SENSOR_LAST_CONSUMPTION = "last_consumption"
SENSOR_LAST_COST = "last_cost"
SENSOR_DAILY_AVERAGE = "daily_average"
SENSOR_PROJECTED_MONTHLY_COST = "projected_monthly_cost"
