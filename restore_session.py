import os, base64, gzip, sys

session_b64 = os.environ.get("TELEGRAM_SESSION_B64", "")
if not session_b64:
    print("ERROR: TELEGRAM_SESSION_B64 not set")
    sys.exit(1)

decoded = base64.b64decode(session_b64)
try:
    decoded = gzip.decompress(decoded)
    print("Session decompressed (gzip)")
except Exception:
    print("Session not compressed, using raw")

path = "/tmp/telegram_session.session"
with open(path, "wb") as f:
    f.write(decoded)

print(f"Session restored: {len(decoded)} bytes -> {path}")
