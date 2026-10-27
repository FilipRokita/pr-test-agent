# Taskly App

## Setup

```sh
cp .env.example .env
```

## Docker

```sh
docker compose up --build -d --wait
```

Application: http://localhost:8080. API: http://localhost:8000/docs.

```sh
docker compose down
```

## Frontend

Installation:

```sh
cd frontend
npm ci
```

Development: http://localhost:5173:

```sh
npm run dev
```

Storybook: http://localhost:6006:

```sh
npm run storybook
```

Tests:

```sh
npm test
```

Coverage: `frontend/coverage/index.html`:

```sh
npm run test:coverage
```

## Backend

Installation (from the repository root):

```sh
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
```

Development: http://localhost:8000/docs:

```sh
docker compose up -d --wait postgres
cd backend
python -m uvicorn app.main:app --reload
```

Tests (in `backend`, with `.venv` activated):

```sh
python -m pytest
```

Coverage: `backend/coverage/html/index.html`:

```sh
python -m pytest --cov=app --cov-report=term-missing --cov-report=html
```

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`: backend tests with coverage,
frontend typecheck, Prettier check and tests with coverage, workflow linting (actionlint, zizmor) and a
secret scan (gitleaks). Actions are pinned to commit SHAs and Dependabot keeps them, `pip` and `npm`
dependencies current. Security reports: see [SECURITY.md](SECURITY.md).

## Test agent

Pull requests from this repository get unit tests proposed by an agent; see [SOLUTION.md](SOLUTION.md) for how it
works and [docs/](docs/architecture.md) for details. The workflow is
`.github/workflows/test-agent.yml`; the agent, its skills and the runner that drives it live in
`.github/test-agent/`.

Runner tests (no network, no credentials; the sandbox tests need `sudo` or root):

```sh
python -m venv .github/test-agent/runner/.venv
.github/test-agent/runner/.venv/bin/pip install -r .github/test-agent/runner/requirements-dev.txt
cd .github/test-agent/runner && .venv/bin/python -m pytest
```
