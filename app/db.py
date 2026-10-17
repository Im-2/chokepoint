"""FalkorDB connection and graph selection. No module-level state beyond the client."""
from functools import lru_cache

from falkordb import FalkorDB

from app import config


@lru_cache(maxsize=1)
def get_client() -> FalkorDB:
    # one connection pool per process; holds no application state
    return FalkorDB(
        host=config.FALKORDB_HOST,
        port=config.FALKORDB_PORT,
        username=config.FALKORDB_USERNAME,
        password=config.FALKORDB_PASSWORD,
        ssl=config.FALKORDB_SSL,
    )


def tenant_graph_name(tenant: str | None = None) -> str:
    return f"env:{tenant or config.TENANT_DEFAULT}"


def get_graph(name: str | None = None):
    return get_client().select_graph(name or tenant_graph_name())
