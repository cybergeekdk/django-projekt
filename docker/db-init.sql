-- Kører én gang ved første start af databasen.
-- Skrivebeskyttet bruger til Grafana, med adgang til tabeller Django opretter senere.
CREATE ROLE grafana_ro LOGIN PASSWORD 'grafana_ro_change_me';
GRANT CONNECT ON DATABASE monitor TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE django IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
