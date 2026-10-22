# deploy: one client per container (partial hosting)

| File | What it does | Status |
|---|---|---|
| [`../Dockerfile`](../Dockerfile) | Image with the engine code only (no client data, outputs, secrets or MCP server); runs as uid 10001 | Written; **not built** (Docker not installed on the build machine, 2026-10-22) |
| [`compose.yaml`](compose.yaml) | Runs `scripts/run_pipeline.py <CLIENT> <MONTH>`: `clients/<CLIENT>` and its data read-only, `outputs/<CLIENT>` the only writable mount, `network_mode: none`, read-only root, all capabilities dropped | Structure tested in [`../tests/test_deploy.py`](../tests/test_deploy.py) |
| [`../scripts/mcp_per_client.py`](../scripts/mcp_per_client.py) | One stdio MCP server process per client, own credential path (by name), working dir and token store | Tested with a fake server |

Proof without Docker: `tests/test_deploy.py::SimulatedContainerRunTests` copies exactly the Dockerfile's `COPY` sources plus one client's mounts into a temp `/app`, runs the pipeline there, and asserts the abc 2026-06 review packet equals the local run's packet.

Not built on purpose: a network-exposed HTTP wrapper for the MCP server (needs authentication, TLS and a security review; see [`../01_connection/connection_decision.md`](../01_connection/connection_decision.md) section 8).
