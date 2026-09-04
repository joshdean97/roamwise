import os


bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
worker_class = "gthread"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("WEB_THREADS", "4"))
timeout = int(os.environ.get("WEB_TIMEOUT", "30"))
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
capture_output = True
max_requests = int(os.environ.get("WEB_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("WEB_MAX_REQUESTS_JITTER", "100"))
