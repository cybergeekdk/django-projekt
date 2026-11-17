# django-projekt – overvågning af Linux-servere og containere

Django (servere, containere, brugere, Bootstrap-frontend) + Grafana (tidsserier og alarmer)
oven på en fælles PostgreSQL-database.

```
Servere ──► collector (manage.py collect) ──► PostgreSQL ◄── Grafana
                                                  ▲            │ iframe
                                  Django + Bootstrap ──────────┘
```

## Kør med Docker Compose
```bash
cp .env.example .env      # ret adgangskoder og SECRET_KEY
docker compose up -d --build
```
- Django: http://localhost:8000  (login: `admin` / `admin`, medmindre du har sat `DJANGO_ADMIN_*` i `.env`)
- Grafana: http://localhost:3000 (bruger `admin`, adgangskode fra `GRAFANA_ADMIN_PASSWORD`)

**Skift standard-adgangskoden** (`docker compose exec web python manage.py changepassword admin`)
før andre kan nå systemet. Skift også `GRAFANA_RO_PASSWORD` i både `.env` og `docker/db-init.sql`
**før første start** (scriptet kører kun, når databasen oprettes første gang).

## Tilføj servere
1. Log ind på Django → Admin → Servere → tilføj. `localhost` måler Docker-værten
   (collector-containeren ser værtens CPU/RAM/containere via `/proc` og Docker-socketten).
2. Fjernservere nås via SSH fra collector-containeren:
   - Læg den **private** nøgle i `./ssh/` (fx `./ssh/id_rsa`, `chmod 600`). Mappen er git-ignoreret.
   - Nøglen skal være tilladt på serveren: `ssh-copy-id -i ./ssh/id_rsa.pub bruger@server`.
   - I Django skriver du stien **set indefra containeren**: `/root/.ssh/id_rsa`
     (ikke `/home/dig/.ssh/...` og ikke `.pub`).
   - Serverens værtsnøgle huskes automatisk første gang (`accept-new`) i volumen `sshdata`.
     Skifter serverens nøgle senere, afvises forbindelsen. Nulstil med
     `docker compose exec collector ssh-keygen -f /data/ssh/known_hosts -R server`.
   - Brugeren skal have lov at køre `docker`.
3. Collector henter nye målinger hvert 60. sekund. Dashboardet viser dem, og Grafana-panelerne
   på hver servers side viser de seneste 24 timer.

## Hvad måles
| Område | Detaljer |
|---|---|
| System | CPU (load/kerner), RAM, **swap**, oppetid |
| Diske | **Alle filsystemer** med brug og **inodes** (pseudo-mounts og containerens egne bind-mounts filtreres fra) |
| Containere | Status, **CPU, RAM, genstarter, exit-kode, OOM** (graf-historik for kørende containere) |
| Tjenester | **Fejlede systemd-tjenester** (`systemctl --failed`) |
| Opdateringer | Ventende apt-opdateringer, heraf sikkerhed, og **genstart påkrævet** (kun Debian/Ubuntu) |

En container vises som problem, hvis den har ≥3 genstarter (crash-loop), er OOM-dræbt eller er stoppet med en fejlkode.

**Oprydning:** Målinger ældre end `METRICS_RETENTION_DAYS` (standard 30) slettes automatisk hver time af collectoren.
Manuelt: `python manage.py prune --days 14`.

## Lokal udvikling (uden Docker)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py runserver
python manage.py collect            # eller --interval 60
```
Uden `POSTGRES_DB` bruger Django SQLite. Grafana-panelerne kræver Compose-opsætningen.

## Sikkerhed
- Grafana tillader anonym *læse*adgang, så panelerne kan indlejres. Udsæt ikke port 3000
  for upålidelige netværk, eller sæt en reverse proxy med login foran.
- Collector kører som root og har Docker-socketten, hvilket svarer til root på værten.
- Frontend henter Bootstrap fra jsDelivr (CDN). På net uden internet skal filerne lægges i `static/`.

## Tests
```bash
python manage.py test
```
