# ==================== config.py ====================
# Ports
HTTP_PORT = 9090
WS_PORT_KDS = 9999
WS_PORT_KDS_DEL = 9998

# Database connection string (update for your setup)
DB_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=pc1;"
    "DATABASE=synopos-cp;"
    "UID=posgst11;"
    "PWD=hello213;"
)

# Optional: If set, WebSocket clients must pass token in URL: ws://host:9999?token=YOUR_TOKEN
SECRET_TOKEN = ""   # leave empty for now to keep open access
