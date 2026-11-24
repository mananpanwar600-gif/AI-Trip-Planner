# Evaluation and local checks

Run the deterministic unit suite from the repository root:

```powershell
python -m pytest backend/tests
```

The tests mock Groq and weather responses; they do not consume API credits or
depend on live provider availability. Run `ruff check backend` for linting.

For a manual smoke test, start the app as described in the README, open the
homepage, and submit a short trip. A generated plan should include a day for
each requested trip day. Available live-source facts appear under **Live travel
context**; provider failures appear there as warnings. Check `/api/health` to
confirm configuration without exposing API keys.