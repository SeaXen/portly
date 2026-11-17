# Contributing to Portly ⚓

Thank you for contributing to Portly! We welcome bug reports, feature suggestions, documentation improvements, and pull requests.

---

## 🛠️ Development Setup

### Prerequisites
- Python 3.10+ (tested through Python 3.13)
- Node.js 18+ and npm
- Docker Desktop or Docker Engine (optional, for container features)

### Setting Up Local Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/SeaXen/Portly.git
   cd Portly
   ```

2. **Setup Python virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Setup Frontend:**
   ```bash
   cd portly/frontend
   npm install
   ```

4. **Running Development Mode:**
   ```bash
   # Terminal 1: Backend
   python -m portly run --port 5533

   # Terminal 2: Frontend
   cd portly/frontend
   npm run dev
   ```

---

## 🧪 Testing Guidelines

Before opening a pull request, ensure all tests pass:

```bash
# 1. Run Python unit and integration tests:
$env:PORTLY_TESTING="1"; python -m pytest tests -q --ignore=tests/e2e

# 2. Verify Frontend TypeScript types and production build:
npm --prefix portly/frontend run build
```

When adding new features or fixing bugs:
- Add tests under `tests/` matching your module.
- Keep unit tests self-contained and mock external Docker calls.
- Enforce Safe Mode verification on any mutating operations.

---

## 📐 Coding Standards

- **Python**: Follow PEP 8 guidelines. Use type hints across all function signatures. Format with `black` or `ruff`.
- **TypeScript / React**: Use functional components, explicit TypeScript interfaces, and avoid inline styles where tokens exist.
- **Accessibility**: Never use browser `alert()` or `confirm()`. Use accessible `Toast` and `ConfirmDialog` components with appropriate ARIA roles and keyboard traps.
- **Local-First**: Do not introduce external CDN dependencies (fonts, stylesheets, remote scripts). Portly must run completely self-contained offline.
