# Agent Notes — agent-canvas

TypeScript/React UI for OpenHands agent servers.

## Layout
- `src/` — React components and app logic
- `scripts/` — dev scripts (`dev:dangerously-dockerless` spawns agent-server + automation backend via uvx)
- `DEVELOPMENT.md` — canonical dev setup guide

## Key config
- `VITE_BACKEND_HOST` — controls which backend the frontend talks to; set by the dev script launcher
- Dev stack runs: ingress on `:8000`, Vite on `:3001`, agent-server on `:18000`, automation on `:18001`
- State lives under `~/.openhands/agent-canvas/`
