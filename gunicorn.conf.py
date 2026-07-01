import multiprocessing
import os

bind = os.getenv("UVICORN_BIND", "0.0.0.0:8000")
workers = int(os.getenv("UVICORN_WORKERS", str(multiprocessing.cpu_count())))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
