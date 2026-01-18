---
description: Restart the Streamlit server to clear stale state or bytecode
---

1. Kill the existing Streamlit process.
// turbo
2. Start the Streamlit server on port 8503.

```bash
pkill -f "streamlit run app.py"
streamlit run app.py --server.port 8503 &
```
