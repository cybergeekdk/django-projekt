# django-projekt – overvågning af Linux-servere og containere

Django-app der indsamler CPU (load/kerner), RAM, disk, oppetid og Docker-containere
fra lokale Linux-servere (lokalt eller via SSH) og viser dem på et dashboard.

## Opsætning
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Standard-login
`migrate` opretter en admin, hvis der ingen superbruger er: **admin / admin**.
Sæt egne værdier med `DJANGO_ADMIN_USER` og `DJANGO_ADMIN_PASSWORD` før første `migrate`,
og **skift adgangskoden** (`python manage.py changepassword admin`) før andre kan nå systemet.

## Brug
1. Log ind på `/admin/` og tilføj servere (`localhost` måler maskinen Django kører på).
2. Fjernservere kræver SSH-nøgle uden adgangskode og `docker`-adgang for brugeren.
3. `python manage.py collect` (eller `--interval 60` for løbende), eller vælg handlingen
   "Indsaml målinger nu" i serverlisten.
4. Dashboardet er på `/` (kræver login).
