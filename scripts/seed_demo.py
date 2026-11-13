from app.storage.database import SessionLocal
from app.storage.repository import AthleteRepository
from app.config import get_settings
from simulator.scenarios import seed_demo_scenario


def main():
    settings = get_settings()
    with SessionLocal() as db:
        repo = AthleteRepository(db)
        repo.ensure_identity(settings.default_tenant_id, settings.default_subject)
        athlete = seed_demo_scenario(repo, settings.default_tenant_id)
        db.commit()
        print(athlete.id)


if __name__ == '__main__':
    main()
