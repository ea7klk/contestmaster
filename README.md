# Contestmaster

Contestmaster is a universal engine for amateur radio contests. Contest managers configure contest rules, accept participant logs, generate results, and publish standings. Contest behavior is defined by versioned rulesets so the scoring engine can serve different contests without contest-specific branches.

## Application overview

- **Frontend:** Vue 3, TypeScript, Vite, Vue Router, and Pinia.
- **API and scoring:** Python 3.12, FastAPI, and Pydantic.
- **Persistence:** SQLite through SQLAlchemy ORM, with schema changes managed by Alembic.
- **Log submissions:** Participants may upload without a system account. Contest-enabled Cabrillo and ADI/ADIF formats are validated by the API.
- **Rules and results:** The graphical ruleset composer configures contest-specific validation and integer-only scoring. Public contest results are viewable without signing in.

Contest rules published by each sponsor remain authoritative. The app's generated summaries and configured rulesets support contest operation but do not replace the official rules.

## Run locally

Requirements and detailed setup instructions are in the [development guide](documentation/development/README.md). With Python 3.12, `uv`, Node.js 24, npm, and Make installed:

```sh
cp .env.example .env
make setup
make dev
```

The frontend is available at <http://localhost:5173>. The API's Swagger UI is at <http://127.0.0.1:8000/api/v1/docs> when the API is running. See the development guide for database initialization, first-administrator setup, environment configuration, and troubleshooting.

## Documentation

- [Architecture and initial feature overview](documentation/README.md)
- [Local development and setup](documentation/development/README.md)
- [API reference](documentation/api/README.md)
- [Contest rules body of knowledge](documentation/radio-contest-body-of-knowledge/README.md)
- [Ruleset composer](documentation/ruleset-composer/README.md)
- [Supported log formats](documentation/formats/README.md)
- [Participant guide](documentation/participants/README.md)
- [Operator guide](documentation/operations/README.md)
- [Implementation plan](documentation/implementation-plan/README.md)

## License

Contestmaster's original software is licensed under [GNU AGPL-3.0-only](LICENSE). Third-party datasets, contest rules, and other imported material retain their own terms; the project license does not grant rights to those materials. See [COPYRIGHT](COPYRIGHT) and the application's attribution footer for further details.
