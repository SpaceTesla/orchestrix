from orchestrix.api.schemas import RootResponse


def build_root_response(
    *,
    service: str,
    version: str,
    base_url: str,
) -> RootResponse:
    base = base_url.rstrip("/")
    return RootResponse(
        service=service,
        version=version,
        docs=f"{base}/docs",
        openapi=f"{base}/openapi.json",
        health=f"{base}/health",
    )
