from prometheus_client import start_http_server

from orchestrix.core.logging import get_logger

log = get_logger(__name__)


def start_worker_metrics_server(*, port: int, addr: str = "0.0.0.0") -> None:
    """Expose Prometheus metrics on a dedicated HTTP port (default 9090)."""
    start_http_server(port, addr=addr)
    log.info("worker_metrics_server_started", port=port, addr=addr)
