# Quickstart

The quickstart gets you from zero to a visible OpenHands trace. The full runnable instructions live in the repo at [`01-quickstart.md`](https://github.com/rajshah4/learn-openhands-harness/blob/main/01-quickstart.md).

## What You Are Proving

You are proving that Agent Server and Agent Canvas are alive, that the model can run through the harness, and that you can inspect the resulting events.

The first run is intentionally small:

```text
Read the current repo and write three facts about it into FACTS.txt.
```

## Minimal Flow

1. Clone `OpenHands/agent-canvas`.
2. Run `npm install`.
3. Run `npm run dev`.
4. Open `http://localhost:8000`.
5. Configure the model key in settings.
6. Send the first prompt.
7. Inspect the trace.

The quickstart also shows how to call the same server through the Python SDK, which makes the key point visible: Canvas and the SDK are different clients on the same harness runtime.

## Safety Note

The first setup is dockerless so the moving parts are easy to see. Treat that as a learning microscope, not a safe operating mode. Use a scratch repo. P06 moves the harness into `DockerWorkspace`.

## Continue

After the health check passes, take the [Harness Tour](/harness-tour).
