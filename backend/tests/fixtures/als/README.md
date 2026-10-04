# ALS fixtures

| File | Status |
| --- | --- |
| `bridge_ok.json` | **Real.** Recorded 2026-10-04 from `/bridge?player=xXfrankX&platform=PC&merge=1&removeMerged=1` (HTTP 200, 9,333 bytes). Frank's Steam account: looked up by EA ID `xXfrankX`, returned with the Steam display name `vinyasaflowTTV`. Level, tier and career kills were checked against the in-game stats screen. |
| `bridge_not_found.json` | **Real.** Recorded 2026-10-04 from `/bridge` with a made-up name (HTTP 404). |
| `rate_limited_200.json` | Provisional. The "200 instead of 429" body cannot be recorded on demand; the message text is a guess. |

Two real `/nametouid` error messages (both HTTP 200) are kept as constants in `tests/test_als_client.py`. The app does not call `/nametouid`: on the recording date it failed for PC names that `/bridge` resolved.

Re-record with:

```
cd backend
uv run apexrep-record-fixture --name <EA name> --platform PC
```

On PC the name must be the EA account name. The recorder stops without touching `bridge_ok.json` if ALS cannot resolve the name. After re-recording, update the expected values in `tests/test_als_parser.py` and `tests/test_als_client.py`.
