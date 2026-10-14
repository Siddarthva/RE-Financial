import streamlit as st

import data
import ui

FLOW = """
digraph G {
  rankdir=LR; node [shape=box, style="rounded", fontname="Helvetica", fontsize=11];
  wb [label="Source workbook\\n(read-only)"];
  qb [label="QuickBooks MCP\\n(stdio, read-only)", style="rounded,dashed"];
  engine [label="Python engine\\ncomputes every number"];
  out [label="outputs/client/\\nJSON + Excel"];
  skill [label="Skill draft\\ncommentary"];
  grader [label="Deterministic grader"];
  rev [label="finance-reviewer\\n(second model)"];
  human [label="Human approval\\nscripts/approve.py"];
  app [label="This workspace\\n(display only)"];
  wb -> engine; engine -> out; out -> skill [label="packet JSON only"];
  skill -> grader; skill -> rev; grader -> out; rev -> out;
  out -> human; human -> out [label="approval + audit log"]; out -> app;
  qb -> out [style=dashed, label="evidence"];
}
"""


def _doc(name, title):
    d = data.load_doc(name)
    if d.ok:
        st.markdown(d.data)
        ui.source_note(d.path)
    else:
        ui.empty_state(title, d.path, "This document does not exist yet; the app does not generate it.")


def render():
    ui.title("Architecture & Security")
    st.subheader("Data flow")
    st.graphviz_chart(FLOW)
    t = st.tabs(["Architecture", "Workflow", "Credentials", "Client isolation", "Traceability"])
    with t[0]:
        _doc("architecture.md", "architecture document")
    with t[1]:
        _doc("workflow.md", "workflow document")
    with t[2]:
        st.markdown(
            "- QuickBooks MCP runs with `QUICKBOOKS_DISABLE_WRITE`, `_UPDATE` and `_DELETE` set to `true`; only read tools are called.\n"
            "- Secrets live outside the repo. Hooks block reads of `.env`, token and credential files, and a secret scan runs in the final run.\n"
            "- This workspace never reads credentials. The connection test returns fixed messages only: no tokens, no realm IDs.\n"
            "- **Not applied:** a separate write credential for the loader. **Proposed:** per-client OAuth grants and token stores.")
        st.caption("Summarised from docs/architecture.md, 'Credential security'.")
    with t[3]:
        st.markdown(
            "- **Implemented:** per-client config and `outputs/<client>/`. An in-process audit hook blocks reads of other clients' folders "
            "and writes outside the client's own output folder (`tests/test_client_isolation.py`).\n"
            "- The model sees only one client's packet JSON for one month. No cross-client memory.\n"
            "- **Limits:** the hook covers the Python process only; Claude's own tools run as the same OS user. "
            "Only two clients exist; ten is untested.")
        st.caption("Summarised from docs/architecture.md, 'Ten-client isolation'.")
    with t[4]:
        _doc("brief_traceability.md", "brief traceability")
